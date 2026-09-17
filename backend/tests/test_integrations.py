"""Bentuk request ke layanan eksternal diuji dengan transport tiruan (tanpa key, tanpa jaringan)."""
import asyncio
import base64
import email
import json

import httpx
import pytest

from app.config import Settings
from app.google_auth import GMAIL_SEND_SCOPE, GmailOAuth, GoogleAuthError, ServiceAccountTokenProvider
from app.integrations import ApifyClient, GmailClient, OpenRouterClient, SendOutcome, Usage
from app.store import TABS, DataGateway, LocalBackend, SheetsBackend


def run(coro):
    return asyncio.run(coro)


def token_ok(request: httpx.Request):
    if request.url.host == "oauth2.googleapis.com":
        return httpx.Response(200, json={"access_token": "ya29.test", "expires_in": 3600,
                                         "scope": "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/gmail.send"})
    return None


def test_openrouter_memakai_structured_output_tanpa_temperature():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"model": "anthropic/claude-sonnet-5", "choices": [{"message": {"content": '{"a": 1}'}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0002}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            usage = Usage()
            client = OpenRouterClient(Settings(openrouter_api_key="sk-or-test"), http, usage)
            res = await client.structured("sys", "usr", "x", {"type": "object"}, "C1")
            return res, usage

    res, usage = run(go())
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert seen["body"]["response_format"]["json_schema"]["strict"] is True
    assert "temperature" not in seen["body"]
    assert seen["auth"] == "Bearer sk-or-test"
    assert res.data == {"a": 1} and usage.cost_by_campaign["C1"] == 0.0002


def test_apify_run_sync_dengan_template_input():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(201, json=[{"fullName": "Sinta Pramesti", "jobTitle": "Operations Manager",
                                          "companyName": "PT Kuliner Nusantara", "companyWebsite": "https://www.kuliner-nusantara.example/"}])

    s = Settings(apify_token="apify_api_x", apify_actor="user/people-finder",
                 apify_input_template='{"queries": ["{name} {company}"], "maxItems": 5}')

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await ApifyClient(s, http, Usage()).find_people({"name": "Sinta Pramesti", "company": "PT Kuliner Nusantara"})

    cands, _ = run(go())
    assert seen["path"] == "/v2/acts/user~people-finder/run-sync-get-dataset-items"
    assert seen["body"] == {"queries": ["Sinta Pramesti PT Kuliner Nusantara"], "maxItems": 5}
    assert seen["auth"] == "Bearer apify_api_x" and seen["params"]["format"] == "json"
    assert cands[0]["domain"] == "kuliner-nusantara.example" and cands[0]["title"] == "Operations Manager"


def _gmail(handler, tmp_path):
    s = Settings(google_client_id="id", google_client_secret="secret")
    token_file = tmp_path / "google-oauth.json"
    token_file.write_text(json.dumps({"refresh_token": "rt", "email": "tim@contoh.example"}))

    async def go():
        def route(request):
            return token_ok(request) or handler(request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as http:
            oauth = GmailOAuth("id", "secret", "http://127.0.0.1:8000/api/google/callback", token_file, http)
            return await GmailClient(s, http, Usage(), oauth).send("Tim Penjualan", "sinta@contoh.example", "Subjek", "Isi email")
    return run(go())


def test_gmail_terkirim_membawa_mime_yang_benar(tmp_path):
    seen = {}

    def handler(request):
        raw = json.loads(request.content)["raw"]
        seen["msg"] = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        return httpx.Response(200, json={"id": "18f0abc", "threadId": "t"})

    outcome, gid, _ = _gmail(handler, tmp_path)
    assert (outcome, gid) == (SendOutcome.SENT, "18f0abc")
    assert seen["msg"]["To"] == "sinta@contoh.example" and seen["msg"]["Subject"] == "Subjek"
    assert "tim@contoh.example" in seen["msg"]["From"]


def test_gmail_timeout_menjadi_sent_unknown_bukan_kirim_ulang(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("timeout", request=request)

    outcome, _, _ = _gmail(handler, tmp_path)
    assert outcome == SendOutcome.UNKNOWN and len(calls) == 1


def test_gmail_400_gagal_tanpa_retry(tmp_path):
    outcome, _, err = _gmail(lambda r: httpx.Response(400, json={"error": "invalid"}), tmp_path)
    assert outcome == SendOutcome.FAILED and "400" in err


def test_sheets_membuat_tab_header_dan_menulis_baris_yang_tepat(tmp_path):
    calls = []

    def handler(request):
        if (t := token_ok(request)) is not None:
            return t
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("SID") and request.method == "GET":
            return httpx.Response(200, json={"sheets": [{"properties": {"title": "Leads"}}]})
        if request.url.path.endswith("values:batchGet"):
            ranges = request.url.params.get_list("ranges")
            vr = [{"range": r, "values": [["lead_id", "name"], ["L1", "Sinta"]]} if r.startswith("Leads") else {"range": r} for r in ranges]
            return httpx.Response(200, json={"valueRanges": vr})
        return httpx.Response(200, json={})

    s = Settings(sheets_spreadsheet_id="SID")
    key_file = service_account_file(tmp_path)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            gw = DataGateway(SheetsBackend(s, ServiceAccountTokenProvider(key_file, ["scope"], http), http))
            await gw.start(background=False)
            assert gw.get("Leads", "L1")["name"] == "Sinta"
            gw.upsert("Leads", {"lead_id": "L2", "name": "Budi"})
            gw.upsert("Leads", {"lead_id": "L1", "stage": "enriched"})
            await gw.flush()

    run(go())
    add_sheet = [c for c in calls if c[1].endswith(":batchUpdate") and "requests" in (c[2] or {})][0]
    assert {r["addSheet"]["properties"]["title"] for r in add_sheet[2]["requests"]} == set(TABS) - {"Leads"}
    writes = [c[2]["data"] for c in calls if c[1].endswith("values:batchUpdate")]
    header_fix = writes[0]
    assert any(d["range"] == "Leads!A1" and d["values"][0][:2] == ["lead_id", "name"] for d in header_fix)
    ranges = {d["range"] for d in writes[-1]}
    assert ranges == {"Leads!A2", "Leads!A3"}  # L1 baris 2 (update), L2 baris 3 (baru)


def test_local_backend_round_trip(tmp_path):
    async def go():
        gw = DataGateway(LocalBackend(tmp_path / "db.json"))
        await gw.start(background=False)
        gw.upsert("Emails", {"send_key": "k", "used_fact_ids": ["F1"], "draft_version": 2, "cost_usd": 0.01})
        await gw.flush()
        gw2 = DataGateway(LocalBackend(tmp_path / "db.json"))
        await gw2.start(background=False)
        return gw2.get("Emails", "k")

    row = run(go())
    assert row["used_fact_ids"] == ["F1"] and row["draft_version"] == 2 and row["cost_usd"] == 0.01


def service_account_file(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    path = tmp_path / "sa.json"
    path.write_text(json.dumps({"type": "service_account", "client_email": "outreach@proj.iam.gserviceaccount.com",
                                "private_key": pem, "private_key_id": "k1",
                                "token_uri": "https://oauth2.googleapis.com/token"}))
    return path


def test_service_account_memakai_jwt_bearer_tanpa_refresh_token(tmp_path):
    seen = {}

    def handler(request):
        seen.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"access_token": "ya29.sa", "expires_in": 3600})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            p = ServiceAccountTokenProvider(service_account_file(tmp_path),
                                            ["https://www.googleapis.com/auth/spreadsheets"], http)
            return await p.token(), await p.token(), p.email

    tok1, tok2, email_addr = run(go())
    assert tok1 == tok2 == "ya29.sa" and email_addr.endswith("iam.gserviceaccount.com")
    assert seen["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    payload = seen["assertion"].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    assert claims["scope"] == "https://www.googleapis.com/auth/spreadsheets" and claims["aud"].endswith("/token")
    assert "refresh_token" not in seen


def _id_token(email_addr):
    body = base64.urlsafe_b64encode(json.dumps({"email": email_addr, "email_verified": True}).encode()).decode().rstrip("=")
    return f"h.{body}.s"


def test_hubungkan_google_menyimpan_pengirim_dan_menolak_state_asing(tmp_path):
    from urllib.parse import parse_qs, urlparse
    token_file = tmp_path / "google-oauth.json"
    seen = {}

    def handler(request):
        if request.url.path == "/revoke":
            seen["revoked"] = True
            return httpx.Response(200)
        seen["exchange"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(200, json={"access_token": "a", "expires_in": 3600, "refresh_token": "rt-baru",
                                         "scope": f"{GMAIL_SEND_SCOPE} openid email",
                                         "id_token": _id_token("tim@gmail.com")})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            oauth = GmailOAuth("cid", "sec", "http://127.0.0.1:8000/api/google/callback", token_file, http)
            q = parse_qs(urlparse(oauth.authorization_url()).query)
            assert q["access_type"] == ["offline"] and q["code_challenge_method"] == ["S256"]
            assert GMAIL_SEND_SCOPE in q["scope"][0]
            with pytest.raises(GoogleAuthError):
                await oauth.complete("state-asing", "code")
            status = await oauth.complete(q["state"][0], "code-1")
            assert status["connected"] and status["email"] == "tim@gmail.com"
            assert seen["exchange"]["code_verifier"]
            assert seen["exchange"]["redirect_uri"].endswith("/api/google/callback")
            with pytest.raises(GoogleAuthError):  # state sekali pakai
                await oauth.complete(q["state"][0], "code-1")
            await oauth.disconnect()
            assert not token_file.exists() and seen["revoked"]

    run(go())


def test_hubungkan_google_ditolak_tanpa_izin_kirim(tmp_path):
    from urllib.parse import parse_qs, urlparse

    def handler(request):
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "scope": "openid email"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            oauth = GmailOAuth("cid", "sec", "http://127.0.0.1:8000/cb", tmp_path / "t.json", http)
            state = parse_qs(urlparse(oauth.authorization_url()).query)["state"][0]
            with pytest.raises(GoogleAuthError, match="kirim email"):
                await oauth.complete(state, "code")
            assert not (tmp_path / "t.json").exists()

    run(go())
