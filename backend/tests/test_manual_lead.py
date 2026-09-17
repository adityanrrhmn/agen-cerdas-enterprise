"""Lead manual dari dashboard: nama lengkap + deskripsi (contoh: Azhari, dosen dan guru besar di UGM)."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import app.integrations as integ
from app.agents import ProfileHintAgent, ResearchAgent, SecurityAgent, crm_facts, effective_lead
from app.config import Settings
from app.integrations import LLMResult
from app.main import build_state

AZHARI = {"name": "Azhari", "description": "Dosen di UGM serta guru besar di sana"}
HINTS = {"organization": "Universitas Gadjah Mada", "organization_aliases": ["Universitas Gadjah Mada", "UGM"],
         "role": "Dosen, Guru Besar", "location": ""}


@pytest.fixture(autouse=True)
def fast_sim(monkeypatch):
    monkeypatch.setattr(integ.random, "uniform", lambda a, b: 0.01)


class FakeLLM:
    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    async def structured(self, system, user, name, schema, campaign_id=""):
        self.calls.append((name, system, user))
        return LLMResult(self.outputs.pop(0), 10, 5, 0.0, "fake")


def test_petunjuk_deskripsi_menambah_nama_lengkap_dan_singkatan_instansi():
    llm = FakeLLM({"organization": "Universitas Gadjah Mada", "organization_aliases": ["UGM"], "role": "Dosen, Guru Besar", "location": ""})
    hints = asyncio.run(ProfileHintAgent(llm).run({"lead_id": "L1", **AZHARI}, "C"))
    assert hints["organization_aliases"] == ["Universitas Gadjah Mada", "UGM"]
    lead = effective_lead({"lead_id": "L1", "company": "", "title_hint": "", **AZHARI, "hints": hints})
    assert lead["company"] == "Universitas Gadjah Mada" and lead["title_hint"] == "Dosen, Guru Besar"


def test_deskripsi_pengguna_menjadi_fakta_tetapi_hasil_llm_tidak():
    facts = crm_facts({"lead_id": "L1", "company": "", "title_hint": "", **AZHARI, "hints": HINTS})
    assert [(f.field, f.source_type) for f in facts] == [("description", "crm")]
    assert facts[0].source_url == "input://pengguna/L1"


class Pages:
    def __init__(self):
        self.query = None

    async def search(self, query):
        self.query = query
        return [
            {"url": "https://ugm.example/prof-azhari", "title": "Prof. Azhari", "description": "",
             "markdown": "Prof. Azhari adalah guru besar Fakultas Teknik Universitas Gadjah Mada bidang sistem cerdas."},
            {"url": "https://kampus-lain.example/azhari", "title": "Azhari", "description": "",
             "markdown": "Dr. Azhari mengajar di Universitas Sumatera Utara."},
            {"url": "https://ugm.example/berita", "title": "Berita UGM", "description": "",
             "markdown": "UGM membuka program baru tanpa menyebut nama dosen tertentu."},
        ]


def test_riset_orang_hanya_memakai_halaman_yang_menyebut_nama_dan_instansi():
    pages = Pages()
    llm = FakeLLM({"facts": [{"field": "keahlian", "value": "Guru besar bidang sistem cerdas di Fakultas Teknik UGM",
                              "source_url": "https://ugm.example/prof-azhari",
                              "quote": "guru besar Fakultas Teknik Universitas Gadjah Mada bidang sistem cerdas"}]})
    lead = effective_lead({"lead_id": "L1", "company": "", "title_hint": "", "domain": "", **AZHARI, "hints": HINTS})
    out = asyncio.run(ResearchAgent(Settings(), pages, llm).run(lead, {"goal": "undang demo", "campaign_id": "C"}))
    assert pages.query == '"Azhari" "Universitas Gadjah Mada"'
    name, system, user = llm.calls[0]
    assert "PROFESIONAL" in system and "https://kampus-lain.example" not in user and "https://ugm.example/berita" not in user
    assert out["irrelevant_pages"] == 2 and [f.value for f in out["facts"]] == ["Guru besar bidang sistem cerdas di Fakultas Teknik UGM"]


def test_email_kosong_menjadi_review_bukan_blokir_dan_email_salah_tetap_blokir():
    sec = SecurityAgent(Settings())
    lead = {"email": "", "permission_status": "granted"}
    assert sec.decide(sec.check_contact(lead, set(), False)) == "REVIEW"
    assert sec.decide(sec.check_contact({**lead, "email": "azhari#ugm"}, set(), False)) == "BLOCK"


def settings(tmp_path):
    return Settings(simulate_integrations=True, data_backend="local", local_store_path=tmp_path / "db.json",
                    gmail_send_enabled=True, gmail_allowlist=["azhari@ugm.example"], send_interval_seconds=0,
                    runtime_a_workers=1, runtime_b_workers=1)


def campaign(st, count=2):
    return st.orch.create_campaign({
        "name": "Uji manual", "goal": "Undang diskusi riset kolaborasi", "offer": "Platform koordinasi riset",
        "cta": "Bersediakah Bapak berdiskusi singkat?", "personalization": "per_lead", "count": count,
        "timezone": "Asia/Jakarta", "sender_name": "Tim", "schedule": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()})


def test_validasi_form_lead_manual(tmp_path):
    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c = campaign(st, count=1)
            with pytest.raises(ValueError, match="Nama"):
                st.orch.add_manual_lead(c["campaign_id"], {"name": "", "description": "dosen"})
            with pytest.raises(ValueError, match="deskripsi"):
                st.orch.add_manual_lead(c["campaign_id"], {"name": "Azhari", "description": ""})
            with pytest.raises(ValueError, match="email"):
                st.orch.add_manual_lead(c["campaign_id"], {**AZHARI, "email": "azhari#ugm"})
            lead = st.orch.add_manual_lead(c["campaign_id"], {**AZHARI, "permission_granted": True, "permission_ref": "kartu nama seminar"})
            assert lead["permission_status"] == "granted" and lead["email"] == "" and lead["description"] == AZHARI["description"]
            with pytest.raises(ValueError, match="batas"):
                st.orch.add_manual_lead(c["campaign_id"], {"name": "Budi", "description": "Manajer di PT Contoh"})

    asyncio.run(go())


def test_alur_lead_manual_tanpa_email_lalu_email_diisi_dan_disetujui(tmp_path):
    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c = campaign(st)
            lead = st.orch.add_manual_lead(c["campaign_id"], {**AZHARI, "permission_granted": True})
            st.orch.run_campaign(c["campaign_id"])
            for _ in range(400):
                tasks = st.db.all("Tasks", campaign_id=c["campaign_id"])
                if tasks and all(t["status"] in {"DONE", "WAITING_REVIEW", "FAILED"} for t in tasks):
                    break
                await asyncio.sleep(0.05)
            lead = st.db.get("Leads", lead["lead_id"])
            assert lead["hints"]["organization"] == "UGM"  # simulasi: instansi diambil dari "di UGM"
            codes = {r["code"] for r in lead["reasons"]}
            assert lead["decision"] == "REVIEW" and "no_email" in codes
            evidence = st.db.all("Evidence", lead_id=lead["lead_id"])
            assert any(f["field"] == "description" and f["selected"] for f in evidence)
            email = st.db.get("Emails", f"{c['campaign_id']}:occ-1:{lead['lead_id']}:step1")
            assert email["body"] and email["to_email"] == ""
            with pytest.raises(ValueError, match="email penerima"):
                st.orch.approve(email["send_key"], email["draft_version"], acknowledge_review=True)

            st.orch.set_lead_email(lead["lead_id"], "Azhari@UGM.example")
            email = st.db.get("Emails", email["send_key"])
            assert email["to_email"] == "azhari@ugm.example" and email["draft_version"] == 2
            assert "no_email" not in {r["code"] for r in email["security_reasons"]}
            st.orch.approve(email["send_key"], email["draft_version"], acknowledge_review=True)
            await st.scheduler.tick()
            assert st.db.get("Emails", email["send_key"])["status"] == "SENT"

    asyncio.run(go())
