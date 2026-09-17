"""Mode satu penerima: campaign hanya boleh mengirim ke satu orang, dijaga di setiap lapisan."""
import asyncio
from datetime import datetime, timezone

import httpx
import pytest

import app.integrations as integ
from app.main import build_state
from tests.test_manual_lead import settings


@pytest.fixture(autouse=True)
def fast_sim(monkeypatch):
    monkeypatch.setattr(integ.random, "uniform", lambda a, b: 0.01)


def single_campaign(st, **extra):
    return st.orch.create_campaign({
        "name": "Kirim ke Azhari", "goal": "Undang diskusi riset", "offer": "Platform koordinasi riset",
        "cta": "Bersediakah Bapak berdiskusi?", "personalization": "per_lead", "count": 50, "cadence": "weekly",
        "timezone": "Asia/Jakarta", "sender_name": "Tim", "single_recipient": True, "send_now": True, **extra})


async def ready_email(st, allow="azhari@ugm.example"):
    c = single_campaign(st)
    lead = st.orch.add_manual_lead(c["campaign_id"], {"name": "Azhari", "description": "Dosen di UGM serta guru besar di sana",
                                                      "email": allow, "permission_granted": True})
    st.orch.run_campaign(c["campaign_id"])
    for _ in range(400):
        tasks = st.db.all("Tasks", campaign_id=c["campaign_id"])
        if tasks and all(t["status"] in {"DONE", "WAITING_REVIEW", "FAILED"} for t in tasks):
            break
        await asyncio.sleep(0.05)
    return c, st.db.get("Emails", f"{c['campaign_id']}:occ-1:{lead['lead_id']}:step1")


def test_mode_satu_penerima_mengunci_jumlah_frekuensi_dan_kirim_segera(tmp_path):
    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c = single_campaign(st)
            assert c["count"] == 1 and c["max_recipients"] == 1 and c["cadence"] == "once"
            assert abs((datetime.fromisoformat(c["schedule"]) - datetime.now(timezone.utc)).total_seconds()) < 60
            st.orch.add_manual_lead(c["campaign_id"], {"name": "Azhari", "description": "Dosen di UGM", "permission_granted": True})
            with pytest.raises(ValueError, match="batas"):
                st.orch.add_manual_lead(c["campaign_id"], {"name": "Budi", "description": "Dosen di UGM", "permission_granted": True})
            normal = st.orch.create_campaign({"name": "x", "goal": "g", "offer": "o", "cta": "c", "personalization": "per_lead",
                                              "count": 5, "timezone": "Asia/Jakarta", "sender_name": "T",
                                              "schedule": "2026-09-21T09:00"})
            assert normal["max_recipients"] == 0 and normal["count"] == 5

    asyncio.run(go())


def test_satu_penerima_terkirim_sekali_dan_penerima_lain_ditolak_di_approval_maupun_scheduler(tmp_path):
    async def go():
        async with httpx.AsyncClient() as http:
            st = build_state(settings(tmp_path), http)
            await st.db.start(background=False)
            c, email = await ready_email(st)
            st.orch.approve(email["send_key"], email["draft_version"], acknowledge_review=True)
            await st.scheduler.tick()
            assert st.db.get("Emails", email["send_key"])["status"] == "SENT"

            # Baris kedua disisipkan di luar alur normal (mis. edit manual Sheets) ke alamat lain.
            other = {**email, "send_key": f"{c['campaign_id']}:occ-1:LAIN:step1", "lead_id": "LAIN",
                     "to_email": "orang.lain@ugm.example", "status": "AWAITING_APPROVAL", "approval_hash": ""}
            st.db.upsert("Emails", other)
            with pytest.raises(ValueError, match="1 penerima"):
                st.orch.approve(other["send_key"], other["draft_version"], acknowledge_review=True)
            assert st.orch.approve_all_pass(c["campaign_id"]) == 0

            # Bahkan bila statusnya dipaksa APPROVED, scheduler tetap menolak.
            from app.orchestrator import approval_hash
            campaign = st.db.get("Campaigns", c["campaign_id"])
            st.db.upsert("Emails", {"send_key": other["send_key"], "status": "APPROVED",
                                    "approval_hash": approval_hash({**other}, campaign)})
            st.settings.gmail_allowlist.append("orang.lain@ugm.example")
            assert st.db.get("Campaigns", c["campaign_id"])["status"] == "COMPLETED"  # selesai setelah 1 kiriman
            await st.scheduler.tick()
            assert st.db.get("Emails", other["send_key"])["status"] == "APPROVED"  # campaign selesai: tidak ada kirim
            st.db.upsert("Campaigns", {"campaign_id": c["campaign_id"], "status": "RUNNING"})  # dipaksa aktif lagi
            await st.scheduler.tick()
            blocked = st.db.get("Emails", other["send_key"])
            assert blocked["status"] == "BLOCKED" and "Batas 1 penerima" in blocked["error"]
            assert st.usage.calls["gmail"] == 1

    asyncio.run(go())
