"""Mode draf: tanpa GOOGLE_CLIENT_ID/SECRET aplikasi tetap berjalan; keluarannya hanya isi email."""
import asyncio
import email
from email import policy
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import app.integrations as integ
from app.agents import SecurityAgent
from app.config import Settings
from app.main import _eml, build_state


@pytest.fixture(autouse=True)
def fast_sim(monkeypatch):
    monkeypatch.setattr(integ.random, "uniform", lambda a, b: 0.01)


def test_mode_draf_otomatis_bila_client_google_kosong():
    assert Settings().draft_only is True
    assert Settings(google_client_id="id", google_client_secret="s").draft_only is False
    assert Settings(google_client_id="id", google_client_secret="s", delivery_mode="draft").draft_only is True
    assert Settings(delivery_mode="send").draft_only is False


def test_mode_draf_email_opsional_dan_tanpa_peringatan_allowlist():
    sec = SecurityAgent(Settings())
    lead = {"email": "", "permission_status": "granted", "company": "UGM", "name": "Azhari"}
    reasons = sec.check_contact(lead, set(), False)
    assert [(r["level"], r["code"]) for r in reasons] == [("info", "no_email")]
    assert sec.decide(reasons) == "PASS"
    draft = {"subject": "Halo", "body": "Isi", "used_fact_ids": [], "warnings": []}
    codes = {r["code"] for r in sec.check_draft(lead, {"personalization": "segmen"}, draft, [], {})}
    assert "outside_allowlist" not in codes
    # pengaman izin tetap berlaku di mode draf
    assert sec.decide(sec.check_contact({**lead, "permission_status": ""}, set(), False)) == "BLOCK"


def draft_settings(tmp_path):
    return Settings(simulate_integrations=True, delivery_mode="draft", data_backend="local",
                    local_store_path=tmp_path / "db.json", runtime_a_workers=1, runtime_b_workers=1)


def test_alur_mode_draf_finalkan_tanpa_email_tanpa_kirim_dan_bisa_diunduh(tmp_path):
    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(draft_settings(tmp_path), http)
            await st.db.start(background=False)
            assert st.scheduler.blocked_reason().startswith("Mode draf")
            c = st.orch.create_campaign({
                "name": "Draf", "goal": "Undang diskusi riset", "offer": "Platform koordinasi riset",
                "cta": "Bersediakah Bapak berdiskusi?", "personalization": "per_lead", "timezone": "Asia/Jakarta",
                "sender_name": "Tim", "single_recipient": True, "send_now": True})
            lead = st.orch.add_manual_lead(c["campaign_id"], {"name": "Azhari", "description": "Dosen di UGM serta guru besar di sana",
                                                              "permission_granted": True})
            st.orch.run_campaign(c["campaign_id"])
            for _ in range(400):
                tasks = st.db.all("Tasks", campaign_id=c["campaign_id"])
                if tasks and all(t["status"] in {"DONE", "WAITING_REVIEW", "FAILED"} for t in tasks):
                    break
                await asyncio.sleep(0.05)
            e = st.db.get("Emails", f"{c['campaign_id']}:occ-1:{lead['lead_id']}:step1")
            assert e["body"] and e["to_email"] == ""
            assert "no_email" in {r["code"] for r in e["security_reasons"] if r["level"] == "info"}

            final = st.orch.approve(e["send_key"], e["draft_version"], acknowledge_review=True)
            assert final["status"] == "FINAL"
            await st.scheduler.tick()
            assert st.usage.calls["gmail"] == 0
            assert st.db.get("Emails", e["send_key"])["status"] == "FINAL"
            assert st.db.get("Campaigns", c["campaign_id"])["status"] == "COMPLETED"

            msg = email.message_from_bytes(_eml(st.db.get("Emails", e["send_key"]), c), policy=policy.default)
            assert msg["Subject"] == e["subject"] and msg["X-Unsent"] == "1" and msg["To"] is None
            assert "berhenti" in msg.get_content()

            # Draf final masih bisa diedit: kembali menunggu finalisasi dengan versi baru.
            edited = st.orch.edit_email(e["send_key"], e["subject"], e["body"] + "\nSalam hangat.")
            assert edited["status"] in {"AWAITING_APPROVAL", "NEEDS_REVIEW"} and edited["draft_version"] == e["draft_version"] + 1

    asyncio.run(go())


def test_draf_final_dapat_disetujui_untuk_dikirim_setelah_gmail_dikonfigurasi(tmp_path):
    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(draft_settings(tmp_path), http)
            await st.db.start(background=False)
            st.db.upsert("Campaigns", {"campaign_id": "C", "status": "RUNNING", "schedule": datetime.now(timezone.utc).isoformat(),
                                       "max_recipients": 0, "current_occurrence": 1, "cadence": "once", "max_occurrences": 1})
            st.db.upsert("Emails", {"send_key": "C:occ-1:L:step1", "campaign_id": "C", "occurrence_id": "occ-1", "lead_id": "L",
                                    "to_email": "", "subject": "S", "body": "B", "draft_version": 1, "status": "FINAL",
                                    "security_decision": "PASS", "security_reasons": []})
            st.settings.delivery_mode = "send"
            with pytest.raises(ValueError, match="email penerima"):
                st.orch.approve("C:occ-1:L:step1", 1)
            st.db.upsert("Emails", {"send_key": "C:occ-1:L:step1", "to_email": "a@ugm.example"})
            assert st.orch.approve("C:occ-1:L:step1", 1)["status"] == "APPROVED"

    asyncio.run(go())
