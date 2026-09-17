"""Orchestrator/Broker (laporan §5.1–5.3).

- State machine per lead: validate → enrichment → research → write → security → approval.
- Enrichment + riset adalah fase mobile-capable yang dijalankan di runtime A/B hasil negosiasi Contract Net.
- Penulisan + pemeriksaan berjalan statis di runtime `core`.
- Migrasi: hentikan worker lama (ACK stop), simpan checkpoint, naikkan generation, lanjutkan di runtime tujuan.
  Hasil dengan generation lama ditolak saat commit.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import itertools
import json
import logging
import time
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .agents import (EMAIL_RE, OPT_OUT_LINE, EnrichmentAgent, Fact, ProfileHintAgent, ResearchAgent, SecurityAgent,
                     WriterAgent, crm_facts, effective_lead,
                     now_iso, reason, select_facts)
from .config import Settings
from .integrations import IntegrationError, Usage
from .store import DataGateway

log = logging.getLogger(__name__)

FINAL_EMAIL = {"SENT", "SENT_UNKNOWN", "FAILED", "REJECTED", "BLOCKED", "NOT_SENT"}
# Status yang "memakai" kuota penerima: sudah disetujui, sedang/sudah dikirim, atau hasil kirim tidak pasti.
COMMITTED = {"APPROVED", "SENDING", "SENT", "SENT_UNKNOWN"}
DELIVERY = {"SENDING", "SENT", "SENT_UNKNOWN"}
CADENCE_DAYS = {"weekly": 7, "monthly": 30}
REQUIRED_CAMPAIGN = ["name", "goal", "offer", "cta", "personalization", "sender_name", "schedule", "timezone", "count"]


def sha(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def config_hash(c: dict[str, Any]) -> str:
    return sha({k: c.get(k) for k in ("goal", "offer", "cta", "personalization", "sender_name", "sender_email",
                                      "schedule", "timezone", "cadence", "template_id", "max_recipients")})


def recipients(db: DataGateway, campaign_id: str, statuses: set[str], exclude_key: str = "") -> set[str]:
    """Alamat unik di campaign (semua kejadian) yang statusnya termasuk `statuses`."""
    return {(e["to_email"] or "").lower() for e in db.all("Emails", campaign_id=campaign_id)
            if e["status"] in statuses and e["send_key"] != exclude_key and e["to_email"]}


def approval_hash(email: dict[str, Any], campaign: dict[str, Any]) -> str:
    return sha({"to": email["to_email"], "subject": email["subject"], "body": email["body"],
                "v": email["draft_version"], "cfg": config_hash(campaign)})


# ------------------------------------------------------------------ event bus
class EventBus:
    def __init__(self, size: int = 600):
        self.buffer: deque[dict[str, Any]] = deque(maxlen=size)
        self.subscribers: set[asyncio.Queue] = set()
        self.counter = itertools.count(1)
        self.totals: Counter = Counter()

    def emit(self, type_: str, text: str, **data: Any) -> dict[str, Any]:
        event = {"id": next(self.counter), "ts": now_iso(), "type": type_, "text": text, **data}
        self.buffer.append(event)
        self.totals[type_] += 1
        if type_ == "message":
            self.totals[f"perf:{data.get('performative')}"] += 1
        for q in list(self.subscribers):
            if q.qsize() < 1000:
                q.put_nowait(event)
        return event

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)


@dataclass
class Runtime:
    name: str
    capacity: int
    online: bool = True
    semaphore: asyncio.Semaphore = field(init=False)
    running: dict[str, asyncio.Task] = field(default_factory=dict)
    active: set[str] = field(default_factory=set)
    durations: deque = field(default_factory=lambda: deque(maxlen=30))
    completed: int = 0

    def __post_init__(self):
        self.semaphore = asyncio.Semaphore(self.capacity)

    def avg_duration(self) -> float:
        return sum(self.durations) / len(self.durations) if self.durations else 5.0

    def estimate(self) -> float:
        waiting = max(0, len(self.running) - len(self.active))
        load = len(self.active) + waiting
        return round(self.avg_duration() * (1 + load / self.capacity), 2)


class Orchestrator:
    def __init__(self, settings: Settings, gateway: DataGateway, usage: Usage, bus: EventBus,
                 enrichment: EnrichmentAgent, research: ResearchAgent, writer: WriterAgent, security: SecurityAgent,
                 hints: ProfileHintAgent | None = None):
        self.s, self.db, self.usage, self.bus = settings, gateway, usage, bus
        self.enrichment, self.research, self.writer, self.security = enrichment, research, writer, security
        self.hints = hints
        self.runtimes = {"A": Runtime("A", settings.runtime_a_workers), "B": Runtime("B", settings.runtime_b_workers)}
        self.core = asyncio.Semaphore(settings.runtime_a_workers + settings.runtime_b_workers)
        self.lead_tasks: dict[str, asyncio.Task] = {}
        self.dispatchers: dict[str, asyncio.Task] = {}
        self.migrations: deque = deque(maxlen=50)
        self.prep_durations: deque = deque(maxlen=500)

    # ------------------------------------------------------------ util
    def audit(self, actor: str, summary: str, task_id: str = "") -> None:
        self.db.upsert("Audit", {"event_id": f"E-{uuid.uuid4().hex[:12]}", "task_id": task_id, "actor": actor,
                                 "timestamp": now_iso(), "change_summary": summary[:500]})

    def message(self, performative: str, sender: str, receiver: str, task: dict[str, Any], text: str, **extra) -> None:
        self.bus.emit("message", text, performative=performative, sender=sender, receiver=receiver,
                      message_id=f"M-{uuid.uuid4().hex[:10]}", conversation_id=f"C-{task['task_id']}",
                      campaign_id=task["campaign_id"], task_id=task["task_id"], lead_id=task["lead_id"],
                      payload_ref=f"Tasks/{task['task_id']}", retry_count=task.get("retry") or 0,
                      lease_generation=task.get("generation") or 0, **extra)

    async def _gate(self, campaign_id: str) -> None:
        while (self.db.get("Campaigns", campaign_id) or {}).get("status") == "PAUSED":
            await asyncio.sleep(1)

    def _task_current(self, task_id: str, generation: int) -> bool:
        task = self.db.get("Tasks", task_id)
        if task and task["generation"] == generation:
            return True
        self.bus.emit("migration", f"Hasil {task_id} generation {generation} ditolak (generation aktif {task and task['generation']})",
                      task_id=task_id, kind="stale_rejected")
        self.audit("orchestrator", f"hasil generation lama {generation} ditolak", task_id)
        return False

    def _update_task(self, task_id: str, **fields: Any) -> dict[str, Any]:
        fields["updated_at"] = now_iso()
        return self.db.upsert("Tasks", {"task_id": task_id, **fields})

    # ------------------------------------------------------------ campaign & leads
    def create_campaign(self, data: dict[str, Any]) -> dict[str, Any]:
        data = dict(data)
        single = bool(data.get("single_recipient"))
        if single:  # mode satu penerima: dikunci di backend, bukan hanya di UI
            data["count"], data["cadence"] = 1, "once"
        if data.get("send_now"):
            data["schedule"] = datetime.now(ZoneInfo(data.get("timezone") or self.s.default_timezone)).replace(microsecond=0).isoformat()
        missing = [k for k in REQUIRED_CAMPAIGN if data.get(k) in (None, "")]
        if missing:
            raise ValueError(f"Wajib diisi: {', '.join(missing)}")
        if data["personalization"] not in {"template", "segmen", "per_lead"}:
            raise ValueError("personalization harus template, segmen, atau per_lead")
        cadence = data.get("cadence") or "once"
        if cadence not in {"once", "weekly", "monthly"}:
            raise ValueError("cadence harus once, weekly, atau monthly")
        tz = ZoneInfo(data["timezone"])
        schedule = datetime.fromisoformat(data["schedule"])
        if schedule.tzinfo is None:
            schedule = schedule.replace(tzinfo=tz)
        campaign_id = f"CMP-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        template_id = ""
        if data.get("template_subject") or data.get("template_body"):
            template_id = f"TPL-{campaign_id}"
            self.db.upsert("Templates", {"template_id": template_id, "version": 1, "goal": data["goal"], "language": "id",
                                         "subject": data.get("template_subject") or "", "body": data.get("template_body") or ""})
        if data["personalization"] == "template" and not template_id:
            raise ValueError("Personalisasi template membutuhkan subjek dan isi template")
        row = {
            "campaign_id": campaign_id, "name": data["name"], "goal": data["goal"], "offer": data["offer"], "cta": data["cta"],
            "personalization": data["personalization"], "cadence": cadence,
            "max_occurrences": 1 if cadence == "once" else int(data.get("max_occurrences") or 4),
            "count": int(data["count"]), "max_recipients": 1 if single else 0,
            "timezone": data["timezone"], "schedule": schedule.isoformat(),
            "budget": float(data.get("budget") or 0), "sender_name": data["sender_name"],
            "sender_email": data.get("sender_email") or "", "template_id": template_id, "status": "DRAFT",
            "current_occurrence": 1, "created_at": now_iso(), "updated_at": now_iso(),
        }
        row["approval_hash"] = config_hash(row)
        self.db.upsert("Campaigns", row)
        self.audit("user", f"campaign {campaign_id} dibuat")
        return row

    def import_leads(self, campaign_id: str, csv_text: str) -> dict[str, Any]:
        campaign = self._campaign(campaign_id)
        if campaign["status"] not in {"DRAFT"}:
            raise ValueError("Lead hanya dapat diimpor sebelum campaign dijalankan")
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
        fields = {f.strip() for f in reader.fieldnames or []}
        if "name" not in fields or not ({"company", "description"} & fields):
            raise ValueError("CSV wajib memiliki kolom name dan company atau description")
        existing = len(self.db.all("Leads", campaign_id=campaign_id))
        added, skipped = 0, []
        for n, raw in enumerate(reader, start=1):
            if existing + added >= campaign["count"]:
                break
            row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            if not row.get("name") or not (row.get("company") or row.get("description")):
                skipped.append(f"baris {n + 1}: name kosong, atau company dan description sama-sama kosong")
                continue
            self._insert_lead(campaign_id, existing + added + 1, row)
            added += 1
        self.audit("user", f"{added} lead diimpor ke {campaign_id}")
        return {"added": added, "skipped": skipped, "total": existing + added, "requested": campaign["count"]}

    def add_manual_lead(self, campaign_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Lead dari form dashboard: cukup nama lengkap + deskripsi; email boleh menyusul."""
        campaign = self._campaign(campaign_id)
        if campaign["status"] != "DRAFT":
            raise ValueError("Lead hanya dapat ditambahkan sebelum campaign dijalankan")
        existing = len(self.db.all("Leads", campaign_id=campaign_id))
        if existing >= campaign["count"]:
            raise ValueError(f"Jumlah lead sudah mencapai batas campaign ({campaign['count']})")
        row = {k: (str(v).strip() if v is not None else "") for k, v in data.items()}
        if len(row.get("name", "")) < 2:
            raise ValueError("Nama lengkap wajib diisi")
        if len(row.get("description", "")) < 5 and not row.get("company"):
            raise ValueError("Isi deskripsi (mis. peran dan instansi) agar agen dapat mengenali orangnya")
        if row.get("email") and not EMAIL_RE.match(row["email"]):
            raise ValueError("Format email tidak valid")
        if row.get("linkedin_url") and "linkedin.com/" not in row["linkedin_url"].lower():
            raise ValueError("URL LinkedIn harus berupa tautan linkedin.com")
        row["permission_status"] = "granted" if data.get("permission_granted") else ""
        lead = self._insert_lead(campaign_id, existing + 1, row, source="manual")
        self.audit("user", f"lead manual {lead['lead_id']} ditambahkan ke {campaign_id}")
        return lead

    def _insert_lead(self, campaign_id: str, number: int, row: dict[str, str], source: str = "csv") -> dict[str, Any]:
        lead_id = f"{campaign_id}-L{number:03d}"
        return self.db.upsert("Leads", {
            "lead_id": lead_id, "campaign_id": campaign_id, "crm_id": row.get("crm_id") or (f"MANUAL-{number}" if source == "manual" else ""),
            "name": row["name"], "email": row.get("email", "").lower(), "company": row.get("company", ""),
            "domain": row.get("domain", "").lower(), "title_hint": row.get("title_hint", ""),
            "linkedin_url": row.get("linkedin_url", ""), "description": row.get("description", "")[:600], "hints": None,
            "permission_status": row.get("permission_status", "").lower(), "permission_ref": row.get("permission_ref", ""),
            "stage": "imported", "decision": "", "reasons": [], "candidates": [], "identity": None, "updated_at": now_iso(),
        })

    def _campaign(self, campaign_id: str) -> dict[str, Any]:
        c = self.db.get("Campaigns", campaign_id)
        if not c:
            raise KeyError(f"Campaign {campaign_id} tidak ditemukan")
        return c

    def occurrence_id(self, campaign: dict[str, Any]) -> str:
        return f"occ-{campaign['current_occurrence']}"

    def run_campaign(self, campaign_id: str) -> dict[str, Any]:
        campaign = self._campaign(campaign_id)
        if campaign["status"] not in {"DRAFT"}:
            raise ValueError(f"Campaign berstatus {campaign['status']}, tidak dapat dijalankan ulang")
        leads = self.db.all("Leads", campaign_id=campaign_id)
        if not leads:
            raise ValueError("Belum ada lead. Impor CSV atau muat data fiktif dulu.")
        self.db.upsert("Campaigns", {"campaign_id": campaign_id, "status": "RUNNING", "updated_at": now_iso()})
        self.audit("user", f"campaign {campaign_id} dijalankan dengan {len(leads)} lead")
        self._start_occurrence(campaign_id, leads)
        return {"leads": len(leads), "occurrence_id": self.occurrence_id(campaign)}

    def _start_occurrence(self, campaign_id: str, leads: list[dict[str, Any]]) -> None:
        campaign = self._campaign(campaign_id)
        occ = self.occurrence_id(campaign)
        tasks = []
        for lead in leads:
            task_id = f"T-{lead['lead_id']}-{occ}"
            tasks.append(self._update_task(task_id, campaign_id=campaign_id, lead_id=lead["lead_id"], occurrence_id=occ,
                                           stage="queued", status="QUEUED", agent_id="orchestrator", host="",
                                           payload_ref=f"Leads/{lead['lead_id']}", checkpoint={"done": []},
                                           generation=1, lease_until=None, retry=0, error="", started_at=now_iso()))
        self.bus.emit("stage", f"Occurrence {occ}: {len(tasks)} task dibuat", campaign_id=campaign_id)
        self.dispatchers[campaign_id] = asyncio.create_task(self._dispatch_all(campaign_id, [t["task_id"] for t in tasks]))

    async def _dispatch_all(self, campaign_id: str, task_ids: list[str]) -> None:
        batch = asyncio.Semaphore(self.s.batch_size)
        seen = set()

        def email_of(tid):
            lead = self.db.get("Leads", self.db.get("Tasks", tid)["lead_id"])
            return (lead.get("email") or "").lower()

        async def one(tid: str, duplicate: bool):
            try:
                await self._launch(tid, duplicate=duplicate)
                while tid in self.lead_tasks:
                    await asyncio.sleep(0.5)
            finally:
                batch.release()

        pending = []
        for tid in task_ids:
            await batch.acquire()
            email = email_of(tid)
            duplicate = bool(email) and email in seen
            seen.add(email)
            pending.append(asyncio.create_task(one(tid, duplicate)))
        await asyncio.gather(*pending, return_exceptions=True)
        self.bus.emit("stage", "Semua task occurrence telah diproses sampai keputusan", campaign_id=campaign_id)

    # ------------------------------------------------------------ dispatch & contract net
    def negotiate(self, task: dict[str, Any], exclude: str = "") -> str | None:
        eligible = [r for r in self.runtimes.values() if r.online and r.name != exclude]
        if not eligible:
            return None
        for r in eligible:
            self.message("CFP", "orchestrator", f"runtime-{r.name}", task, f"CFP enrichment+riset {task['lead_id']}",
                         deadline=(datetime.now(timezone.utc) + timedelta(seconds=self.s.lease_seconds)).isoformat(timespec="seconds"))
        proposals = {r.name: r.estimate() for r in eligible}
        for name, est in proposals.items():
            self.message("PROPOSE", f"runtime-{name}", "orchestrator", task, f"Runtime {name}: estimasi {est:.1f} dtk", estimate=est)
        winner = min(proposals, key=lambda n: (proposals[n], n))
        for name in proposals:
            perf = "ACCEPT_PROPOSAL" if name == winner else "REJECT_PROPOSAL"
            self.message(perf, "orchestrator", f"runtime-{name}", task, f"{perf} runtime {name}")
        return winner

    async def _launch(self, task_id: str, duplicate: bool = False, host: str | None = None) -> None:
        task = self.db.get("Tasks", task_id)
        done = task["checkpoint"].get("done", [])
        needs_runtime = "research" not in done
        if needs_runtime and host is None:
            host = self.negotiate(task)
            if host is None:
                self._update_task(task_id, status="HELD", stage="no_runtime", error="Tidak ada runtime online")
                self.bus.emit("stage", f"{task_id} ditahan: tidak ada runtime online", task_id=task_id, lead_id=task["lead_id"])
                return
        host = host or "core"
        self._update_task(task_id, host=host, status="QUEUED")
        runner = asyncio.create_task(self._run(task_id, task["generation"], host, duplicate))
        self.lead_tasks[task_id] = runner
        if host in self.runtimes:
            self.runtimes[host].running[task_id] = runner
        runner.add_done_callback(lambda t, tid=task_id, h=host: self._finished(tid, h, t))

    def _finished(self, task_id: str, host: str, runner: asyncio.Task) -> None:
        if self.lead_tasks.get(task_id) is runner:
            self.lead_tasks.pop(task_id, None)
        if host in self.runtimes and self.runtimes[host].running.get(task_id) is runner:
            self.runtimes[host].running.pop(task_id, None)

    async def _run(self, task_id: str, generation: int, host: str, duplicate: bool) -> None:
        task = self.db.get("Tasks", task_id)
        campaign_id, lead_id = task["campaign_id"], task["lead_id"]
        try:
            await self._gate(campaign_id)
            if "validate" not in task["checkpoint"].get("done", []):
                if not self._validate(task, generation, duplicate):
                    return
            task = self.db.get("Tasks", task_id)
            if "research" not in task["checkpoint"].get("done", []):
                runtime = self.runtimes[host]
                async with runtime.semaphore:
                    runtime.active.add(task_id)
                    started = time.monotonic()
                    try:
                        cont = await self._prep_phase(task_id, generation, host)
                    finally:
                        runtime.active.discard(task_id)
                    if not cont:
                        return
                    elapsed = time.monotonic() - started
                    runtime.durations.append(elapsed)
                    runtime.completed += 1
                    self.prep_durations.append(elapsed)
            async with self.core:
                await self._core_phase(task_id, generation)
        except asyncio.CancelledError:
            self.bus.emit("migration", f"Worker {task_id} di runtime {host} berhenti (ACK stop)", task_id=task_id, kind="ack_stop")
            raise
        except Exception as exc:  # kegagalan tak terduga: retry terkontrol dari checkpoint
            log.exception("Task %s gagal", task_id)
            await self._retry_or_review(task_id, generation, exc)

    async def _retry_or_review(self, task_id: str, generation: int, exc: Exception) -> None:
        if not self._task_current(task_id, generation):
            return
        task = self.db.get("Tasks", task_id)
        retry = (task["retry"] or 0) + 1
        if retry < self.s.max_retry:
            new_gen = task["generation"] + 1
            self._update_task(task_id, retry=retry, generation=new_gen, status="RETRY", error=str(exc)[:300],
                              next_run=(datetime.now(timezone.utc) + timedelta(seconds=2 ** retry)).isoformat(timespec="seconds"))
            self.bus.emit("stage", f"{task_id} retry {retry}/{self.s.max_retry - 1}: {exc}", task_id=task_id, lead_id=task["lead_id"])
            await asyncio.sleep(2 ** retry)
            self.lead_tasks.pop(task_id, None)
            await self._launch(task_id)
            return
        self._update_task(task_id, status="FAILED", error=str(exc)[:300])
        self._set_lead(task["lead_id"], stage="failed", decision="REVIEW",
                       reasons=[reason("review", "task_failed", f"Gagal diproses setelah {retry} percobaan: {exc}")])

    def _set_lead(self, lead_id: str, **fields: Any) -> None:
        self.db.upsert("Leads", {"lead_id": lead_id, **fields, "updated_at": now_iso()})
        self.bus.emit("lead", f"Lead {lead_id}: {fields.get('stage', '')} {fields.get('decision', '')}".strip(),
                      lead_id=lead_id, stage=fields.get("stage"), decision=fields.get("decision"))

    def _checkpoint(self, task_id: str, stage: str, **extra: Any) -> None:
        task = self.db.get("Tasks", task_id)
        cp = dict(task["checkpoint"] or {})
        done = list(cp.get("done", []))
        if stage not in done:
            done.append(stage)
        cp.update(extra, done=done)
        self._update_task(task_id, checkpoint=cp, stage=stage,
                          lease_until=time.time() + self.s.lease_seconds)

    # ------------------------------------------------------------ stages
    def _validate(self, task: dict[str, Any], generation: int, duplicate: bool) -> bool:
        lead = self.db.get("Leads", task["lead_id"])
        suppressed = {r["email"].lower() for r in self.db.all("Suppression")}
        reasons = self.security.check_contact(lead, suppressed, duplicate)
        if not self._task_current(task["task_id"], generation):
            return False
        if self.security.decide(reasons) == "BLOCK":
            self._update_task(task["task_id"], status="DONE", stage="blocked")
            self._set_lead(lead["lead_id"], stage="blocked", decision="BLOCK", reasons=reasons)
            self._write_email(task, lead, {"subject": "", "body": "", "used_fact_ids": [], "warnings": []},
                              "BLOCK", reasons, "BLOCKED")
            self.message("INFORM", "security", "orchestrator", task, f"BLOCK {lead['lead_id']}: {reasons[0]['message']}")
            return False
        self._checkpoint(task["task_id"], "validate")
        self._set_lead(lead["lead_id"], stage="validated")
        return True

    async def _prep_phase(self, task_id: str, generation: int, host: str) -> bool:
        task = self._update_task(task_id, status="RUNNING", agent_id="enrichment", host=host,
                                 lease_until=time.time() + self.s.lease_seconds)
        lead = self.db.get("Leads", task["lead_id"])
        campaign = self._campaign(task["campaign_id"])
        errors = list(task["checkpoint"].get("integration_errors", []))

        if "enrichment" not in task["checkpoint"].get("done", []):
            self._set_lead(lead["lead_id"], stage="enrichment")
            identity = self.db.get("Leads", lead["lead_id"]).get("identity")
            try:
                if identity:  # dipilih manual oleh pengguna setelah review
                    result = {"link": "matched", "reason": "dipilih pengguna", "identity": identity, "candidates": [],
                              "match_score": identity.get("score", {}).get("S"), "facts": crm_facts(lead)}
                    for key in ("title", "industry", "location"):
                        if identity.get(key):
                            result["facts"].append(Fact(f"{lead['lead_id']}-apify-{key}", key, identity[key],
                                                        identity.get("profile_url") or "apify://manual", "apify",
                                                        result["match_score"]))
                else:
                    lead = await self._ensure_hints(lead, campaign["campaign_id"], errors)
                    result = await self.enrichment.run(lead)
            except IntegrationError as exc:
                errors.append(f"Enrichment: {exc}")
                result = {"link": "error", "reason": str(exc), "facts": crm_facts(lead), "candidates": [],
                          "identity": None, "match_score": None}
            await self._gate(campaign["campaign_id"])
            if not self._task_current(task_id, generation):
                return False
            for fact in result["facts"]:
                self.db.upsert("Evidence", fact.row(lead["lead_id"]))
            self.message("INFORM_RESULT", f"enrichment@{host}", "orchestrator", task,
                         f"Enrichment {lead['lead_id']}: {result['link']} ({result['reason']})")
            self._set_lead(lead["lead_id"], candidates=result["candidates"], match_score=result["match_score"],
                           identity=result["identity"] or lead.get("identity"), stage="enriched")
            self._checkpoint(task_id, "enrichment", link=result["link"], integration_errors=errors)
            if result["link"] == "ambiguous":
                self._update_task(task_id, status="WAITING_REVIEW", stage="identity_review")
                self._set_lead(lead["lead_id"], stage="identity_review", decision="REVIEW",
                               reasons=[reason("review", "ambiguous_identity", result["reason"])])
                self._write_email(task, lead, {"subject": "", "body": "", "used_fact_ids": [], "warnings": []},
                                  "REVIEW", [reason("review", "ambiguous_identity", result["reason"])], "NEEDS_IDENTITY")
                return False

        task = self.db.get("Tasks", task_id)
        self._update_task(task_id, agent_id="research")
        self._set_lead(lead["lead_id"], stage="research")
        research = {"incidents": [], "dropped": 0}
        if campaign["personalization"] != "template":
            try:
                lead = self.db.get("Leads", lead["lead_id"])
                research = await self.research.run(effective_lead(lead), campaign)
            except IntegrationError as exc:
                errors.append(f"Riset: {exc}")
            await self._gate(campaign["campaign_id"])
            if not self._task_current(task_id, generation):
                return False
            for fact in research.get("facts", []):
                self.db.upsert("Evidence", fact.row(lead["lead_id"]))
            for url in research.get("incidents", []):
                self.bus.emit("incident", f"Instruksi mencurigakan di sumber {url} diabaikan", lead_id=lead["lead_id"])
                self.audit("research", f"insiden prompt injection dari {url}", task_id)
        evidence = self.db.all("Evidence", lead_id=lead["lead_id"])
        selected = select_facts(evidence, self.s.max_facts)
        for f in evidence:
            self.db.upsert("Evidence", {"fact_id": f["fact_id"], "selected": f in selected})
        self.message("INFORM_RESULT", f"research@{host}", "orchestrator", task,
                     f"Riset {lead['lead_id']}: {len(research.get('facts', []))} fakta web, {len(selected)} dipilih")
        self._checkpoint(task_id, "research", selected_fact_ids=[f["fact_id"] for f in selected],
                         incidents=research.get("incidents", []), dropped=research.get("dropped", 0),
                         integration_errors=errors)
        return True

    async def _core_phase(self, task_id: str, generation: int) -> None:
        task = self._update_task(task_id, status="RUNNING", agent_id="writer", host="core")
        lead = self.db.get("Leads", task["lead_id"])
        campaign = self._campaign(task["campaign_id"])
        cp = task["checkpoint"]
        errors = list(cp.get("integration_errors", []))
        facts = [f for f in self.db.all("Evidence", lead_id=lead["lead_id"]) if f["fact_id"] in cp.get("selected_fact_ids", [])]
        template = self.db.get("Templates", campaign["template_id"]) if campaign.get("template_id") else None
        self._set_lead(lead["lead_id"], stage="writing")
        spent = self.usage.cost_by_campaign[campaign["campaign_id"]]
        draft = {"subject": "", "body": "", "used_fact_ids": [], "warnings": []}
        if campaign["budget"] and spent >= campaign["budget"]:
            errors.append(f"Anggaran LLM habis (US${spent:.4f} dari US${campaign['budget']:.2f})")
        else:
            try:
                draft = await self.writer.run(effective_lead(lead), campaign, facts, template)
            except IntegrationError as exc:
                errors.append(f"Writer: {exc}")
        await self._gate(campaign["campaign_id"])
        if not self._task_current(task_id, generation):
            return
        self.message("INFORM_RESULT", "writer", "orchestrator", task,
                     f"Draft {lead['lead_id']} selesai ({draft.get('revisions', 0)} revisi)" if draft["body"] else f"Draft {lead['lead_id']} gagal")
        self.message("REQUEST", "orchestrator", "security", task, f"Periksa fakta, izin & draft {lead['lead_id']}")
        context = {**cp, "integration_errors": errors}
        reasons = self.security.check_contact(lead, {r["email"].lower() for r in self.db.all("Suppression")}, False)
        if not draft["body"]:
            reasons.append(reason("review", "no_draft", "Draft belum tersedia; tulis manual atau jalankan ulang"))
        reasons += self.security.check_draft(effective_lead(lead), campaign, draft, facts, context)
        decision = self.security.decide(reasons)
        status = {"PASS": "AWAITING_APPROVAL", "REVIEW": "NEEDS_REVIEW", "BLOCK": "BLOCKED"}[decision]
        self._write_email(task, lead, draft, decision, reasons, status)
        self.message(decision, "security", "orchestrator", task, f"{decision} {lead['lead_id']}")
        self._checkpoint(task_id, "security", integration_errors=errors)
        self._update_task(task_id, status="DONE", stage="decided", lease_until=None)
        self._set_lead(lead["lead_id"], stage="decided", decision=decision, reasons=reasons)

    async def _ensure_hints(self, lead: dict[str, Any], campaign_id: str, errors: list[str]) -> dict[str, Any]:
        """Ekstrak instansi/peran dari deskripsi bila kolom CRM kosong. Disimpan agar resume tidak memanggil LLM lagi."""
        if not self.hints or not lead.get("description") or lead.get("hints") or (lead.get("company") and lead.get("title_hint")):
            return lead
        try:
            hints = await self.hints.run(lead, campaign_id)
        except IntegrationError as exc:
            errors.append(f"Petunjuk deskripsi: {exc}")
            return lead
        self.bus.emit("stage", f"Petunjuk {lead['lead_id']}: {hints['role'] or '-'} @ {hints['organization'] or '-'}",
                      lead_id=lead["lead_id"])
        return self.db.upsert("Leads", {"lead_id": lead["lead_id"], "hints": hints, "updated_at": now_iso()})

    def set_lead_email(self, lead_id: str, email_addr: str) -> dict[str, Any]:
        lead = self.db.get("Leads", lead_id)
        if not lead:
            raise KeyError("Lead tidak ditemukan")
        email_addr = email_addr.strip().lower()
        if not EMAIL_RE.match(email_addr):
            raise ValueError("Format email tidak valid")
        campaign = self._campaign(lead["campaign_id"])
        send_key = f"{lead['campaign_id']}:{self.occurrence_id(campaign)}:{lead_id}:step1"
        email = self.db.get("Emails", send_key)
        if email and email["status"] in FINAL_EMAIL | {"SENDING"}:
            raise ValueError("Email sudah diproses kirim; alamat tidak dapat diubah")
        self.db.upsert("Leads", {"lead_id": lead_id, "email": email_addr, "updated_at": now_iso()})
        self.audit("user", f"email penerima {lead_id} diisi/diubah")
        if email:
            self.db.upsert("Emails", {"send_key": send_key, "to_email": email_addr})
            if email["body"] and email["status"] != "NEEDS_IDENTITY":
                self.edit_email(send_key, email["subject"], email["body"])  # periksa ulang + batalkan approval lama
        return self.db.get("Leads", lead_id)

    def _write_email(self, task, lead, draft, decision, reasons, status) -> dict[str, Any]:
        send_key = f"{task['campaign_id']}:{task['occurrence_id']}:{lead['lead_id']}:step1"
        prev = self.db.get("Emails", send_key) or {}
        return self.db.upsert("Emails", {
            "send_key": send_key, "campaign_id": task["campaign_id"], "occurrence_id": task["occurrence_id"],
            "lead_id": lead["lead_id"], "to_email": lead.get("email", ""), "subject": draft.get("subject", ""),
            "body": draft.get("body", ""), "used_fact_ids": draft.get("used_fact_ids", []),
            "warnings": draft.get("warnings", []), "draft_version": (prev.get("draft_version") or 0) + 1,
            "security_decision": decision, "security_reasons": reasons, "approval_hash": "", "approved_at": None,
            "schedule": self._campaign(task["campaign_id"])["schedule"], "gmail_id": "", "status": status, "error": "",
            "llm_model": draft.get("llm_model", ""), "tokens_in": (prev.get("tokens_in") or 0) + draft.get("tokens_in", 0),
            "tokens_out": (prev.get("tokens_out") or 0) + draft.get("tokens_out", 0),
            "cost_usd": round((prev.get("cost_usd") or 0) + draft.get("cost_usd", 0.0), 6), "updated_at": now_iso(),
        })

    # ------------------------------------------------------------ migrasi (§5.3)
    async def migrate(self, task_id: str, target: str, reason_text: str = "manual") -> dict[str, Any]:
        task = self.db.get("Tasks", task_id)
        if not task:
            raise KeyError(f"Task {task_id} tidak ditemukan")
        if target not in self.runtimes or not self.runtimes[target].online:
            raise ValueError(f"Runtime {target} tidak tersedia")
        source = task["host"]
        if source not in self.runtimes or "research" in task["checkpoint"].get("done", []) or task["status"] in {"DONE", "WAITING_REVIEW", "FAILED"}:
            raise ValueError("Hanya task enrichment/riset yang sedang antre atau berjalan di runtime A/B yang dapat dipindahkan")
        if source == target:
            raise ValueError("Runtime tujuan sama dengan runtime asal")
        started = time.monotonic()
        self.message("REQUEST", "orchestrator", f"runtime-{source}", task, f"Bekukan {task_id} untuk migrasi ke {target}")
        self._update_task(task_id, status="MIGRATING")
        runner = self.runtimes[source].running.get(task_id)
        if runner and not runner.done():
            runner.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(runner), timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        self.lead_tasks.pop(task_id, None)
        self.runtimes[source].running.pop(task_id, None)
        task = self.db.get("Tasks", task_id)
        new_gen = task["generation"] + 1
        self._update_task(task_id, generation=new_gen, host=target, status="QUEUED", lease_until=None)
        self.message("INFORM", f"runtime-{source}", "orchestrator", task,
                     f"Checkpoint {task_id}: selesai {task['checkpoint'].get('done', [])}; generation {task['generation']}→{new_gen}")
        record = {"task_id": task_id, "lead_id": task["lead_id"], "from": source, "to": target, "generation": new_gen,
                  "checkpoint": task["checkpoint"].get("done", []), "reason": reason_text, "at": now_iso(),
                  "overhead_ms": round((time.monotonic() - started) * 1000)}
        self.migrations.appendleft(record)
        self.bus.emit("migration", f"{task_id} dipindah {source}→{target} (generation {new_gen})", kind="migrated", **record)
        self.audit("orchestrator", f"migrasi {source}->{target} generation {new_gen} ({reason_text})", task_id)
        await self._launch(task_id, host=target)
        return record

    async def set_runtime_online(self, name: str, online: bool) -> dict[str, Any]:
        runtime = self.runtimes[name]
        runtime.online = online
        self.bus.emit("runtime", f"Runtime {name} {'online' if online else 'offline'}", runtime=name, online=online)
        moved = []
        if not online:
            other = next((r.name for r in self.runtimes.values() if r.online), None)
            for task_id in list(runtime.running):
                if other:
                    try:
                        moved.append(await self.migrate(task_id, other, f"runtime {name} offline"))
                    except ValueError:
                        pass
                else:
                    runner = runtime.running.pop(task_id)
                    runner.cancel()
                    self.lead_tasks.pop(task_id, None)
                    self._update_task(task_id, status="HELD", stage="no_runtime", error="Semua runtime offline")
        else:
            for task in self.db.all("Tasks", status="HELD"):
                self.lead_tasks.pop(task["task_id"], None)
                await self._launch(task["task_id"], host=name)
        return {"runtime": name, "online": online, "moved": len(moved)}

    # ------------------------------------------------------------ review & approval
    async def resolve_identity(self, lead_id: str, candidate_index: int | None) -> dict[str, Any]:
        lead = self.db.get("Leads", lead_id)
        task = self._latest_task(lead_id)
        if not lead or not task or task["status"] != "WAITING_REVIEW":
            raise ValueError("Lead ini tidak sedang menunggu review identitas")
        cp = dict(task["checkpoint"])
        cp["done"] = [d for d in cp.get("done", []) if d != "enrichment"]
        if candidate_index is None:
            self.db.upsert("Leads", {"lead_id": lead_id, "identity": None})
            cp["done"].append("enrichment")
            cp["link"] = "not_found"
            summary = "pengguna memilih lanjut tanpa kandidat enrichment"
        else:
            candidate = lead["candidates"][candidate_index]
            self.db.upsert("Leads", {"lead_id": lead_id, "identity": candidate})
            summary = f"pengguna memilih kandidat {candidate.get('name')} ({candidate.get('company')})"
        self._update_task(task["task_id"], checkpoint=cp, status="QUEUED", generation=task["generation"] + 1)
        self._set_lead(lead_id, stage="identity_resolved", decision="", reasons=[])
        self.audit("user", summary, task["task_id"])
        self.lead_tasks.pop(task["task_id"], None)
        await self._launch(task["task_id"])
        return {"lead_id": lead_id, "resumed": task["task_id"]}

    def _latest_task(self, lead_id: str) -> dict[str, Any] | None:
        tasks = self.db.all("Tasks", lead_id=lead_id)
        return max(tasks, key=lambda t: t["occurrence_id"]) if tasks else None

    def edit_email(self, send_key: str, subject: str, body: str) -> dict[str, Any]:
        email = self.db.get("Emails", send_key)
        if not email or email["status"] in FINAL_EMAIL | {"SENDING", "NEEDS_IDENTITY"}:
            raise ValueError("Draft ini tidak dapat diedit")
        lead = self.db.get("Leads", email["lead_id"])
        campaign = self._campaign(email["campaign_id"])
        task = self.db.get("Tasks", f"T-{email['lead_id']}-{email['occurrence_id']}")
        cp = (task or {}).get("checkpoint") or {}
        facts = [f for f in self.db.all("Evidence", lead_id=lead["lead_id"]) if f["fact_id"] in cp.get("selected_fact_ids", [])]
        body = body.strip()
        if OPT_OUT_LINE not in body:
            body = f"{body}\n\n{OPT_OUT_LINE}"
        draft = {"subject": subject.strip(), "body": body, "used_fact_ids": email["used_fact_ids"], "warnings": []}
        reasons = self.security.check_contact(lead, {r["email"].lower() for r in self.db.all("Suppression")}, False)
        reasons += self.security.check_draft(effective_lead(lead), campaign, draft, facts, {**cp, "integration_errors": []})
        decision = self.security.decide(reasons)
        was_approved = email["status"] == "APPROVED"
        row = self.db.upsert("Emails", {
            "send_key": send_key, "subject": draft["subject"], "body": body, "warnings": [],
            "draft_version": email["draft_version"] + 1, "security_decision": decision, "security_reasons": reasons,
            "approval_hash": "", "approved_at": None, "error": "",
            "status": {"PASS": "AWAITING_APPROVAL", "REVIEW": "NEEDS_REVIEW", "BLOCK": "BLOCKED"}[decision],
            "updated_at": now_iso(),
        })
        self._set_lead(lead["lead_id"], decision=decision, reasons=reasons)
        self.audit("user", f"draft {send_key} diedit ke versi {row['draft_version']}" + ("; approval lama dibatalkan" if was_approved else ""))
        self.bus.emit("approval", f"Draft {lead['lead_id']} diedit (v{row['draft_version']}), keputusan {decision}", send_key=send_key)
        return row

    def approve(self, send_key: str, draft_version: int, acknowledge_review: bool = False) -> dict[str, Any]:
        email = self.db.get("Emails", send_key)
        if not email:
            raise KeyError("Draft tidak ditemukan")
        if email["draft_version"] != draft_version:
            raise ValueError(f"Versi draft berubah (sekarang v{email['draft_version']}); muat ulang sebelum menyetujui")
        if email["status"] == "AWAITING_APPROVAL":
            pass
        elif email["status"] == "NEEDS_REVIEW" and acknowledge_review:
            pass
        elif email["status"] == "NEEDS_REVIEW":
            raise ValueError("Draft perlu review: centang konfirmasi bahwa alasan review sudah diperiksa")
        else:
            raise ValueError(f"Draft berstatus {email['status']} tidak dapat disetujui")
        if not email["body"] or not email["subject"]:
            raise ValueError("Draft kosong tidak dapat disetujui")
        if not EMAIL_RE.match(email["to_email"] or ""):
            raise ValueError("Isi email penerima yang valid sebelum menyetujui")
        campaign = self._campaign(email["campaign_id"])
        limit = campaign.get("max_recipients") or 0
        taken = recipients(self.db, campaign["campaign_id"], COMMITTED, exclude_key=send_key)
        if limit and email["to_email"].lower() not in taken and len(taken) >= limit:
            raise ValueError(f"Campaign ini dibatasi {limit} penerima dan kuotanya sudah terpakai ({', '.join(sorted(taken))})")
        row = self.db.upsert("Emails", {"send_key": send_key, "status": "APPROVED", "approved_at": now_iso(),
                                        "approval_hash": approval_hash(email, campaign), "error": "",
                                        "schedule": campaign["schedule"], "updated_at": now_iso()})
        self.audit("user", f"draft {send_key} v{draft_version} disetujui" + (" setelah review" if acknowledge_review else ""))
        self.bus.emit("approval", f"Draft {email['lead_id']} v{draft_version} disetujui", send_key=send_key)
        return row

    def approve_all_pass(self, campaign_id: str) -> int:
        count = 0
        for email in self.db.all("Emails", campaign_id=campaign_id, status="AWAITING_APPROVAL"):
            try:
                self.approve(email["send_key"], email["draft_version"])
            except ValueError:
                if self._campaign(campaign_id).get("max_recipients"):
                    break  # kuota penerima penuh
                raise
            count += 1
        return count

    def reject(self, send_key: str) -> dict[str, Any]:
        email = self.db.get("Emails", send_key)
        if not email or email["status"] in FINAL_EMAIL | {"SENDING"}:
            raise ValueError("Draft tidak dapat ditolak")
        self.audit("user", f"draft {send_key} ditolak")
        return self.db.upsert("Emails", {"send_key": send_key, "status": "REJECTED", "approval_hash": "", "updated_at": now_iso()})

    def suppress(self, email_addr: str, reason_text: str) -> None:
        email_addr = email_addr.strip().lower()
        if not EMAIL_RE.match(email_addr):
            raise ValueError("Format email tidak valid")
        self.db.upsert("Suppression", {"email": email_addr, "reason": reason_text or "manual", "recorded_at": now_iso()})
        for e in self.db.all("Emails", to_email=email_addr):
            if e["status"] not in FINAL_EMAIL | {"SENDING"}:
                self.db.upsert("Emails", {"send_key": e["send_key"], "status": "BLOCKED", "security_decision": "BLOCK",
                                          "approval_hash": "", "error": "Masuk suppression", "updated_at": now_iso()})
                self._set_lead(e["lead_id"], decision="BLOCK",
                               reasons=[reason("block", "suppressed", "Email ada di daftar suppression")])
        self.audit("user", f"suppression ditambahkan ({reason_text or 'manual'})")

    def reconcile(self, send_key: str, outcome: str) -> dict[str, Any]:
        email = self.db.get("Emails", send_key)
        if not email or email["status"] != "SENT_UNKNOWN":
            raise ValueError("Hanya status SENT_UNKNOWN yang direkonsiliasi")
        status = {"sent": "SENT", "not_sent": "NOT_SENT"}[outcome]
        self.audit("user", f"rekonsiliasi {send_key}: {status}")
        return self.db.upsert("Emails", {"send_key": send_key, "status": status, "error": "direkonsiliasi manual",
                                         "updated_at": now_iso()})

    def set_paused(self, campaign_id: str, paused: bool) -> dict[str, Any]:
        campaign = self._campaign(campaign_id)
        if campaign["status"] in {"DRAFT", "COMPLETED"}:
            raise ValueError(f"Campaign {campaign['status']} tidak dapat di-pause/resume")
        status = "PAUSED" if paused else "RUNNING"
        self.audit("user", f"campaign {campaign_id} {status}")
        self.bus.emit("stage", f"Campaign {campaign_id} {'dijeda' if paused else 'dilanjutkan'}", campaign_id=campaign_id)
        return self.db.upsert("Campaigns", {"campaign_id": campaign_id, "status": status, "updated_at": now_iso()})

    # ------------------------------------------------------------ pemulihan & occurrence
    async def recover(self) -> dict[str, int]:
        resumed = unknown = 0
        for email in self.db.all("Emails", status="SENDING"):
            self.db.upsert("Emails", {"send_key": email["send_key"], "status": "SENT_UNKNOWN",
                                      "error": "Proses berhenti saat mengirim; perlu rekonsiliasi", "updated_at": now_iso()})
            unknown += 1
        for task in self.db.all("Tasks"):
            if task["status"] in {"QUEUED", "RUNNING", "MIGRATING", "RETRY", "HELD"}:
                campaign = self.db.get("Campaigns", task["campaign_id"])
                if not campaign or campaign["status"] not in {"RUNNING", "PAUSED"}:
                    continue
                self._update_task(task["task_id"], generation=task["generation"] + 1, status="QUEUED", host="")
                self.audit("orchestrator", "task dilanjutkan dari checkpoint setelah restart", task["task_id"])
                await self._launch(task["task_id"])
                resumed += 1
        if resumed or unknown:
            self.bus.emit("stage", f"Pemulihan: {resumed} task dilanjutkan, {unknown} email SENT_UNKNOWN")
        return {"resumed": resumed, "sent_unknown": unknown}

    def maybe_next_occurrence(self, campaign_id: str) -> bool:
        campaign = self._campaign(campaign_id)
        occ = self.occurrence_id(campaign)
        emails = self.db.all("Emails", campaign_id=campaign_id, occurrence_id=occ)
        tasks = self.db.all("Tasks", campaign_id=campaign_id, occurrence_id=occ)
        if campaign["status"] != "RUNNING" or not tasks or any(t["status"] not in {"DONE", "FAILED"} for t in tasks):
            return False
        if len(emails) < len(tasks) or any(e["status"] not in FINAL_EMAIL for e in emails):
            return False
        if campaign["cadence"] == "once" or campaign["current_occurrence"] >= campaign["max_occurrences"]:
            self.db.upsert("Campaigns", {"campaign_id": campaign_id, "status": "COMPLETED", "updated_at": now_iso()})
            self.bus.emit("stage", f"Campaign {campaign_id} selesai", campaign_id=campaign_id)
            return False
        next_schedule = datetime.fromisoformat(campaign["schedule"]) + timedelta(days=CADENCE_DAYS[campaign["cadence"]])
        self.db.upsert("Campaigns", {"campaign_id": campaign_id, "current_occurrence": campaign["current_occurrence"] + 1,
                                     "schedule": next_schedule.isoformat(), "updated_at": now_iso()})
        suppressed = {r["email"].lower() for r in self.db.all("Suppression")}
        leads = [l for l in self.db.all("Leads", campaign_id=campaign_id) if (l["email"] or "").lower() not in suppressed]
        self.audit("scheduler", f"occurrence berikutnya {next_schedule.isoformat()} dibuat; perlu approval ulang")
        self._start_occurrence(campaign_id, leads)
        return True

    # ------------------------------------------------------------ ringkasan
    def campaign_summary(self, campaign_id: str) -> dict[str, Any]:
        campaign = self._campaign(campaign_id)
        occ = self.occurrence_id(campaign)
        leads = self.db.all("Leads", campaign_id=campaign_id)
        emails = self.db.all("Emails", campaign_id=campaign_id, occurrence_id=occ)
        tasks = self.db.all("Tasks", campaign_id=campaign_id, occurrence_id=occ)
        decisions = Counter(e["security_decision"] for e in emails)
        statuses = Counter(e["status"] for e in emails)
        stages = Counter(t["stage"] for t in tasks)
        durations = sorted(self.prep_durations)
        p95 = durations[max(0, int(len(durations) * 0.95) - 1)] if durations else None
        return {
            "campaign": campaign, "occurrence_id": occ,
            "counts": {"requested": campaign["count"], "imported": len(leads), "tasks": len(tasks),
                       "in_progress": sum(1 for t in tasks if t["status"] not in {"DONE", "FAILED", "WAITING_REVIEW"}),
                       "pass": decisions.get("PASS", 0), "review": decisions.get("REVIEW", 0), "block": decisions.get("BLOCK", 0)},
            "email_status": dict(statuses), "stages": dict(stages),
            "cost_usd": round(self.usage.cost_by_campaign[campaign_id], 6),
            "prep_seconds": {"avg": round(sum(durations) / len(durations), 2) if durations else None,
                             "p95": round(p95, 2) if p95 is not None else None, "n": len(durations)},
        }
