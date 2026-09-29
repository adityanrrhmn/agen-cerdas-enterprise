"""Alur ujung ke ujung dengan integrasi simulasi dan penyimpanan lokal sementara (laporan §5.2, §5.3, §8.3)."""
import asyncio
import csv
import io
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import app.integrations as integ
from app.config import BACKEND_DIR, Settings
from app.agents import OPT_OUT_LINE
from app.main import build_state

HEADER = "crm_id,name,email,company,domain,title_hint,permission_status,permission_ref\n"


@pytest.fixture(autouse=True)
def fast_sim(monkeypatch):
    monkeypatch.setattr(integ.random, "uniform", lambda a, b: 0.01)


ROWS = list(csv.DictReader(open(BACKEND_DIR / "data" / "leads_fiktif.csv", encoding="utf-8")))
EMAILS = [r["email"] for r in ROWS]


def find(pred, nth=0):
    return [i for i, r in enumerate(ROWS) if pred(r)][nth]


SINTA = find(lambda r: r["name"] == "Sinta Pramesti")
DENIED = find(lambda r: r["permission_status"] == "denied")
INVALID = find(lambda r: "@" not in r["email"])
NO_DOMAIN = find(lambda r: not r["domain"] and r["permission_status"] == "granted" and "@" in r["email"])
DUP_A = find(lambda r: EMAILS.count(r["email"]) == 2)
DUP_B = find(lambda r: EMAILS.count(r["email"]) == 2, 1)
NORMAL = [i for i, r in enumerate(ROWS) if r["domain"] and r["permission_status"] == "granted" and "@" in r["email"]
          and EMAILS.count(r["email"]) == 1 and r["name"] != "Sinta Pramesti"][:3]


def sample_rows(indices):
    rows = ROWS
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=rows[0].keys())
    w.writeheader()
    for i in indices:
        w.writerow(rows[i])
    return out.getvalue(), [rows[i] for i in indices]


def settings(tmp_path, **kw):
    base = dict(simulate_integrations=True, data_backend="local", local_store_path=tmp_path / "db.json",
                gmail_send_enabled=True, gmail_allowlist=["@kuliner-nusantara.example"], send_interval_seconds=0,
                runtime_a_workers=2, runtime_b_workers=1)
    base.update(kw)
    return Settings(**base)


async def wait_decided(st, campaign_id, timeout=20):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        tasks = st.db.all("Tasks", campaign_id=campaign_id)
        if tasks and all(t["status"] in {"DONE", "WAITING_REVIEW", "FAILED"} for t in tasks):
            return tasks
        await asyncio.sleep(0.05)
    raise AssertionError(f"task belum selesai: {[(t['task_id'], t['status'], t['stage']) for t in st.db.all('Tasks')]}")


def new_campaign(st, count, schedule=None, personalization="per_lead"):
    return st.orch.create_campaign({
        "name": "Uji", "goal": "Undang demo otomasi laporan", "offer": "Solusi merangkum laporan antar-gerai",
        "cta": "Bersedia demo singkat minggu depan?", "personalization": personalization, "count": count,
        "timezone": "Asia/Jakarta", "sender_name": "Tim Penjualan",
        "schedule": schedule or (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()})


def test_alur_lengkap_keputusan_approval_dan_kirim_tanpa_duplikasi(tmp_path):
    # count=5 memotong baris ke-6; DUP_A menjadi lead normal di luar allowlist
    csv_text, rows = sample_rows([SINTA, DENIED, INVALID, NO_DOMAIN, DUP_A, DUP_B])

    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c = new_campaign(st, 5)
            imported = st.orch.import_leads(c["campaign_id"], csv_text)
            assert imported["added"] == 5  # jumlah lead dibatasi count, tanpa penggantian diam-diam
            st.orch.run_campaign(c["campaign_id"])
            await wait_decided(st, c["campaign_id"])
            leads = {l["name"]: l for l in st.db.all("Leads", campaign_id=c["campaign_id"])}
            assert leads[rows[1]["name"]]["decision"] == "BLOCK"          # tanpa izin
            assert leads[rows[2]["name"]]["decision"] == "BLOCK"          # email invalid
            assert leads[rows[3]["name"]]["stage"] == "identity_review"   # nama ambigu tidak ditebak
            sinta = leads["Sinta Pramesti"]
            assert sinta["decision"] == "PASS", sinta["reasons"]
            email = st.db.get("Emails", f"{c['campaign_id']}:occ-1:{sinta['lead_id']}:step1")
            assert email["status"] == "AWAITING_APPROVAL" and len(email["used_fact_ids"]) <= 3
            evidence = [f for f in st.db.all("Evidence", lead_id=sinta["lead_id"]) if f["selected"]]
            assert 0 < len(evidence) <= 3 and all(f["source_url"] and f["retrieved_at"] for f in evidence)

            # approval terikat versi; edit membatalkan approval
            st.orch.approve(email["send_key"], email["draft_version"])
            edited = st.orch.edit_email(email["send_key"], email["subject"], email["body"] + "\nSalam hangat.")
            assert edited["approval_hash"] == "" and edited["status"] == "AWAITING_APPROVAL"
            with pytest.raises(ValueError):
                st.orch.approve(email["send_key"], email["draft_version"])  # versi lama ditolak
            st.orch.approve(email["send_key"], edited["draft_version"])

            await st.scheduler.tick()
            await st.scheduler.tick()
            sent = st.db.get("Emails", email["send_key"])
            assert sent["status"] == "SENT" and sent["gmail_id"].startswith("sim-")
            assert st.usage.calls["gmail"] == 1  # tick kedua tidak mengirim ulang

            # penerima di luar allowlist tidak dikirim
            other = next(e for e in st.db.all("Emails", campaign_id=c["campaign_id"])
                         if e["status"] == "AWAITING_APPROVAL" and e["send_key"] != email["send_key"])
            assert not other["to_email"].endswith("@kuliner-nusantara.example")
            st.orch.approve(other["send_key"], other["draft_version"])
            await st.scheduler.tick()
            assert st.db.get("Emails", other["send_key"])["status"] == "BLOCKED"
            assert st.usage.calls["gmail"] == 1
            await st.db.flush()

    asyncio.run(go())


def test_duplikat_email_diblokir(tmp_path):
    csv_text, rows = sample_rows([DUP_A, DUP_B])
    assert rows[0]["email"] == rows[1]["email"]

    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c = new_campaign(st, 2)
            st.orch.import_leads(c["campaign_id"], csv_text)
            st.orch.run_campaign(c["campaign_id"])
            await wait_decided(st, c["campaign_id"])
            decisions = sorted((l["decision"], [r["code"] for r in l["reasons"]]) for l in st.db.all("Leads"))
            assert any(code == ["duplicate"] for _, code in decisions)

    asyncio.run(go())


def test_jadwal_belum_tiba_dan_pengiriman_nonaktif_tidak_mengirim(tmp_path):
    csv_text, _ = sample_rows([SINTA])

    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path, gmail_send_enabled=False), http)
            await st.db.start(background=False)
            future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            for sched, expect_error in ((future, None), (None, "Pengiriman nonaktif")):
                c = new_campaign(st, 1, schedule=sched)
                st.orch.import_leads(c["campaign_id"], csv_text)
                st.orch.run_campaign(c["campaign_id"])
                await wait_decided(st, c["campaign_id"])
                e = st.db.all("Emails", campaign_id=c["campaign_id"])[0]
                st.orch.approve(e["send_key"], e["draft_version"])
                await st.scheduler.tick()
                e = st.db.get("Emails", e["send_key"])
                assert e["status"] == "APPROVED" and (expect_error is None or expect_error in e["error"])
            assert st.usage.calls["gmail"] == 0

    asyncio.run(go())


def test_migrasi_menaikkan_generation_dan_hasil_lama_ditolak(tmp_path, monkeypatch):
    csv_text, _ = sample_rows([SINTA])
    gate = asyncio.Event()

    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            original = st.clients["apify"].find_people

            async def slow(lead):
                await gate.wait()
                return await original(lead)

            monkeypatch.setattr(st.clients["apify"], "find_people", slow)
            await st.db.start(background=False)
            c = new_campaign(st, 1)
            st.orch.import_leads(c["campaign_id"], csv_text)
            st.orch.run_campaign(c["campaign_id"])
            task_id = st.db.all("Tasks", campaign_id=c["campaign_id"])[0]["task_id"]
            for _ in range(100):
                t = st.db.get("Tasks", task_id)
                if t["status"] == "RUNNING" and t["host"] in {"A", "B"}:
                    break
                await asyncio.sleep(0.02)
            source = t["host"]
            target = "B" if source == "A" else "A"
            record = await st.orch.migrate(task_id, target)
            assert record["generation"] == 2 and record["from"] == source
            assert st.orch._task_current(task_id, 1) is False  # hasil worker lama akan ditolak
            gate.set()
            tasks = await wait_decided(st, c["campaign_id"])
            assert tasks[0]["generation"] == 2 and tasks[0]["status"] == "DONE"
            kinds = [e.get("kind") for e in st.bus.buffer if e["type"] == "migration"]
            assert "ack_stop" in kinds and "migrated" in kinds and "stale_rejected" in kinds

    asyncio.run(go())


def test_runtime_offline_memindahkan_task_dan_contract_net_tercatat(tmp_path, monkeypatch):
    csv_text, _ = sample_rows(NORMAL)
    gate = asyncio.Event()

    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            original = st.clients["apify"].find_people

            async def slow(lead):
                await gate.wait()
                return await original(lead)

            monkeypatch.setattr(st.clients["apify"], "find_people", slow)
            await st.db.start(background=False)
            c = new_campaign(st, 3)
            st.orch.import_leads(c["campaign_id"], csv_text)
            st.orch.run_campaign(c["campaign_id"])
            await asyncio.sleep(0.3)
            on_a = list(st.orch.runtimes["A"].running)
            assert on_a
            result = await st.orch.set_runtime_online("A", False)
            assert result["moved"] == len(on_a) and not st.orch.runtimes["A"].running
            gate.set()
            await wait_decided(st, c["campaign_id"])
            perfs = {e["performative"] for e in st.bus.buffer if e["type"] == "message"}
            assert {"CFP", "PROPOSE", "ACCEPT_PROPOSAL", "INFORM_RESULT", "REQUEST"} <= perfs

    asyncio.run(go())


def test_pemulihan_setelah_restart_menandai_sending_sebagai_sent_unknown(tmp_path):
    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            st.db.upsert("Emails", {"send_key": "k1", "status": "SENDING", "lead_id": "L"})
            await st.db.flush()
            st2 = build_state(settings(tmp_path), http)
            await st2.db.start(background=False)
            result = await st2.orch.recover()
            assert result["sent_unknown"] == 1
            assert st2.db.get("Emails", "k1")["status"] == "SENT_UNKNOWN"
            with pytest.raises(ValueError):
                st2.orch.reconcile("missing", "sent")
            assert st2.orch.reconcile("k1", "not_sent")["status"] == "NOT_SENT"

    asyncio.run(go())


def test_review_identitas_dilanjutkan_setelah_pengguna_memilih_kandidat(tmp_path):
    csv_text, rows = sample_rows([NO_DOMAIN])

    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c = new_campaign(st, 1)
            st.orch.import_leads(c["campaign_id"], csv_text)
            st.orch.run_campaign(c["campaign_id"])
            await wait_decided(st, c["campaign_id"])
            lead = st.db.all("Leads")[0]
            assert lead["stage"] == "identity_review" and len(lead["candidates"]) >= 2
            index = next(i for i, cand in enumerate(lead["candidates"]) if cand["company"] == rows[0]["company"])
            await st.orch.resolve_identity(lead["lead_id"], index)
            await asyncio.sleep(0.1)
            await wait_decided(st, c["campaign_id"])
            lead = st.db.get("Leads", lead["lead_id"])
            assert lead["stage"] == "decided" and lead["identity"]["company"] == rows[0]["company"]

    asyncio.run(go())


def test_draft_gagal_dapat_ditulis_ulang_tanpa_mengulang_enrichment(tmp_path):
    """Writer yang gagal meninggalkan draft kosong; pengguna harus bisa menulis ulang.

    Tulis ulang hanya menjalankan fase core, jadi tidak ada panggilan Apify/Firecrawl tambahan
    dan approval lama batal karena draft_version naik.
    """
    csv_text, _ = sample_rows([NORMAL[0]])
    gagal = {"aktif": True}
    asli = integ.SimLLM.structured

    async def kadang_gagal(self, system, user, schema_name, schema, campaign_id=""):
        if schema_name == "email_draft" and gagal["aktif"]:
            raise integ.IntegrationError("openrouter", "keluaran LLM bukan JSON")
        return await asli(self, system, user, schema_name, schema, campaign_id)

    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c = new_campaign(st, 1)
            st.orch.import_leads(c["campaign_id"], csv_text)
            st.orch.run_campaign(c["campaign_id"])
            await wait_decided(st, c["campaign_id"])

            email = st.db.all("Emails")[0]
            assert email["body"].strip() in ("", OPT_OUT_LINE), "Writer gagal seharusnya tidak menghasilkan isi"
            assert any(r["code"] == "no_draft" for r in email["security_reasons"])
            assert email["draft_version"] == 1
            prep_calls = {n: st.usage.calls[n] for n in ("apify", "firecrawl")}

            gagal["aktif"] = False
            await st.orch.regenerate_draft(email["send_key"])
            await wait_decided(st, c["campaign_id"])

            ditulis = st.db.get("Emails", email["send_key"])
            assert ditulis["body"].strip(), "tulis ulang harus menghasilkan isi email"
            assert ditulis["draft_version"] == 2, "approval lama batal karena versi draft naik"
            assert ditulis["approval_hash"] == ""
            assert not any(r["code"] == "no_draft" for r in ditulis["security_reasons"])
            assert {n: st.usage.calls[n] for n in ("apify", "firecrawl")} == prep_calls, \
                "tulis ulang tidak boleh memanggil enrichment atau riset lagi"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(integ.SimLLM, "structured", kadang_gagal)
        asyncio.run(go())


def test_tulis_ulang_ditolak_untuk_draft_yang_sudah_final(tmp_path):
    csv_text, _ = sample_rows([NORMAL[0]])

    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c = new_campaign(st, 1)
            st.orch.import_leads(c["campaign_id"], csv_text)
            st.orch.run_campaign(c["campaign_id"])
            await wait_decided(st, c["campaign_id"])
            email = st.db.all("Emails")[0]
            st.orch.reject(email["send_key"])
            with pytest.raises(ValueError):
                await st.orch.regenerate_draft(email["send_key"])

    asyncio.run(go())
