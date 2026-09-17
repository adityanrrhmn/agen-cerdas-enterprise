"""Enrichment dengan actor berbasis URL LinkedIn (anchor~linkedin-profile-enrichment)."""
import asyncio
import json

import httpx

from app.agents import EnrichmentAgent, ResearchAgent, link_entity
from app.config import Settings
from app.integrations import ApifyClient, LLMResult, Usage

TEMPLATE = '{"startUrls": [{"url": "{linkedin_url}", "id": "{lead_id}"}]}'
LEAD = {"lead_id": "L7", "crm_id": "C7", "name": "Sinta Pramesti", "company": "PT Kuliner Nusantara", "domain": "",
        "title_hint": "", "linkedin_url": "https://www.linkedin.com/in/sinta-pramesti/"}
ACTOR_ITEM = {"url": "https://linkedin.com/in/sinta-pramesti", "full_name": "Sinta Pramesti",
              "headline": "Operations Manager di PT Kuliner Nusantara", "company_name": "PT Kuliner Nusantara",
              "company_industry": "Food & Beverage", "city": "Yogyakarta", "country": "Indonesia"}


def settings():
    return Settings(apify_token="t", apify_actor="anchor~linkedin-profile-enrichment", apify_input_template=TEMPLATE)


def test_lead_tanpa_linkedin_url_tidak_memanggil_apify():
    calls = []

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(201, json=[]))) as http:
            agent = EnrichmentAgent(settings(), ApifyClient(settings(), http, Usage()))
            return await agent.run({**LEAD, "linkedin_url": ""})

    out = asyncio.run(go())
    assert calls == [] and out["link"] == "not_found" and "linkedin_url" in out["reason"]
    assert [f.field for f in out["facts"]] == ["company"]  # fakta CRM tetap tersedia


def test_url_linkedin_cocok_menjadi_petunjuk_identitas_dan_output_actor_terpetakan():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json=[ACTOR_ITEM])

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await EnrichmentAgent(settings(), ApifyClient(settings(), http, Usage())).run(LEAD)

    out = asyncio.run(go())
    assert seen["body"] == {"startUrls": [{"url": LEAD["linkedin_url"], "id": "L7"}]}
    assert out["link"] == "matched", out["reason"]  # tanpa domain, URL identik memberi d=1
    facts = {f.field: f.value for f in out["facts"]}
    assert facts["title"].startswith("Operations Manager") and facts["industry"] == "Food & Beverage"
    assert facts["location"] == "Yogyakarta, Indonesia"


def test_url_linkedin_berbeda_tidak_dianggap_cocok():
    other = {"name": "Sinta Pramesti", "company": "PT Kuliner Nusantara", "domain": "",
             "profile_url": "https://linkedin.com/in/sinta-pramesti-2", "title": ""}
    s = Settings()
    assert link_entity(LEAD, [other], s.entity_accept_threshold, s.entity_min_gap).status == "ambiguous"


class Pages:
    async def search(self, query):
        return [{"url": "https://lain.example", "title": "PT Kuliner Sentosa", "description": "", "markdown": "Kuliner Sentosa buka 9 cabang."},
                {"url": "https://benar.example", "title": "Profil", "description": "", "markdown": "PT Kuliner Nusantara mengelola tiga gerai."}]


class LLM:
    def __init__(self):
        self.pages = None

    async def structured(self, system, user, name, schema, campaign_id=""):
        self.pages = [p["url"] for p in json.loads(user)["pages"]]
        return LLMResult({"facts": []}, 1, 1, 0.0, "m")


def test_riset_membuang_halaman_yang_tidak_menyebut_perusahaan_lead():
    llm = LLM()
    out = asyncio.run(ResearchAgent(Settings(), Pages(), llm).run(LEAD, {"goal": "demo", "campaign_id": "C"}))
    assert llm.pages == ["https://benar.example"] and out["irrelevant_pages"] == 1
