"""Adapter layanan eksternal. Adapter adalah tool, bukan agen (laporan §5.1).

Mode simulasi (`SIMULATE_INTEGRATIONS=true`) hanya untuk uji UI tanpa key; UI menandainya jelas.
"""
from __future__ import annotations

import asyncio
import base64
import json
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import BACKEND_DIR, Settings
from .google_auth import GmailOAuth, GoogleAuthError


class IntegrationError(RuntimeError):
    def __init__(self, provider: str, message: str, retryable: bool = False):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.retryable = retryable


class SkippedEnrichment(Exception):
    """Input actor tidak lengkap untuk lead ini; bukan kegagalan layanan."""


class NotConfigured(IntegrationError):
    def __init__(self, provider: str, missing: list[str]):
        super().__init__(provider, f"belum dikonfigurasi ({', '.join(missing)})")
        self.missing = missing


@dataclass
class Usage:
    calls: Counter = field(default_factory=Counter)
    errors: Counter = field(default_factory=Counter)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cost_by_campaign: Counter = field(default_factory=Counter)


@dataclass
class LLMResult:
    data: dict[str, Any]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str


def _host(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


async def _with_retry(provider: str, usage: Usage, fn, attempts: int = 3):
    for attempt in range(attempts):
        usage.calls[provider] += 1
        try:
            return await fn()
        except IntegrationError as exc:
            usage.errors[provider] += 1
            if not exc.retryable or attempt == attempts - 1:
                raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            usage.errors[provider] += 1
            if attempt == attempts - 1:
                raise IntegrationError(provider, f"jaringan: {type(exc).__name__}", retryable=True) from exc
        await asyncio.sleep(1.5 * (2 ** attempt))


def _raise_for(provider: str, resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    retryable = resp.status_code in (408, 429, 500, 502, 503, 504)
    raise IntegrationError(provider, f"HTTP {resp.status_code}: {resp.text[:240]}", retryable=retryable)


# ---------------------------------------------------------------- OpenRouter (LLM)
class OpenRouterClient:
    provider = "openrouter"

    def __init__(self, settings: Settings, client: httpx.AsyncClient, usage: Usage):
        self.s = settings
        self.client = client
        self.usage = usage

    async def structured(self, system: str, user: str, schema_name: str, schema: dict, campaign_id: str = "") -> LLMResult:
        if not self.s.configured("openrouter"):
            raise NotConfigured(self.provider, self.s.missing("openrouter"))
        payload = {
            "model": self.s.openrouter_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": self.s.llm_max_tokens,
            # Model reasoning (mis. Claude 5) memakai max_tokens untuk berpikir lebih dulu; tanpa ini
            # anggaran habis sebelum JSON selesai ditulis dan keluaran terpotong.
            "reasoning": {"enabled": False},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
        }
        headers = {
            "Authorization": f"Bearer {self.s.openrouter_api_key}",
            "HTTP-Referer": self.s.openrouter_referer,
            "X-Title": self.s.openrouter_app_name,
        }

        async def call():
            resp = await self.client.post(f"{self.s.openrouter_base_url}/chat/completions",
                                          json=payload, headers=headers, timeout=90)
            _raise_for(self.provider, resp)
            return resp.json()

        body = await _with_retry(self.provider, self.usage, call)
        if body.get("error"):
            raise IntegrationError(self.provider, str(body["error"])[:240])
        choice = body["choices"][0]
        content = choice["message"].get("content") or ""
        if choice.get("finish_reason") == "length":
            raise IntegrationError(self.provider,
                                   f"keluaran LLM terpotong pada batas {self.s.llm_max_tokens} token; "
                                   f"naikkan LLM_MAX_TOKENS di .env")
        data = parse_json_content(content)
        usage = body.get("usage") or {}
        result = LLMResult(data, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0),
                           float(usage.get("cost") or 0.0), body.get("model", self.s.openrouter_model))
        self.usage.tokens_in += result.tokens_in
        self.usage.tokens_out += result.tokens_out
        self.usage.cost_usd += result.cost_usd
        self.usage.cost_by_campaign[campaign_id] += result.cost_usd
        return result

    async def ping(self) -> str:
        resp = await self.client.get(f"{self.s.openrouter_base_url}/key",
                                     headers={"Authorization": f"Bearer {self.s.openrouter_api_key}"}, timeout=20)
        _raise_for(self.provider, resp)
        return f"key valid; model {self.s.openrouter_model}"


def parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise IntegrationError("openrouter", f"keluaran LLM bukan JSON: {text[:120]!r}")


# ---------------------------------------------------------------- Apify (enrichment)
def _fill(template: Any, values: dict[str, str]) -> Any:
    if isinstance(template, str):
        for k, v in values.items():
            template = template.replace("{" + k + "}", v)
        return template
    if isinstance(template, list):
        return [_fill(x, values) for x in template]
    if isinstance(template, dict):
        return {k: _fill(v, values) for k, v in template.items()}
    return template


def _first(item: dict, *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("name") or value.get("title")
        if value not in (None, "", []):
            return str(value)
    return ""


def normalize_linkedin(url: str) -> str:
    """linkedin.com/in/<id> tanpa protokol, www, query, atau garis miring akhir."""
    if not url:
        return ""
    url = url.strip().lower().split("?")[0].split("#")[0].rstrip("/")
    return re.sub(r"^https?://(www\.|[a-z]{2}\.)?", "", url)


def normalize_candidate(item: dict[str, Any]) -> dict[str, str]:
    name = _first(item, "fullName", "full_name", "name")
    if not name and (item.get("firstName") or item.get("lastName")):
        name = f"{item.get('firstName', '')} {item.get('lastName', '')}".strip()
    email = _first(item, "email", "workEmail")
    website = _first(item, "companyDomain", "companyWebsite", "company_website", "domain", "website", "companyUrl")
    location = _first(item, "location", "addressLocality")
    if not location:
        location = ", ".join(x for x in (_first(item, "city"), _first(item, "country")) if x)
    return {
        "name": name,
        "title": _first(item, "title", "jobTitle", "headline", "position", "occupation"),
        "company": _first(item, "companyName", "company_name", "company", "organization", "currentCompany", "organizationName"),
        "domain": _host(website) or (email.split("@")[-1].lower() if "@" in email else ""),
        "industry": _first(item, "industry", "companyIndustry", "company_industry"),
        "location": location,
        "profile_url": _first(item, "url", "profileUrl", "linkedinUrl", "linkedin", "linkedInProfileUrl"),
        "email": email,
    }


class ApifyClient:
    provider = "apify"

    def __init__(self, settings: Settings, client: httpx.AsyncClient, usage: Usage):
        self.s = settings
        self.client = client
        self.usage = usage

    async def find_people(self, lead: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
        if not self.s.configured("apify"):
            raise NotConfigured(self.provider, self.s.missing("apify"))
        actor = self.s.apify_actor.replace("/", "~")
        values = {k: str(lead.get(k) or "") for k in ("name", "company", "domain", "email", "title_hint",
                                                      "linkedin_url", "lead_id")}
        needed = set(re.findall(r"\{(\w+)\}", self.s.apify_input_template)) & set(values)
        empty = sorted(k for k in needed if not values[k])
        if empty:  # jangan membayar run actor dengan input kosong
            raise SkippedEnrichment(f"lead tidak memiliki {', '.join(empty)}; enrichment Apify dilewati")
        run_input = _fill(json.loads(self.s.apify_input_template), values)
        url = f"{self.s.apify_base_url}/acts/{actor}/run-sync-get-dataset-items"
        params = {"timeout": self.s.apify_timeout_seconds, "format": "json", "clean": "true",
                  "limit": self.s.apify_max_items}

        async def call():
            resp = await self.client.post(url, params=params, json=run_input, timeout=self.s.apify_timeout_seconds + 30,
                                          headers={"Authorization": f"Bearer {self.s.apify_token}"})
            _raise_for(self.provider, resp)
            return resp.json()

        items = await _with_retry(self.provider, self.usage, call, attempts=2)
        if not isinstance(items, list):
            raise IntegrationError(self.provider, "respons dataset bukan list")
        return [normalize_candidate(i) for i in items if isinstance(i, dict)], f"apify://{actor}"

    async def ping(self) -> str:
        resp = await self.client.get(f"{self.s.apify_base_url}/users/me",
                                     headers={"Authorization": f"Bearer {self.s.apify_token}"}, timeout=20)
        _raise_for(self.provider, resp)
        return f"token valid; actor {self.s.apify_actor or '(belum diisi)'}"


# ---------------------------------------------------------------- Firecrawl (riset)
class FirecrawlClient:
    provider = "firecrawl"

    def __init__(self, settings: Settings, client: httpx.AsyncClient, usage: Usage):
        self.s = settings
        self.client = client
        self.usage = usage

    async def search(self, query: str) -> list[dict[str, str]]:
        if not self.s.configured("firecrawl"):
            raise NotConfigured(self.provider, self.s.missing("firecrawl"))
        payload = {"query": query, "limit": self.s.firecrawl_results, "sources": ["web"],
                   "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True}}

        async def call():
            resp = await self.client.post(f"{self.s.firecrawl_base_url}/v2/search", json=payload, timeout=90,
                                          headers={"Authorization": f"Bearer {self.s.firecrawl_api_key}"})
            _raise_for(self.provider, resp)
            return resp.json()

        body = await _with_retry(self.provider, self.usage, call, attempts=2)
        data = body.get("data", [])
        results = data.get("web", []) if isinstance(data, dict) else data  # dokumentasi memuat kedua bentuk
        return [{"url": r.get("url", ""), "title": r.get("title", ""), "description": r.get("description", ""),
                 "markdown": (r.get("markdown") or "")[:8000]} for r in results if r.get("url")]

    async def ping(self) -> str:
        resp = await self.client.get(f"{self.s.firecrawl_base_url}/v2/team/credit-usage",
                                     headers={"Authorization": f"Bearer {self.s.firecrawl_api_key}"}, timeout=20)
        _raise_for(self.provider, resp)
        return "key valid"


# ---------------------------------------------------------------- Gmail (kirim)
class SendOutcome:
    SENT = "SENT"
    UNKNOWN = "SENT_UNKNOWN"
    FAILED = "FAILED"


class GmailClient:
    provider = "gmail"

    def __init__(self, settings: Settings, client: httpx.AsyncClient, usage: Usage, oauth: GmailOAuth | None):
        self.s = settings
        self.client = client
        self.usage = usage
        self.oauth = oauth

    @staticmethod
    def build_raw(sender_name: str, sender_email: str, to: str, subject: str, body: str) -> str:
        msg = EmailMessage()
        msg["From"] = formataddr((sender_name, sender_email)) if sender_name else sender_email
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        return base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")

    async def send(self, sender_name: str, to: str, subject: str, body: str) -> tuple[str, str, str]:
        """Kembalikan (outcome, gmail_id, error). Timeout setelah request terkirim = SENT_UNKNOWN."""
        if not self.s.configured("gmail") or self.oauth is None:
            raise NotConfigured(self.provider, self.s.missing("gmail"))
        sender = self.oauth.sender_email
        if not sender:
            return SendOutcome.FAILED, "", "Akun Google pengirim belum dihubungkan"
        raw = self.build_raw(sender_name, sender, to, subject, body)
        url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        for attempt in range(3):
            self.usage.calls[self.provider] += 1
            try:
                token = await self.oauth.token()
            except Exception as exc:  # belum ada request kirim: aman ditandai gagal
                self.usage.errors[self.provider] += 1
                return SendOutcome.FAILED, "", str(exc)
            try:
                resp = await self.client.post(url, json={"raw": raw}, timeout=30,
                                              headers={"Authorization": f"Bearer {token}"})
            except httpx.ConnectError as exc:
                self.usage.errors[self.provider] += 1
                if attempt < 2:  # koneksi gagal dibuat: request belum sampai
                    await asyncio.sleep(2 ** attempt)
                    continue
                return SendOutcome.FAILED, "", f"koneksi gagal: {exc}"
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                self.usage.errors[self.provider] += 1
                return SendOutcome.UNKNOWN, "", f"hasil tidak pasti: {type(exc).__name__}"
            if resp.status_code == 200:
                return SendOutcome.SENT, resp.json().get("id", ""), ""
            self.usage.errors[self.provider] += 1
            if resp.status_code in (429, 503) and attempt < 2:  # ditolak sebelum diproses: aman dicoba ulang
                await asyncio.sleep(2 ** (attempt + 1))
                continue
            if resp.status_code >= 500:
                return SendOutcome.UNKNOWN, "", f"HTTP {resp.status_code}: status kirim tidak pasti"
            return SendOutcome.FAILED, "", f"HTTP {resp.status_code}: {resp.text[:200]}"
        return SendOutcome.FAILED, "", "batas retry tercapai"

    async def ping(self) -> str:
        if self.oauth is None:
            raise NotConfigured(self.provider, self.s.missing("gmail"))
        try:
            await self.oauth.token()
        except GoogleAuthError as exc:
            raise IntegrationError(self.provider, str(exc)) from exc
        return f"terhubung sebagai {self.oauth.sender_email}; kirim {'aktif' if self.s.gmail_send_enabled else 'nonaktif'}"


# ---------------------------------------------------------------- Simulasi (uji tanpa key)
class SimulatedWorld:
    """Direktori dan halaman web fiktif. Hanya dipakai bila SIMULATE_INTEGRATIONS=true."""

    def __init__(self, path: Path = BACKEND_DIR / "data" / "simulasi.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.people = data["people"]
        self.pages = data["pages"]


class SimApify(ApifyClient):
    def __init__(self, world: SimulatedWorld, usage: Usage):
        self.world, self.usage = world, usage

    async def find_people(self, lead):
        self.usage.calls[self.provider] += 1
        await asyncio.sleep(random.uniform(0.6, 1.6))
        first = (lead.get("name") or "").split(" ")[0].lower()
        items = [p for p in self.world.people if first and p["fullName"].lower().startswith(first)]
        return [normalize_candidate(i) for i in items], "apify://simulasi"

    async def ping(self):
        return "SIMULASI"


class SimFirecrawl(FirecrawlClient):
    def __init__(self, world: SimulatedWorld, usage: Usage):
        self.world, self.usage = world, usage

    async def search(self, query):
        self.usage.calls[self.provider] += 1
        await asyncio.sleep(random.uniform(0.5, 1.2))
        q = query.lower()
        return [p for p in self.world.pages if any(tok in q for tok in p["match"])][:3]

    async def ping(self):
        return "SIMULASI"


class SimLLM(OpenRouterClient):
    """Mengembalikan keluaran deterministik berbentuk sama dengan LLM. Bukan pengganti LLM sungguhan."""

    def __init__(self, usage: Usage):
        self.usage = usage

    async def structured(self, system, user, schema_name, schema, campaign_id=""):
        self.usage.calls[self.provider] += 1
        await asyncio.sleep(random.uniform(0.4, 1.0))
        payload = json.loads(user)
        if schema_name == "profile_hint":
            desc = payload["description"]
            org = re.search(r"\b(?:di|at)\s+([A-Z][\w.&-]*(?:\s+[A-Z][\w.&-]*)*)", desc)
            role = re.split(r"\s+(?:di|at)\s+", desc)[0].strip()
            name = org.group(1) if org else ""
            data = {"organization": name, "organization_aliases": [name] if name else [], "role": role[:60], "location": ""}
            return LLMResult(data, 60, 30, 0.0, "simulasi")
        if schema_name == "research_facts":
            facts = []
            for page in payload["pages"][:2]:
                sentences = [x.strip() for x in page["content"].split(". ") if payload["company"] in x]
                sentence = sentences[-1] if sentences else page["content"].split(". ")[0].strip()
                facts.append({"field": "company_news", "value": sentence[:160], "source_url": page["url"], "quote": sentence[:160]})
            data = {"facts": facts}
        else:
            lead, facts = payload["lead"], payload["facts"]
            detail = "; ".join(f["value"] for f in facts[:2]) or payload["brief"]["goal"]
            data = {
                "subject": f"{payload['brief']['goal'][:50]} untuk {lead['company']}",
                "body": (f"Halo {lead['name']},\n\nKami memperhatikan: {detail}. Tim kami membantu perusahaan dengan "
                         f"kebutuhan serupa agar koordinasi harian lebih rapi dan tindak lanjut tidak terlewat. "
                         f"{payload['brief']['offer']}. Kami ingin memahami apakah hal ini relevan bagi tim di {lead['company']}."
                         f"\n\n{payload['brief']['cta']}\n\nSalam,\n{payload['brief']['sender_name']}"),
                "used_fact_ids": [f["fact_id"] for f in facts[:2]],
                "warnings": [],
            }
        tokens = len(user) // 4
        self.usage.tokens_in += tokens
        self.usage.tokens_out += 180
        return LLMResult(data, tokens, 180, 0.0, "simulasi")

    async def ping(self):
        return "SIMULASI"


class SimGmail(GmailClient):
    def __init__(self, settings: Settings, usage: Usage):
        self.s, self.usage, self.oauth = settings, usage, None

    async def send(self, sender_name, to, subject, body):
        self.usage.calls[self.provider] += 1
        await asyncio.sleep(0.3)
        return SendOutcome.SENT, f"sim-{int(time.time() * 1000)}", ""

    async def ping(self):
        return "SIMULASI"
