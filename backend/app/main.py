"""API dashboard Outreach Control. Jalankan: `uvicorn app.main:app --port 8000` dari folder backend."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import Body, FastAPI, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agents import EnrichmentAgent, ProfileHintAgent, ResearchAgent, SecurityAgent, WriterAgent
from .config import BACKEND_DIR, ROOT, Settings, load_settings
from .google_auth import SHEETS_SCOPE, GmailOAuth, GoogleAuthError, ServiceAccountTokenProvider
from .integrations import (ApifyClient, FirecrawlClient, GmailClient, IntegrationError, OpenRouterClient, SimApify,
                           SimFirecrawl, SimGmail, SimLLM, SimulatedWorld, Usage)
from .orchestrator import MAX_BODY, MAX_CAMPAIGN_COUNT, MAX_FIELD, MAX_SUBJECT, MAX_TEXT, EventBus, Orchestrator
from .scheduler import Scheduler
from .store import DataGateway, LocalBackend, SheetsBackend

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # URL request memuat ID spreadsheet
log = logging.getLogger("outreach")


class AppState:
    settings: Settings
    http: httpx.AsyncClient
    usage: Usage
    bus: EventBus
    db: DataGateway
    orch: Orchestrator
    scheduler: Scheduler
    clients: dict[str, Any]
    modes: dict[str, str]
    storage_note: str
    oauth: GmailOAuth | None
    service_account: ServiceAccountTokenProvider | None


def build_state(settings: Settings, http: httpx.AsyncClient) -> AppState:
    st = AppState()
    st.settings, st.http, st.usage, st.bus = settings, http, Usage(), EventBus()
    st.oauth = GmailOAuth(settings.google_client_id, settings.google_client_secret, settings.google_oauth_redirect_uri,
                          settings.google_token_file, http) if settings.configured("gmail") else None
    sa_path = settings.service_account_path()
    st.service_account = ServiceAccountTokenProvider(sa_path, [SHEETS_SCOPE], http) if sa_path else None
    world = SimulatedWorld() if settings.simulate_integrations else None

    def pick(name: str, real, sim):
        if settings.configured(name):
            st.modes[name] = "live"
            return real()
        if world is not None:
            st.modes[name] = "simulasi"
            return sim()
        st.modes[name] = "belum"
        return real()

    st.modes = {}
    st.clients = {
        "openrouter": pick("openrouter", lambda: OpenRouterClient(settings, http, st.usage), lambda: SimLLM(st.usage)),
        "apify": pick("apify", lambda: ApifyClient(settings, http, st.usage), lambda: SimApify(world, st.usage)),
        "firecrawl": pick("firecrawl", lambda: FirecrawlClient(settings, http, st.usage), lambda: SimFirecrawl(world, st.usage)),
        "gmail": pick("gmail", lambda: GmailClient(settings, http, st.usage, st.oauth), lambda: SimGmail(settings, st.usage)),
    }
    if settings.data_backend == "sheets" and settings.configured("sheets"):
        backend = SheetsBackend(settings, st.service_account, http)
        st.modes["sheets"] = "live"
        st.storage_note = "Google Sheets"
    else:
        backend = LocalBackend(settings.local_store_path)
        st.modes["sheets"] = "belum" if settings.data_backend == "sheets" else "lokal"
        st.storage_note = ("Sheets belum dikonfigurasi: memakai file lokal sementara"
                           if settings.data_backend == "sheets" else "File lokal (DATA_BACKEND=local)")
    st.db = DataGateway(backend, settings.flush_seconds)
    st.orch = Orchestrator(settings, st.db, st.usage, st.bus,
                           EnrichmentAgent(settings, st.clients["apify"]),
                           ResearchAgent(settings, st.clients["firecrawl"], st.clients["openrouter"]),
                           WriterAgent(settings, st.clients["openrouter"]), SecurityAgent(settings),
                           ProfileHintAgent(st.clients["openrouter"]))
    st.scheduler = Scheduler(settings, st.orch, st.clients["gmail"], st.bus, simulated=st.modes["gmail"] == "simulasi")
    return st


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    async with httpx.AsyncClient() as http:
        st = build_state(settings, http)
        await st.db.start()
        await st.orch.recover()
        st.scheduler.start()
        app.state.s = st
        log.info("Siap. Penyimpanan: %s; mode integrasi: %s", st.storage_note, st.modes)
        try:
            yield
        finally:
            st.scheduler.stop()
            await st.db.stop()


app = FastAPI(title="Outreach Control API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=load_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])


class DurableWrites:
    """BUG-07: permintaan yang mengubah data baru dibalas setelah data ditulis ke penyimpanan (bukan menunggu batch 2 dtk).

    ASGI murni (bukan BaseHTTPMiddleware) agar SSE `/api/events` tidak terganggu. Gagal flush tidak menggagalkan respons:
    batch berkala mencoba lagi, dan kegagalannya terlihat di status penyimpanan.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await self.app(scope, receive, send)
        held: dict | None = None

        async def flush() -> None:
            st = getattr(scope["app"].state, "s", None)
            if st is None:
                return
            try:
                await st.db.flush()
            except Exception:
                log.exception("Flush setelah permintaan gagal; batch berkala akan mengulang")

        async def wrapped(message):
            nonlocal held
            if message["type"] == "http.response.start":
                held = message  # tahan sampai data tertulis
                return
            if held is not None:
                if held["status"] < 400:
                    await flush()
                await send(held)
                held = None
            await send(message)

        await self.app(scope, receive, wrapped)


app.add_middleware(DurableWrites)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """Pesan validasi berupa teks Indonesia singkat (UI hanya menampilkan `detail` bertipe string)."""
    parts = []
    for err in exc.errors()[:3]:
        where = ".".join(str(x) for x in err["loc"] if x != "body")
        parts.append(f"{where or 'input'}: {err['msg']}")
    return JSONResponse({"detail": "Input tidak valid — " + "; ".join(parts)}, status_code=422)


def S(request: Request) -> AppState:
    return request.app.state.s


def guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'\"")) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


async def aguard(coro):
    try:
        return await coro
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'\"")) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------- sistem & integrasi
INTEGRATION_INFO = {
    "openrouter": "LLM penulis email dan ekstraksi fakta",
    "apify": "Enrichment profil (actor Apify)",
    "firecrawl": "Riset bukti web",
    "sheets": "Database campaign (Google Sheets)",
    "gmail": "Pengiriman email",
}


@app.get("/api/system")
async def system(request: Request):
    st = S(request)
    s = st.settings
    return {
        "storage": {"backend": st.db.backend.name, "note": st.storage_note, "pending_writes": st.db.pending_writes(),
                    "last_flush_error": st.db.last_flush_error, "spreadsheet_id_set": bool(s.sheets_spreadsheet_id),
                    "service_account_email": _sa_email(st)},
        "google": {**(st.oauth.status() if st.oauth else {"connected": False, "email": ""}),
                   "configured": st.oauth is not None, "connect_url": "/api/google/connect",
                   "redirect_uri": s.google_oauth_redirect_uri},
        "integrations": [{"name": n, "purpose": INTEGRATION_INFO[n], "mode": st.modes[n], "missing": s.missing(n)}
                         for n in INTEGRATION_INFO],
        "model": s.openrouter_model,
        "delivery": {"mode": "draft" if s.draft_only else "send", "setting": s.delivery_mode,
                     "reason": ("GOOGLE_CLIENT_ID/SECRET belum diisi" if s.delivery_mode == "auto" else "DELIVERY_MODE=draft")
                     if s.draft_only else ""},
        "sending": {"enabled": s.gmail_send_enabled, "blocked_reason": st.scheduler.blocked_reason(),
                    "allowlist": s.gmail_allowlist, "interval_seconds": s.send_interval_seconds,
                    "sender": st.oauth.sender_email if st.oauth else ""},
        "limits": {"batch_size": s.batch_size, "workers": s.runtime_a_workers + s.runtime_b_workers,
                   "max_facts": s.max_facts, "max_revisions": s.max_revisions, "max_retry": s.max_retry,
                   "entity_threshold": s.entity_accept_threshold, "entity_gap": s.entity_min_gap},
        "simulate": s.simulate_integrations,
        "scheduler_tick": st.scheduler.last_tick,
    }


def _sa_email(st: AppState) -> str:
    try:
        return st.service_account.email if st.service_account else ""
    except GoogleAuthError:
        return ""


@app.get("/api/google/connect")
async def google_connect(request: Request):
    st = S(request)
    if not st.oauth:
        raise HTTPException(400, f"Isi dahulu di .env: {', '.join(st.settings.missing('gmail'))}")
    return RedirectResponse(st.oauth.authorization_url())


@app.get("/api/google/callback")
async def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    st = S(request)
    target = f"{st.settings.app_url}/?tab=koneksi"
    if error or not st.oauth:
        return RedirectResponse(f"{target}&google=error&detail={error or 'belum_dikonfigurasi'}")
    try:
        status = await st.oauth.complete(state, code)
    except (GoogleAuthError, httpx.HTTPError) as exc:
        log.warning("Koneksi Google gagal: %s", exc)
        return RedirectResponse(f"{target}&google=error&detail={quote(str(exc)[:200])}")
    st.orch.audit("user", f"akun Google pengirim dihubungkan ({status['email']})")
    return RedirectResponse(f"{target}&google=connected")


@app.post("/api/google/disconnect")
async def google_disconnect(request: Request):
    st = S(request)
    if st.oauth:
        await st.oauth.disconnect()
        st.orch.audit("user", "akun Google pengirim diputus")
    return {"connected": False}


@app.post("/api/integrations/{name}/test")
async def test_integration(name: str, request: Request):
    st = S(request)
    if name not in INTEGRATION_INFO:
        raise HTTPException(404, "Integrasi tidak dikenal")
    if st.modes[name] == "belum":
        return {"ok": False, "message": f"Belum dikonfigurasi: {', '.join(st.settings.missing(name))}"}
    try:
        if name == "sheets":
            if st.db.backend.name != "sheets":
                return {"ok": False, "message": st.storage_note}
            await st.db.flush()
            return {"ok": True, "message": "Terhubung; tab dan header sudah disiapkan"}
        return {"ok": True, "message": await st.clients[name].ping()}
    except (IntegrationError, RuntimeError, httpx.HTTPError) as exc:
        return {"ok": False, "message": str(exc)[:300]}


# ---------------------------------------------------------------- campaign
class CampaignIn(BaseModel):
    name: str = Field(max_length=MAX_FIELD)
    goal: str = Field(max_length=MAX_FIELD)
    offer: str = Field(max_length=MAX_FIELD)
    cta: str = Field(max_length=MAX_FIELD)
    personalization: str = Field(default="per_lead", max_length=20)
    cadence: str = Field(default="once", max_length=20)
    max_occurrences: int | None = Field(default=None, ge=1, le=12)
    count: int = Field(default=1, ge=1, le=MAX_CAMPAIGN_COUNT)
    timezone: str = Field(default="Asia/Jakarta", max_length=64)
    schedule: str = Field(default="", max_length=40)
    budget: float = Field(default=0, ge=0, le=1e9)
    sender_name: str = Field(max_length=MAX_FIELD)
    template_subject: str = Field(default="", max_length=MAX_SUBJECT)
    template_body: str = Field(default="", max_length=MAX_TEXT)
    single_recipient: bool = False
    send_now: bool = False


@app.get("/api/campaigns")
async def list_campaigns(request: Request):
    st = S(request)
    rows = sorted(st.db.all("Campaigns"), key=lambda c: c["created_at"] or "", reverse=True)
    return [st.orch.campaign_summary(c["campaign_id"]) for c in rows]


@app.post("/api/campaigns")
async def create_campaign(body: CampaignIn, request: Request):
    st = S(request)
    data = body.model_dump() | {"sender_email": st.oauth.sender_email if st.oauth else ""}
    return guard(st.orch.create_campaign, data)


@app.get("/api/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, request: Request):
    return guard(S(request).orch.campaign_summary, campaign_id)


@app.post("/api/campaigns/{campaign_id}/leads/csv")
async def upload_leads(campaign_id: str, file: UploadFile, request: Request):
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "File CSV maksimal 2 MB")
    return guard(S(request).orch.import_leads, campaign_id, raw.decode("utf-8-sig", errors="replace"))


class LeadIn(BaseModel):
    name: str = Field(max_length=MAX_FIELD)
    description: str = Field(default="", max_length=MAX_TEXT)
    email: str = Field(default="", max_length=320)
    company: str = Field(default="", max_length=MAX_FIELD)
    title_hint: str = Field(default="", max_length=MAX_FIELD)
    linkedin_url: str = Field(default="", max_length=500)
    permission_granted: bool = False
    permission_ref: str = Field(default="", max_length=MAX_FIELD)


@app.post("/api/campaigns/{campaign_id}/leads")
async def add_lead(campaign_id: str, body: LeadIn, request: Request):
    return guard(S(request).orch.add_manual_lead, campaign_id, body.model_dump())


@app.put("/api/leads/{lead_id}/email")
async def set_lead_email(lead_id: str, request: Request, email: str = Body(embed=True, max_length=320)):
    return guard(S(request).orch.set_lead_email, lead_id, email)


@app.post("/api/campaigns/{campaign_id}/leads/sample")
async def sample_leads(campaign_id: str, request: Request):
    text = (BACKEND_DIR / "data" / "leads_fiktif.csv").read_text(encoding="utf-8")
    return guard(S(request).orch.import_leads, campaign_id, text)


@app.post("/api/campaigns/{campaign_id}/run")
async def run_campaign(campaign_id: str, request: Request):
    return guard(S(request).orch.run_campaign, campaign_id)


@app.post("/api/campaigns/{campaign_id}/pause")
async def pause(campaign_id: str, request: Request, paused: bool = Body(embed=True)):
    return guard(S(request).orch.set_paused, campaign_id, paused)


@app.post("/api/campaigns/{campaign_id}/approve-pass")
async def approve_pass(campaign_id: str, request: Request):
    return {"approved": guard(S(request).orch.approve_all_pass, campaign_id)}


@app.get("/api/campaigns/{campaign_id}/leads")
async def campaign_leads(campaign_id: str, request: Request):
    st = S(request)
    campaign = guard(st.orch._campaign, campaign_id)
    occ = st.orch.occurrence_id(campaign)
    emails = {e["lead_id"]: e for e in st.db.all("Emails", campaign_id=campaign_id, occurrence_id=occ)}
    tasks = {t["lead_id"]: t for t in st.db.all("Tasks", campaign_id=campaign_id, occurrence_id=occ)}
    out = []
    for lead in st.db.all("Leads", campaign_id=campaign_id):
        e, t = emails.get(lead["lead_id"]), tasks.get(lead["lead_id"])
        out.append({
            "lead_id": lead["lead_id"], "name": lead["name"], "email": lead["email"], "description": lead.get("description") or "",
            "company": lead["company"] or (lead.get("hints") or {}).get("organization") or "",
            "stage": lead["stage"], "decision": lead["decision"], "match_score": lead["match_score"],
            "reasons": lead["reasons"], "subject": e["subject"] if e else "", "email_status": e["status"] if e else "",
            "send_key": e["send_key"] if e else "", "task_status": t["status"] if t else "", "host": t["host"] if t else "",
        })
    return out


@app.get("/api/leads/{lead_id}")
async def lead_detail(lead_id: str, request: Request):
    st = S(request)
    lead = st.db.get("Leads", lead_id)
    if not lead:
        raise HTTPException(404, "Lead tidak ditemukan")
    campaign = st.db.get("Campaigns", lead["campaign_id"])
    occ = st.orch.occurrence_id(campaign)
    task = st.db.get("Tasks", f"T-{lead_id}-{occ}")
    email = st.db.get("Emails", f"{lead['campaign_id']}:{occ}:{lead_id}:step1")
    evidence = sorted(st.db.all("Evidence", lead_id=lead_id), key=lambda f: (not f["selected"], f["fact_id"]))
    audit = [a for a in st.db.all("Audit") if task and a["task_id"] == task["task_id"]][-20:]
    return {"lead": lead, "task": task, "email": email, "evidence": evidence, "audit": audit}


@app.post("/api/leads/{lead_id}/resolve")
async def resolve(lead_id: str, request: Request, candidate_index: int | None = Body(default=None, embed=True)):
    return await aguard(S(request).orch.resolve_identity(lead_id, candidate_index))


@app.post("/api/suppression")
async def suppress(request: Request, email: str = Body(embed=True), reason: str = Body(default="manual", embed=True)):
    guard(S(request).orch.suppress, email, reason)
    return {"ok": True}


# ---------------------------------------------------------------- email & approval
class EditIn(BaseModel):
    subject: str = Field(max_length=MAX_SUBJECT)
    body: str = Field(max_length=MAX_BODY)


class ApproveIn(BaseModel):
    draft_version: int
    acknowledge_review: bool = False


@app.put("/api/emails/{send_key}")
async def edit_email(send_key: str, body: EditIn, request: Request):
    return guard(S(request).orch.edit_email, send_key, body.subject, body.body)


@app.post("/api/emails/{send_key}/approve")
async def approve(send_key: str, body: ApproveIn, request: Request):
    return guard(S(request).orch.approve, send_key, body.draft_version, body.acknowledge_review)


@app.post("/api/emails/{send_key}/reject")
async def reject(send_key: str, request: Request):
    return guard(S(request).orch.reject, send_key)


@app.post("/api/emails/{send_key}/reconcile")
async def reconcile(send_key: str, request: Request, outcome: str = Body(embed=True)):
    if outcome not in {"sent", "not_sent"}:
        raise HTTPException(400, "outcome harus sent atau not_sent")
    return guard(S(request).orch.reconcile, send_key, outcome)


def _eml(email: dict[str, Any], campaign: dict[str, Any]) -> bytes:
    from email.message import EmailMessage
    msg = EmailMessage()
    if email.get("to_email"):
        msg["To"] = email["to_email"]
    msg["Subject"] = " ".join((email["subject"] or "").split())  # CR/LF di header membuat EmailMessage menolak (BUG-03)
    msg["X-Unsent"] = "1"  # dibuka sebagai draf baru oleh Outlook/Thunderbird
    msg.set_content(email["body"])
    return msg.as_bytes()


@app.get("/api/emails/{send_key}/eml")
async def download_eml(send_key: str, request: Request):
    st = S(request)
    email = st.db.get("Emails", send_key)
    if not email or not email["body"]:
        raise HTTPException(404, "Draft tidak ditemukan atau masih kosong")
    campaign = st.db.get("Campaigns", email["campaign_id"])
    name = f"{email['lead_id']}-v{email['draft_version']}.eml"
    return Response(_eml(email, campaign), media_type="message/rfc822",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/campaigns/{campaign_id}/export.csv")
async def export_csv(campaign_id: str, request: Request):
    import csv
    import io
    st = S(request)
    campaign = guard(st.orch._campaign, campaign_id)
    occ = st.orch.occurrence_id(campaign)
    evidence = {}
    for f in st.db.all("Evidence"):
        evidence[f["fact_id"]] = f
    out = io.StringIO()
    w = csv.writer(out)

    def safe(value: Any) -> Any:
        """BUG-04: sel yang diawali = + - @ (atau tab/CR) dibaca Excel sebagai rumus; awali dengan tanda petik."""
        if isinstance(value, str) and value.lstrip(" ")[:1] in {"=", "+", "-", "@", "\t", "\r"}:
            return "'" + value
        return value

    w.writerow(["lead_id", "nama", "instansi", "email_penerima", "status", "keputusan_security", "versi", "subjek", "isi",
                "fakta_dipakai", "alasan_review"])
    for lead in st.db.all("Leads", campaign_id=campaign_id):
        e = st.db.get("Emails", f"{campaign_id}:{occ}:{lead['lead_id']}:step1") or {}
        facts = [f"{evidence[i]['value']} [{evidence[i]['source_url']}]" for i in e.get("used_fact_ids") or [] if i in evidence]
        reasons = [r["message"] for r in e.get("security_reasons") or [] if r["level"] != "info"]
        w.writerow([safe(v) for v in (
            lead["lead_id"], lead["name"], lead["company"] or (lead.get("hints") or {}).get("organization") or "",
            e.get("to_email", lead["email"]), e.get("status", lead["stage"]), e.get("security_decision", ""),
            e.get("draft_version", ""), e.get("subject", ""), e.get("body", ""), " | ".join(facts), " | ".join(reasons))])
    data = "\ufeff" + out.getvalue()  # BOM agar Excel membaca UTF-8
    return Response(data.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{campaign_id}-draf-email.csv"'})


@app.get("/api/campaigns/{campaign_id}/emails")
async def send_queue(campaign_id: str, request: Request):
    st = S(request)
    guard(st.orch._campaign, campaign_id)  # BUG-11: campaign tidak ada -> 404, bukan 200 []
    rows = st.db.all("Emails", campaign_id=campaign_id)
    keep = {"APPROVED", "SENDING", "SENT", "SENT_UNKNOWN", "FAILED", "NEEDS_REAPPROVAL", "NOT_SENT"}
    return sorted(({k: e[k] for k in ("send_key", "lead_id", "occurrence_id", "to_email", "subject", "schedule", "status",
                                       "gmail_id", "error", "approved_at", "updated_at")}
                   for e in rows if e["status"] in keep), key=lambda e: (e["occurrence_id"], e["lead_id"]))


# ---------------------------------------------------------------- runtime, migrasi, monitor
@app.get("/api/runtimes")
async def runtimes(request: Request):
    st = S(request)
    out = []
    for r in st.orch.runtimes.values():
        tasks = []
        for tid in list(r.running):
            t = st.db.get("Tasks", tid)
            if t:
                tasks.append({"task_id": tid, "lead_id": t["lead_id"], "stage": t["stage"], "status": t["status"],
                              "generation": t["generation"], "agent_id": t["agent_id"], "lease_until": t["lease_until"],
                              "active": tid in r.active})
        out.append({"name": r.name, "online": r.online, "capacity": r.capacity, "active": len(r.active),
                    "queued": len(r.running) - len(r.active), "completed": r.completed,
                    "avg_seconds": round(r.avg_duration(), 2), "tasks": tasks})
    return {"runtimes": out, "migrations": list(st.orch.migrations)}


@app.post("/api/runtimes/{name}/online")
async def runtime_online(name: str, request: Request, online: bool = Body(embed=True)):
    st = S(request)
    if name not in st.orch.runtimes:
        raise HTTPException(404, "Runtime tidak dikenal")
    return await st.orch.set_runtime_online(name, online)


@app.post("/api/tasks/{task_id}/migrate")
async def migrate(task_id: str, request: Request, target: str = Body(embed=True)):
    return await aguard(S(request).orch.migrate(task_id, target))


@app.get("/api/metrics")
async def metrics(request: Request):
    st = S(request)
    u = st.usage
    perf = {k.split(":", 1)[1]: v for k, v in st.bus.totals.items() if k.startswith("perf:")}
    return {"api_calls": dict(u.calls), "api_errors": dict(u.errors), "tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
            "cost_usd": round(u.cost_usd, 6), "messages": st.bus.totals.get("message", 0), "performatives": perf,
            "migrations": len(st.orch.migrations), "incidents": st.bus.totals.get("incident", 0)}


@app.get("/api/events/recent")
async def recent_events(request: Request, limit: int = 200):
    return list(S(request).bus.buffer)[-limit:]


@app.get("/api/events")
async def events(request: Request):
    st = S(request)
    queue = st.bus.subscribe()

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            st.bus.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- frontend hasil build
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Endpoint API tidak ditemukan")
        target = DIST / path
        if path and target.is_file() and DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
