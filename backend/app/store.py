"""Data Gateway single-writer (laporan §7.1).

Semua agen dan layanan membaca/menulis state lewat `DataGateway`. State dimuat ke memori saat start,
perubahan ditandai kotor lalu di-flush berkala sebagai satu `values:batchUpdate` ke Google Sheets
(atau ke file JSON lokal bila Sheets belum dikonfigurasi). Ini bukan transaksi lintas layanan:
hanya ada satu proses penulis, dan kolom state tidak boleh diedit manual saat aplikasi berjalan.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from .config import Settings
from .google_auth import ServiceAccountTokenProvider

log = logging.getLogger(__name__)

# Kolom mengikuti tabel §7.1 laporan, ditambah kolom operasional yang dibutuhkan implementasi.
TABS: dict[str, list[str]] = {
    "Campaigns": [
        "campaign_id", "name", "goal", "offer", "cta", "personalization", "cadence", "max_occurrences",
        "count", "max_recipients", "timezone", "schedule", "budget", "sender_name", "sender_email", "template_id",
        "status", "current_occurrence", "approval_hash", "created_at", "updated_at",
    ],
    "Leads": [
        "lead_id", "campaign_id", "crm_id", "name", "email", "company", "domain", "title_hint", "linkedin_url",
        "description", "hints", "permission_status", "permission_ref", "stage", "decision", "reasons", "match_score",
        "candidates", "identity", "updated_at",
    ],
    "Evidence": [
        "fact_id", "lead_id", "field", "value", "source_url", "retrieved_at", "match_score",
        "source_type", "quote", "selected",
    ],
    "Templates": ["template_id", "version", "goal", "language", "subject", "body"],
    "Tasks": [
        "task_id", "campaign_id", "lead_id", "occurrence_id", "stage", "status", "agent_id", "host",
        "payload_ref", "checkpoint", "generation", "lease_until", "retry", "next_run", "error",
        "started_at", "updated_at",
    ],
    "Emails": [
        "send_key", "campaign_id", "occurrence_id", "lead_id", "to_email", "subject", "body",
        "used_fact_ids", "warnings", "draft_version", "security_decision", "security_reasons",
        "approval_hash", "approved_at", "schedule", "gmail_id", "status", "error", "llm_model",
        "tokens_in", "tokens_out", "cost_usd", "updated_at",
    ],
    "Suppression": ["email", "reason", "recorded_at"],
    "Audit": ["event_id", "task_id", "actor", "timestamp", "change_summary"],
}
KEYS = {
    "Campaigns": "campaign_id", "Leads": "lead_id", "Evidence": "fact_id", "Templates": "template_id",
    "Tasks": "task_id", "Emails": "send_key", "Suppression": "email", "Audit": "event_id",
}
JSON_COLS = {"reasons", "candidates", "identity", "hints", "checkpoint", "used_fact_ids", "warnings", "security_reasons"}
INT_COLS = {"count", "max_recipients", "generation", "retry", "draft_version", "tokens_in", "tokens_out", "max_occurrences",
            "current_occurrence", "version"}
FLOAT_COLS = {"budget", "match_score", "cost_usd", "lease_until"}
BOOL_COLS = {"selected"}


def encode(col: str, value: Any) -> str:
    if value is None:
        return ""
    if col in JSON_COLS:
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    text = str(value)
    return text[:45000]  # batas sel Sheets 50.000 karakter


def decode(col: str, raw: Any) -> Any:
    if raw is None or raw == "":
        return [] if col in {"used_fact_ids", "warnings", "reasons", "security_reasons", "candidates"} else None
    raw = str(raw)
    try:
        if col in JSON_COLS:
            return json.loads(raw)
        if col in INT_COLS:
            return int(float(raw))
        if col in FLOAT_COLS:
            return float(raw)
        if col in BOOL_COLS:
            return raw.strip().upper() in {"TRUE", "1", "YA"}
    except (ValueError, json.JSONDecodeError):
        log.warning("Nilai kolom %s tidak valid: %.40s", col, raw)
        return None
    return raw


class Backend(Protocol):
    name: str

    async def load(self) -> dict[str, tuple[list[str], list[dict[str, Any]]]]: ...
    async def write(self, headers: dict[str, list[str]], rows: dict[str, list[tuple[int, dict[str, Any]]]]) -> None: ...


class LocalBackend:
    """File JSON lokal: dipakai saat Sheets belum dikonfigurasi dan untuk pengujian."""

    name = "local"

    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, list[dict[str, Any]]] = {}

    async def load(self):
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        return {tab: (list(TABS[tab]), [dict(r) for r in self._data.get(tab, [])]) for tab in TABS}

    async def write(self, headers, rows):
        for tab, items in rows.items():
            table = self._data.setdefault(tab, [])
            for index, row in items:
                while len(table) <= index:
                    table.append({})
                table[index] = {k: encode(k, v) for k, v in row.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)


class SheetsBackend:
    """Google Sheets API v4. Kuota tulis dihemat dengan satu batchUpdate per flush."""

    name = "sheets"
    base = "https://sheets.googleapis.com/v4/spreadsheets"

    def __init__(self, settings: Settings, tokens: ServiceAccountTokenProvider, client: httpx.AsyncClient):
        self.sid = settings.sheets_spreadsheet_id
        self.tokens = tokens
        self.client = client

    async def _request(self, method: str, url: str, **kw) -> dict:
        for attempt in range(4):
            headers = {"Authorization": f"Bearer {await self.tokens.token()}"}
            resp = await self.client.request(method, url, headers=headers, timeout=30, **kw)
            if resp.status_code in (429, 500, 502, 503) and attempt < 3:
                await asyncio.sleep(2 ** attempt)
                continue
            if resp.status_code == 403:
                raise RuntimeError("Sheets API 403: bagikan spreadsheet ke email service account sebagai Editor, "
                                   "dan pastikan Google Sheets API aktif di project")
            if resp.status_code == 404:
                raise RuntimeError("Sheets API 404: SHEETS_SPREADSHEET_ID tidak ditemukan")
            if resp.status_code >= 400:
                raise RuntimeError(f"Sheets API {resp.status_code}: {resp.text[:300]}")
            return resp.json() if resp.content else {}
        raise RuntimeError("Sheets API gagal setelah retry")

    async def load(self):
        meta = await self._request("GET", f"{self.base}/{self.sid}", params={"fields": "sheets.properties.title"})
        existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
        missing = [tab for tab in TABS if tab not in existing]
        if missing:
            await self._request("POST", f"{self.base}/{self.sid}:batchUpdate", json={
                "requests": [{"addSheet": {"properties": {"title": tab}}} for tab in missing]})
        got = await self._request("GET", f"{self.base}/{self.sid}/values:batchGet",
                                  params=[("ranges", f"{tab}!A1:AZ") for tab in TABS] + [("majorDimension", "ROWS")])
        result = {}
        header_updates = []
        for tab, vr in zip(TABS, got.get("valueRanges", [])):
            values = vr.get("values", [])
            header = [h.strip() for h in values[0]] if values else []
            full = header + [c for c in TABS[tab] if c not in header]
            if full != header:
                header_updates.append({"range": f"{tab}!A1", "values": [full]})
            rows = []
            for raw in values[1:]:
                rows.append({col: (raw[i] if i < len(raw) else "") for i, col in enumerate(full)})
            result[tab] = (full, rows)
        if header_updates:
            await self._request("POST", f"{self.base}/{self.sid}/values:batchUpdate",
                                json={"valueInputOption": "RAW", "data": header_updates})
        return result

    async def write(self, headers, rows):
        data = []
        for tab, items in rows.items():
            cols = headers[tab]
            for index, row in items:
                data.append({"range": f"{tab}!A{index + 2}", "values": [[encode(c, row.get(c)) for c in cols]]})
        if data:
            await self._request("POST", f"{self.base}/{self.sid}/values:batchUpdate",
                                json={"valueInputOption": "RAW", "data": data})


@dataclass
class _Table:
    header: list[str]
    rows: list[dict[str, Any]]
    index: dict[str, int]


class DataGateway:
    def __init__(self, backend: Backend, flush_seconds: float = 2.0):
        self.backend = backend
        self.flush_seconds = flush_seconds
        self.tables: dict[str, _Table] = {}
        self._dirty: dict[str, set[int]] = {tab: set() for tab in TABS}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.last_flush_error: str | None = None
        self.last_flush_at: float | None = None

    async def start(self, background: bool = True) -> None:
        loaded = await self.backend.load()
        for tab, (header, raw_rows) in loaded.items():
            rows = [{c: decode(c, r.get(c)) for c in header} for r in raw_rows]
            key = KEYS[tab]
            self.tables[tab] = _Table(header, rows, {r[key]: i for i, r in enumerate(rows) if r.get(key)})
        if background:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await self.flush()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.flush_seconds)
            try:
                await self.flush()
            except Exception as exc:  # flush berikutnya mencoba lagi; state tetap di memori
                self.last_flush_error = str(exc)
                log.exception("Flush gagal")

    async def flush(self) -> None:
        async with self._lock:
            pending = {tab: sorted(idx) for tab, idx in self._dirty.items() if idx}
            if not pending:
                return
            snapshot = {tab: [(i, dict(self.tables[tab].rows[i])) for i in idx] for tab, idx in pending.items()}
            headers = {tab: self.tables[tab].header for tab in TABS}
            # Tandai bersih sebelum menulis: perubahan selama await akan menandai kotor lagi.
            for tab, idx in pending.items():
                self._dirty[tab].difference_update(idx)
            try:
                await self.backend.write(headers, snapshot)
            except Exception:
                for tab, idx in pending.items():
                    self._dirty[tab].update(idx)
                raise
            self.last_flush_error = None
            self.last_flush_at = time.time()

    # ---- operasi baca/tulis (sinkron: aman di satu event loop) ----
    def get(self, tab: str, key: str) -> dict[str, Any] | None:
        t = self.tables[tab]
        i = t.index.get(key)
        return dict(t.rows[i]) if i is not None else None

    def all(self, tab: str, **where: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in self.tables[tab].rows
                if r.get(KEYS[tab]) and all(r.get(k) == v for k, v in where.items())]

    def upsert(self, tab: str, row: dict[str, Any]) -> dict[str, Any]:
        t = self.tables[tab]
        key = row[KEYS[tab]]
        unknown = set(row) - set(t.header)
        if unknown:
            raise KeyError(f"Kolom tidak dikenal di {tab}: {sorted(unknown)}")
        if key in t.index:
            i = t.index[key]
            t.rows[i].update(row)
        else:
            i = len(t.rows)
            t.rows.append({c: None for c in t.header} | row)
            t.index[key] = i
        self._dirty[tab].add(i)
        return dict(t.rows[i])

    def pending_writes(self) -> int:
        return sum(len(v) for v in self._dirty.values())
