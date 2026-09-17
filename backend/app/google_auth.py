"""Autentikasi Google.

- Sheets: service account (file JSON). Spreadsheet di-share ke email service account; tidak ada refresh token manual.
- Gmail: pengguna menekan "Hubungkan akun Google" di dashboard (OAuth + PKCE). Token disimpan backend di
  `backend/data/google-oauth.json` (di-gitignore) dan diperbarui otomatis; tidak perlu disalin ke .env.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
from google.auth import crypt, jwt

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_SCOPES = [GMAIL_SEND_SCOPE, "openid", "email"]


class GoogleAuthError(RuntimeError):
    pass


class ServiceAccountTokenProvider:
    """Access token dari service account lewat JWT bearer grant (RFC 7523)."""

    def __init__(self, key_file: Path, scopes: list[str], client: httpx.AsyncClient):
        self.key_file, self.scopes, self.client = key_file, scopes, client
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()

    def info(self) -> dict[str, Any]:
        try:
            data = json.loads(self.key_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GoogleAuthError(f"File service account tidak dapat dibaca: {self.key_file.name}") from exc
        if data.get("type") != "service_account" or not data.get("private_key") or not data.get("client_email"):
            raise GoogleAuthError("File JSON bukan kunci service account yang valid")
        return data

    @property
    def email(self) -> str:
        return self.info()["client_email"]

    async def token(self) -> str:
        async with self._lock:
            if self._token and time.time() < self._expires - 60:
                return self._token
            info = self.info()
            now = int(time.time())
            assertion = jwt.encode(crypt.RSASigner.from_service_account_info(info), {
                "iss": info["client_email"], "scope": " ".join(self.scopes), "aud": TOKEN_URL,
                "iat": now, "exp": now + 3600,
            })
            resp = await self.client.post(TOKEN_URL, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion.decode() if isinstance(assertion, bytes) else assertion,
            }, timeout=20)
            if resp.status_code != 200:
                raise GoogleAuthError(f"Token service account ditolak Google (HTTP {resp.status_code}): {_error_code(resp)}")
            body = resp.json()
            self._token = body["access_token"]
            self._expires = time.time() + int(body.get("expires_in", 3600))
            return self._token


def _error_code(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return str(body.get("error_description") or body.get("error") or resp.status_code)
    except ValueError:
        return str(resp.status_code)


def _id_token_email(id_token: str) -> str:
    """Email dari id_token yang diterima langsung dari endpoint token Google via TLS (OIDC §3.1.3.7)."""
    try:
        payload = id_token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return data.get("email", "") if data.get("email_verified", True) else ""
    except (IndexError, ValueError):
        return ""


class GmailOAuth:
    """Koneksi akun Google pengirim. Refresh token hanya hidup di file privat backend."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, token_file: Path, client: httpx.AsyncClient):
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri
        self.token_file, self.client = token_file, client
        self._pending: dict[str, tuple[str, float]] = {}  # state -> (code_verifier, dibuat)
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()

    # ---- status
    def stored(self) -> dict[str, Any] | None:
        if not self.token_file.exists():
            return None
        try:
            return json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def status(self) -> dict[str, Any]:
        data = self.stored() or {}
        return {"connected": bool(data.get("refresh_token")), "email": data.get("email", ""),
                "connected_at": data.get("connected_at"), "scopes": data.get("scopes", [])}

    @property
    def sender_email(self) -> str:
        return (self.stored() or {}).get("email", "")

    # ---- alur OAuth
    def authorization_url(self) -> str:
        now = time.time()
        self._pending = {s: v for s, v in self._pending.items() if now - v[1] < 600}
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(64)
        self._pending[state] = (verifier, now)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id, "redirect_uri": self.redirect_uri, "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES), "access_type": "offline", "prompt": "consent",
            "include_granted_scopes": "true", "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256",
        })

    async def complete(self, state: str, code: str) -> dict[str, Any]:
        pending = self._pending.pop(state, None)
        if not pending or time.time() - pending[1] > 600:
            raise GoogleAuthError("Sesi login kedaluwarsa atau tidak dikenal. Ulangi dari tombol Hubungkan.")
        resp = await self.client.post(TOKEN_URL, data={
            "code": code, "client_id": self.client_id, "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri, "grant_type": "authorization_code", "code_verifier": pending[0],
        }, timeout=20)
        if resp.status_code != 200:
            raise GoogleAuthError(f"Google menolak kode login: {_error_code(resp)}")
        body = resp.json()
        scopes = body.get("scope", "").split()
        if GMAIL_SEND_SCOPE not in scopes:
            raise GoogleAuthError("Izin 'kirim email' tidak dicentang saat login. Ulangi dan setujui izin tersebut.")
        refresh = body.get("refresh_token") or (self.stored() or {}).get("refresh_token")
        if not refresh:
            raise GoogleAuthError("Google tidak memberi refresh token. Cabut akses aplikasi di myaccount.google.com/permissions lalu ulangi.")
        data = {"refresh_token": refresh, "email": _id_token_email(body.get("id_token", "")), "scopes": scopes,
                "connected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps(data), encoding="utf-8")
        self._token = body.get("access_token")
        self._expires = time.time() + int(body.get("expires_in", 3600))
        return self.status()

    async def disconnect(self) -> None:
        data = self.stored()
        if data and data.get("refresh_token"):
            try:
                await self.client.post(REVOKE_URL, params={"token": data["refresh_token"]}, timeout=15)
            except httpx.HTTPError:
                pass  # file tetap dihapus; akses juga bisa dicabut dari akun Google
        self.token_file.unlink(missing_ok=True)
        self._token, self._expires = None, 0.0

    async def token(self) -> str:
        async with self._lock:
            if self._token and time.time() < self._expires - 60:
                return self._token
            data = self.stored()
            if not data or not data.get("refresh_token"):
                raise GoogleAuthError("Akun Google pengirim belum dihubungkan")
            resp = await self.client.post(TOKEN_URL, data={
                "client_id": self.client_id, "client_secret": self.client_secret,
                "refresh_token": data["refresh_token"], "grant_type": "refresh_token",
            }, timeout=20)
            if resp.status_code != 200:
                raise GoogleAuthError(f"Koneksi Google kedaluwarsa ({_error_code(resp)}). Hubungkan ulang akun di tab Koneksi.")
            body = resp.json()
            self._token = body["access_token"]
            self._expires = time.time() + int(body.get("expires_in", 3600))
            return self._token
