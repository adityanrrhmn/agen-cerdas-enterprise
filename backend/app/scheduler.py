"""Scheduler + Gmail sender (layanan terprogram, bukan agen; laporan §5.2).

Sebelum kirim: cek kunci kirim, versi approval, suppression, allowlist, dan jadwal.
Status SENDING disimpan ke penyimpanan SEBELUM memanggil Gmail agar crash tidak menyebabkan kirim ganda.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from .agents import now_iso
from .config import Settings
from .integrations import GmailClient, IntegrationError, SendOutcome
from .orchestrator import DELIVERY, EventBus, Orchestrator, approval_hash, recipients

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, settings: Settings, orch: Orchestrator, gmail: GmailClient, bus: EventBus, simulated: bool):
        self.s, self.orch, self.gmail, self.bus, self.simulated = settings, orch, gmail, bus, simulated
        self.db = orch.db
        self._task: asyncio.Task | None = None
        self.last_send = 0.0
        self.last_tick: str | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    def blocked_reason(self) -> str | None:
        if self.s.draft_only:
            why = "DELIVERY_MODE=draft" if self.s.delivery_mode == "draft" else "Google Client ID/Secret belum diisi"
            return f"Mode draf: aplikasi hanya menyusun isi email ({why})"
        if not self.simulated and not self.s.configured("gmail"):
            return f"Gmail belum dikonfigurasi ({', '.join(self.s.missing('gmail'))})"
        if not self.simulated and not (self.gmail.oauth and self.gmail.oauth.status()["connected"]):
            return "Akun Google pengirim belum dihubungkan (tab Koneksi)"
        if not self.s.gmail_send_enabled:
            return "Pengiriman nonaktif (GMAIL_SEND_ENABLED=false)"
        return None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Tick scheduler gagal")
            await asyncio.sleep(5)

    async def tick(self) -> None:
        self.last_tick = now_iso()
        now = datetime.now(timezone.utc)
        for campaign in self.db.all("Campaigns", status="RUNNING"):
            occ = self.orch.occurrence_id(campaign)
            due = [e for e in self.db.all("Emails", campaign_id=campaign["campaign_id"], occurrence_id=occ, status="APPROVED")
                   if datetime.fromisoformat(e["schedule"]) <= now]
            blocked = self.blocked_reason()
            for email in sorted(due, key=lambda e: e["lead_id"]):
                if blocked:
                    if email.get("error") != blocked:
                        self.db.upsert("Emails", {"send_key": email["send_key"], "error": blocked})
                    continue
                if time.monotonic() - self.last_send < self.s.send_interval_seconds:
                    break  # throttle: jendela kirim bertahap
                await self._send_one(email, campaign)
            self.orch.maybe_next_occurrence(campaign["campaign_id"])

    async def _send_one(self, email: dict, campaign: dict) -> None:
        key = email["send_key"]
        current = self.db.get("Emails", key)
        if current["status"] != "APPROVED":  # kunci kirim: sudah diproses
            return
        if current["approval_hash"] != approval_hash(current, campaign):
            self._finish(key, "NEEDS_REAPPROVAL", error="Draft atau konfigurasi berubah setelah approval")
            return
        to = current["to_email"].lower()
        sender = self.gmail.oauth.sender_email if self.gmail.oauth else ""
        if campaign.get("sender_email") and sender and sender.lower() != campaign["sender_email"].lower():
            self._finish(key, "NEEDS_REAPPROVAL", error=f"Akun pengirim berubah menjadi {sender}; buat campaign ulang")
            return
        if to in {r["email"].lower() for r in self.db.all("Suppression")}:
            self._finish(key, "BLOCKED", error="Masuk suppression sebelum kirim")
            return
        if not self.s.recipient_allowed(to):
            self._finish(key, "BLOCKED", error="Penerima di luar GMAIL_ALLOWLIST")
            return
        limit = campaign.get("max_recipients") or 0
        delivered = recipients(self.db, campaign["campaign_id"], DELIVERY, exclude_key=key)
        if limit and to not in delivered and len(delivered) >= limit:
            self._finish(key, "BLOCKED", error=f"Batas {limit} penerima campaign sudah tercapai")
            return
        self.db.upsert("Emails", {"send_key": key, "status": "SENDING", "updated_at": now_iso()})
        try:
            await self.db.flush()
        except Exception as exc:
            self.db.upsert("Emails", {"send_key": key, "status": "APPROVED", "error": f"Status kirim gagal disimpan: {exc}"})
            return
        self.last_send = time.monotonic()
        try:
            outcome, gmail_id, error = await self.gmail.send(campaign["sender_name"], to, current["subject"], current["body"])
        except IntegrationError as exc:
            outcome, gmail_id, error = SendOutcome.FAILED, "", str(exc)
        self._finish(key, outcome, gmail_id=gmail_id, error=error)
        await self.db.flush()

    def _finish(self, key: str, status: str, gmail_id: str = "", error: str = "") -> None:
        row = self.db.upsert("Emails", {"send_key": key, "status": status, "gmail_id": gmail_id, "error": error,
                                        "updated_at": now_iso()})
        label = {"SENT": "diterima Gmail API (bukan bukti dibaca)", "SENT_UNKNOWN": "hasil tidak pasti, perlu rekonsiliasi"}.get(status, error)
        self.bus.emit("send", f"{row['lead_id']} → {status}: {label}", send_key=key, status=status, lead_id=row["lead_id"])
        self.orch.audit("sender", f"{key} {status} {error}".strip())
