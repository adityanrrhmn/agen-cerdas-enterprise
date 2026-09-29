"""Regresi untuk 11 temuan bug test (BUG-01 … BUG-11). Tiap tes gagal pada kode sebelum perbaikan."""
import asyncio
import csv
import io
import json

import httpx
import pytest

from app.main import app, build_state
from app.orchestrator import DELIVERY, approval_hash
from tests.test_orchestrator import DUP_A, DUP_B, NORMAL, new_campaign, sample_rows, wait_decided
from tests.test_orchestrator import settings as base_settings

import app.integrations as integ


@pytest.fixture(autouse=True)
def fast_sim(monkeypatch):
    monkeypatch.setattr(integ.random, "uniform", lambda a, b: 0.01)


def settings(tmp_path):
    return base_settings(tmp_path, gmail_allowlist=["@properti-jaya.example", "@logistik-harmoni.example",
                                                    "@kuliner-cemerlang.example"])


def run(coro_fn):
    async def go():
        async with httpx.AsyncClient() as http:
            await coro_fn(http)
    asyncio.run(go())


async def decided(st, count, indices):
    csv_text, rows = sample_rows(indices)
    c = new_campaign(st, count)
    st.orch.import_leads(c["campaign_id"], csv_text)
    st.orch.run_campaign(c["campaign_id"])
    await wait_decided(st, c["campaign_id"])
    return c, st.db.all("Leads", campaign_id=c["campaign_id"])


def first_email(st, c, lead):
    return st.db.get("Emails", f"{c['campaign_id']}:occ-1:{lead['lead_id']}:step1")


def force_approved(st, key):
    """Setujui langsung dengan hash yang sah (mengabaikan pemeriksaan approval) untuk menguji lapisan scheduler."""
    email = st.db.get("Emails", key)
    campaign = st.db.get("Campaigns", email["campaign_id"])
    return st.db.upsert("Emails", {"send_key": key, "status": "APPROVED", "approval_hash": approval_hash(email, campaign)})


# ------------------------------------------------------------------ BUG-01
def test_bug01_alamat_lead_lain_ditolak_dan_pengaman_scheduler_memblokir_kembaran(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        c, leads = await decided(st, 2, NORMAL[:2])
        a, b = sorted(leads, key=lambda x: x["lead_id"])
        with pytest.raises(ValueError, match="sudah dipakai lead lain"):
            st.orch.set_lead_email(b["lead_id"], a["email"].upper())  # huruf besar/kecil tidak menipu
        assert st.db.get("Leads", b["lead_id"])["email"] == b["email"]

        # Baris email disisipkan di luar alur normal: alamat sama, lead berbeda, kejadian sama.
        ea, eb = first_email(st, c, a), first_email(st, c, b)
        st.db.upsert("Emails", {"send_key": eb["send_key"], "to_email": ea["to_email"]})
        force_approved(st, ea["send_key"])
        await st.scheduler.tick()
        assert st.db.get("Emails", ea["send_key"])["status"] == "SENT"
        force_approved(st, eb["send_key"])
        await st.scheduler.tick()
        blocked = st.db.get("Emails", eb["send_key"])
        assert blocked["status"] == "BLOCKED" and "sudah menerima email lain" in blocked["error"]

    run(go)


def test_bug01_edit_ke_alamat_yang_sama_dihitung_duplikat_dari_data(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        c, leads = await decided(st, 2, NORMAL[:2])
        a, b = sorted(leads, key=lambda x: x["lead_id"])
        # Kondisi yang bisa muncul dari suntingan manual di Sheets: dua lead beralamat sama.
        st.db.upsert("Leads", {"lead_id": b["lead_id"], "email": a["email"]})
        eb = first_email(st, c, b)
        edited = st.orch.edit_email(eb["send_key"], eb["subject"], eb["body"])
        assert edited["security_decision"] == "BLOCK"
        assert "duplicate" in [r["code"] for r in edited["security_reasons"]]

    run(go)


# ------------------------------------------------------------------ BUG-02
def test_bug02_duplikat_tetap_terdeteksi_tanpa_flag_memori(tmp_path):
    csv_text, rows = sample_rows([DUP_A, DUP_B])

    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        c = new_campaign(st, 2)
        st.orch.import_leads(c["campaign_id"], csv_text)
        first, second = sorted(st.db.all("Leads", campaign_id=c["campaign_id"]), key=lambda x: x["lead_id"])
        assert not st.orch._is_duplicate(first) and st.orch._is_duplicate(second)
        # Jalur pemulihan/relaunch memanggil _validate tanpa flag duplikat.
        task = st.orch._update_task(f"T-{second['lead_id']}-occ-1", campaign_id=c["campaign_id"], lead_id=second["lead_id"],
                                    occurrence_id="occ-1", stage="queued", status="QUEUED", agent_id="orchestrator", host="",
                                    payload_ref="", checkpoint={"done": []}, generation=1, lease_until=None, retry=0, error="",
                                    started_at="")
        assert st.orch._validate(task, 1, False) is False
        assert first_email(st, c, second)["status"] == "BLOCKED"

    run(go)


# ------------------------------------------------------------------ BUG-03
def test_bug03_subjek_dengan_crlf_ditolak_dan_eml_tidak_500(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        c, leads = await decided(st, 1, NORMAL[:1])
        e = first_email(st, c, leads[0])
        with pytest.raises(ValueError, match="baris baru"):
            st.orch.edit_email(e["send_key"], "Halo\r\nBcc: x@y.example", "Isi")
        # Data lama/tersunting manual yang sudah memuat CR/LF: unduh .eml tetap berhasil.
        st.db.upsert("Emails", {"send_key": e["send_key"], "subject": "Halo\r\nBcc: x@y.example"})
        app.state.s = st
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
            r = await api.get(f"/api/emails/{e['send_key']}/eml")
        assert r.status_code == 200
        header_lines = r.content.split(b"\n\n")[0].splitlines()
        assert not any(line.lower().startswith(b"bcc:") for line in header_lines)  # tidak ada header baru yang disusupkan

    run(go)


def test_bug03_scheduler_tidak_menggantung_di_sending(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        c, leads = await decided(st, 2, NORMAL[:2])
        a, b = sorted(leads, key=lambda x: x["lead_id"])
        ea, eb = first_email(st, c, a), first_email(st, c, b)

        # (1) subjek CR/LF lolos dari validasi (data tersunting manual): FAILED, bukan SENDING.
        st.db.upsert("Emails", {"send_key": ea["send_key"], "subject": "Halo\r\nBcc: x@y.example"})
        force_approved(st, ea["send_key"])
        await st.scheduler.tick()
        got = st.db.get("Emails", ea["send_key"])
        assert got["status"] == "FAILED" and "tidak valid" in got["error"]

        # (2) galat tak terduga sesudah SENDING disimpan: SENT_UNKNOWN (tidak kirim ulang), bukan SENDING.
        async def boom(*args, **kwargs):
            raise RuntimeError("gangguan tak terduga")
        st.scheduler.gmail.send = boom
        force_approved(st, eb["send_key"])
        await st.scheduler.tick()
        got = st.db.get("Emails", eb["send_key"])
        assert got["status"] == "SENT_UNKNOWN" and "gangguan tak terduga" in got["error"]
        assert got["status"] not in {"SENDING"} and "SENDING" in DELIVERY  # SENT_UNKNOWN tetap menghitung kuota

    run(go)


# ------------------------------------------------------------------ BUG-04
def test_bug04_ekspor_csv_menetralkan_rumus(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        c = new_campaign(st, 3)
        for name in ('=HYPERLINK("http://evil.example","klik")', "+cmd|' /C calc'!A0", "@SUM(1+1)"):
            st.orch.add_manual_lead(c["campaign_id"], {"name": name, "description": "Dosen di UGM", "permission_granted": True})
        app.state.s = st
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
            r = await api.get(f"/api/campaigns/{c['campaign_id']}/export.csv")
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))[1:]
        names = [row[1] for row in rows]
        assert all(n.startswith("'") for n in names) and len(names) == 3

    run(go)


# ------------------------------------------------------------------ BUG-05
def test_bug05_batas_panjang_input(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        app.state.s = st
        base = {"name": "x", "goal": "g", "offer": "o", "cta": "c", "personalization": "per_lead", "count": 2,
                "timezone": "Asia/Jakarta", "sender_name": "T", "schedule": "2026-10-01T09:00"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
            r = await api.post("/api/campaigns", json={**base, "name": "N" * 100_000})
            assert r.status_code == 422 and isinstance(r.json()["detail"], str)  # string: bisa ditampilkan UI
            c = (await api.post("/api/campaigns", json=base)).json()
            r = await api.post(f"/api/campaigns/{c['campaign_id']}/leads",
                               json={"name": "A" * 200_000, "description": "Dosen di UGM", "permission_granted": True})
            assert r.status_code == 422
            r = await api.post(f"/api/campaigns/{c['campaign_id']}/leads",
                               json={"name": "Azhari", "description": "D" * 300_000, "permission_granted": True})
            assert r.status_code == 422
            ok = await api.post(f"/api/campaigns/{c['campaign_id']}/leads",
                                json={"name": "Azhari", "description": "Dosen di UGM", "permission_granted": True})
            assert ok.status_code == 200
        c2 = new_campaign(st, 3)
        header = "name,company\n"
        big = header + f"Baris Besar,{'X' * 6000}\nBaris Wajar,PT Contoh\n"
        res = st.orch.import_leads(c2["campaign_id"], big)
        assert res["added"] == 1 and "baris 2" in res["skipped"][0]

    run(go)


def test_bug05_edit_draf_terlalu_panjang_ditolak(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        c, leads = await decided(st, 1, NORMAL[:1])
        e = first_email(st, c, leads[0])
        with pytest.raises(ValueError, match="Subjek maksimal"):
            st.orch.edit_email(e["send_key"], "S" * 500, "isi")
        with pytest.raises(ValueError, match="Isi email maksimal"):
            st.orch.edit_email(e["send_key"], "Halo", "B" * 30_000)

    run(go)


# ------------------------------------------------------------------ BUG-06
def test_bug06_csv_rusak_dibalas_400_bukan_500(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        app.state.s = st
        c = new_campaign(st, 5)
        cid = c["campaign_id"]
        huge = "name,company\nBaris Baik,PT Baik\nBaris Besar," + "X" * 1_000_000 + "\n"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
            r = await api.post(f"/api/campaigns/{cid}/leads/csv", files={"file": ("l.csv", huge.encode(), "text/csv")})
            assert r.status_code == 400 and "CSV tidak dapat dibaca" in r.json()["detail"]
            assert st.db.all("Leads", campaign_id=cid) == []  # impor bersifat atomik: tidak ada yang separuh masuk
            semi = "name;company\nSinta;PT Satu\nBudi;PT Dua\n"  # Excel regional Indonesia memakai titik koma
            r = await api.post(f"/api/campaigns/{cid}/leads/csv", files={"file": ("l.csv", semi.encode(), "text/csv")})
            assert r.status_code == 200 and r.json()["added"] == 2

    run(go)


# ------------------------------------------------------------------ BUG-07
def test_bug07_permintaan_tulis_baru_dibalas_setelah_data_tersimpan(tmp_path):
    async def go(http):
        cfg = settings(tmp_path)
        st = build_state(cfg, http)
        await st.db.start(background=False)  # tanpa loop flush berkala: hanya middleware yang bisa menulis
        app.state.s = st
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
            r = await api.post("/api/campaigns", json={
                "name": "Simpan segera", "goal": "g", "offer": "o", "cta": "c", "count": 1, "sender_name": "T",
                "schedule": "2026-10-01T09:00"})
        assert r.status_code == 200
        on_disk = json.loads((tmp_path / "db.json").read_text(encoding="utf-8"))
        assert r.json()["campaign_id"] in json.dumps(on_disk)

    run(go)


# ------------------------------------------------------------------ BUG-08
@pytest.mark.parametrize("patch,status,pesan", [
    ({"count": 0}, 422, "count"), ({"count": -5}, 422, "count"), ({"count": 1_000_000_000}, 422, "count"),
    ({"budget": -10}, 422, "budget"), ({"max_occurrences": -3}, 422, "max_occurrences"),
    ({"name": "   "}, 400, "Wajib diisi"), ({"timezone": "Bukan/Zona"}, 400, "Zona waktu"),
    ({"schedule": "besok pagi"}, 400, ""),
])
def test_bug08_validasi_campaign_di_api(tmp_path, patch, status, pesan):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        app.state.s = st
        base = {"name": "x", "goal": "g", "offer": "o", "cta": "c", "personalization": "per_lead", "count": 2,
                "timezone": "Asia/Jakarta", "sender_name": "T", "schedule": "2026-10-01T09:00"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
            r = await api.post("/api/campaigns", json={**base, **patch})
        assert r.status_code == status, r.text
        assert pesan in r.json()["detail"]
        assert st.db.all("Campaigns") == []

    run(go)


# ------------------------------------------------------------------ BUG-09
def test_bug09_draf_tanpa_isi_tidak_lolos_dan_tidak_bisa_disetujui(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        c, leads = await decided(st, 1, NORMAL[:1])
        e = first_email(st, c, leads[0])
        empty = st.orch.edit_email(e["send_key"], "Halo", "")
        codes = [r["code"] for r in empty["security_reasons"]]
        assert empty["security_decision"] == "REVIEW" and "empty_draft" in codes  # bukan PASS
        with pytest.raises(ValueError, match="kosong"):
            st.orch.approve(e["send_key"], empty["draft_version"], acknowledge_review=True)
        blank_subject = st.orch.edit_email(e["send_key"], "   ", "Isi yang sungguhan")
        assert blank_subject["security_decision"] == "REVIEW"
        with pytest.raises(ValueError, match="kosong"):
            st.orch.approve(e["send_key"], blank_subject["draft_version"], acknowledge_review=True)

    run(go)


# ------------------------------------------------------------------ BUG-11
def test_bug11_daftar_kirim_campaign_tidak_ada_404(tmp_path):
    async def go(http):
        st = build_state(settings(tmp_path), http)
        await st.db.start(background=False)
        app.state.s = st
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
            assert (await api.get("/api/campaigns/NOPE/emails")).status_code == 404
            c = new_campaign(st, 1)
            r = await api.get(f"/api/campaigns/{c['campaign_id']}/emails")
            assert r.status_code == 200 and r.json() == []

    run(go)
