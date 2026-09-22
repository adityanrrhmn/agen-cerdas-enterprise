"""Konfigurasi dari `.env` di root workspace. Nilai rahasia tidak pernah dikirim ke frontend."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "ya", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class Settings:
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-5"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_name: str = "Outreach Control"
    openrouter_referer: str = "http://localhost:5173"
    llm_max_tokens: int = 1200

    apify_token: str = ""
    apify_base_url: str = "https://api.apify.com/v2"
    apify_actor: str = ""
    apify_input_template: str = '{"query": "{name} {company}", "maxItems": 5}'
    apify_timeout_seconds: int = 120
    apify_max_items: int = 5

    firecrawl_api_key: str = ""
    firecrawl_base_url: str = "https://api.firecrawl.dev"
    firecrawl_results: int = 3

    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://127.0.0.1:8000/api/google/callback"
    google_token_file: Path = BACKEND_DIR / "data" / "google-oauth.json"
    google_service_account_file: str = ""
    app_url: str = "http://localhost:5173"
    sheets_spreadsheet_id: str = ""
    data_backend: str = "sheets"
    local_store_path: Path = BACKEND_DIR / "data" / "local-store.json"
    flush_seconds: float = 2.0

    gmail_send_enabled: bool = False
    gmail_allowlist: list[str] = field(default_factory=list)
    send_interval_seconds: int = 20

    simulate_integrations: bool = False
    # auto: mode draf bila GOOGLE_CLIENT_ID/SECRET belum diisi; draft: selalu draf; send: selalu mode kirim
    delivery_mode: str = "auto"

    runtime_a_workers: int = 3
    runtime_b_workers: int = 2
    batch_size: int = 25
    max_facts: int = 3
    max_revisions: int = 2
    max_retry: int = 3
    lease_seconds: int = 90
    entity_accept_threshold: float = 0.85
    entity_min_gap: float = 0.10
    default_timezone: str = "Asia/Jakarta"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])

    # ---- status integrasi (tanpa membocorkan nilai) ----
    def missing(self, integration: str) -> list[str]:
        required = {
            "openrouter": {"OPENROUTER_API_KEY": self.openrouter_api_key, "OPENROUTER_MODEL": self.openrouter_model},
            "apify": {"APIFY_TOKEN": self.apify_token, "APIFY_ENRICHMENT_ACTOR": self.apify_actor},
            "firecrawl": {"FIRECRAWL_API_KEY": self.firecrawl_api_key},
            "sheets": {
                "GOOGLE_SERVICE_ACCOUNT_FILE": self.service_account_path() is not None,
                "SHEETS_SPREADSHEET_ID": self.sheets_spreadsheet_id,
            },
            "gmail": {
                "GOOGLE_CLIENT_ID": self.google_client_id,
                "GOOGLE_CLIENT_SECRET": self.google_client_secret,
            },
        }[integration]
        return [k for k, v in required.items() if not v]

    def service_account_path(self) -> Path | None:
        """Path file JSON service account bila diisi dan ada (relatif terhadap root workspace)."""
        if not self.google_service_account_file:
            return None
        path = Path(self.google_service_account_file)
        path = path if path.is_absolute() else ROOT / path
        return path if path.is_file() else None

    def configured(self, integration: str) -> bool:
        return not self.missing(integration)

    @property
    def draft_only(self) -> bool:
        """Mode draf: aplikasi hanya menyusun isi email; tidak ada antrean kirim."""
        if self.delivery_mode == "draft":
            return True
        if self.delivery_mode == "send":
            return False
        return not self.configured("gmail") and not self.simulate_integrations

    def recipient_allowed(self, email: str) -> bool:
        email = email.strip().lower()
        for entry in self.gmail_allowlist:
            entry = entry.strip().lower()
            if not entry:
                continue
            if entry.startswith("@") and email.endswith(entry):
                return True
            if email == entry:
                return True
        return False


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env", override=False)
    template = _str("APIFY_ENRICHMENT_INPUT", Settings.apify_input_template)
    json.loads(template)  # gagal cepat bila template bukan JSON
    return Settings(
        openrouter_api_key=_str("OPENROUTER_API_KEY"),
        openrouter_model=_str("OPENROUTER_MODEL", Settings.openrouter_model),
        openrouter_base_url=_str("OPENROUTER_BASE_URL", Settings.openrouter_base_url).rstrip("/"),
        openrouter_app_name=_str("OPENROUTER_APP_NAME", Settings.openrouter_app_name),
        openrouter_referer=_str("OPENROUTER_REFERER", Settings.openrouter_referer),
        llm_max_tokens=_int("LLM_MAX_TOKENS", 1200),
        apify_token=_str("APIFY_TOKEN"),
        apify_actor=_str("APIFY_ENRICHMENT_ACTOR"),
        apify_input_template=template,
        apify_timeout_seconds=_int("APIFY_TIMEOUT_SECONDS", 120),
        apify_max_items=_int("APIFY_MAX_ITEMS", 5),
        firecrawl_api_key=_str("FIRECRAWL_API_KEY"),
        firecrawl_results=_int("FIRECRAWL_RESULTS_PER_LEAD", 3),
        google_client_id=_str("GOOGLE_CLIENT_ID"),
        google_client_secret=_str("GOOGLE_CLIENT_SECRET"),
        google_oauth_redirect_uri=_str("GOOGLE_OAUTH_REDIRECT_URI", Settings.google_oauth_redirect_uri),
        google_service_account_file=_str("GOOGLE_SERVICE_ACCOUNT_FILE"),
        app_url=_str("APP_URL", Settings.app_url).rstrip("/"),
        sheets_spreadsheet_id=_str("SHEETS_SPREADSHEET_ID"),
        data_backend=_str("DATA_BACKEND", "sheets").lower(),
        flush_seconds=_float("SHEETS_FLUSH_SECONDS", 2.0),
        gmail_send_enabled=_bool("GMAIL_SEND_ENABLED"),
        gmail_allowlist=[x for x in _str("GMAIL_ALLOWLIST").split(",") if x.strip()],
        send_interval_seconds=_int("SEND_INTERVAL_SECONDS", 20),
        simulate_integrations=_bool("SIMULATE_INTEGRATIONS"),
        delivery_mode=(_str("DELIVERY_MODE", "auto").lower() if _str("DELIVERY_MODE", "auto").lower() in {"auto", "draft", "send"} else "auto"),
        runtime_a_workers=_int("RUNTIME_A_WORKERS", 3),
        runtime_b_workers=_int("RUNTIME_B_WORKERS", 2),
        batch_size=_int("BATCH_SIZE", 25),
        max_facts=_int("MAX_FACTS", 3),
        max_revisions=_int("MAX_REVISIONS", 2),
        max_retry=_int("MAX_RETRY", 3),
        lease_seconds=_int("LEASE_SECONDS", 90),
        entity_accept_threshold=_float("ENTITY_ACCEPT_THRESHOLD", 0.85),
        entity_min_gap=_float("ENTITY_MIN_GAP", 0.10),
        default_timezone=_str("DEFAULT_TIMEZONE", "Asia/Jakarta"),
        cors_origins=[x.strip() for x in _str("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()],
    )
