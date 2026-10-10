"""Twenty CRM et Listmonk (auto-hébergés)."""

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agence.config import settings
from agence.tools.common import NotConfigured, as_tool_result, context, require


def _twenty() -> httpx.AsyncClient:
    s = settings()
    return httpx.AsyncClient(
        base_url=f"{s.twenty_url.rstrip('/')}/rest",
        headers={"Authorization": f"Bearer {require(s.twenty_api_key, 'TWENTY_API_KEY')}"},
        timeout=30,
    )


def _listmonk() -> httpx.AsyncClient:
    s = settings()
    user = require(s.listmonk_api_user, "LISTMONK_API_USER")
    token = require(s.listmonk_api_token, "LISTMONK_API_TOKEN")
    return httpx.AsyncClient(
        base_url=f"{s.listmonk_url.rstrip('/')}/api", headers={"Authorization": f"token {user}:{token}"}, timeout=30
    )


async def _get(http: httpx.AsyncClient, path: str, **params) -> dict:
    try:
        r = await http.get(path, params=params)
    except httpx.ConnectError as e:
        raise NotConfigured(f"Service injoignable ({http.base_url}) : docker compose --profile crm up -d.") from e
    r.raise_for_status()
    return r.json()


@tool
@as_tool_result
async def crm_search_people(query: str = "", limit: int = 20) -> list:
    """Cherche des contacts dans Twenty CRM (nom, email, poste, entreprise). Vide = derniers contacts."""
    async with _twenty() as http:
        params = {"limit": limit}
        if query:
            params["filter"] = f'name.firstName[ilike]:"%{query}%"'
        data = await _get(http, "/people", **params)
    return data.get("data", {}).get("people", [])


@tool
@as_tool_result
async def crm_list_companies(limit: int = 20) -> list:
    """Liste les entreprises (prospects/clients) dans Twenty CRM."""
    async with _twenty() as http:
        data = await _get(http, "/companies", limit=limit)
    return data.get("data", {}).get("companies", [])


@tool
@as_tool_result
async def email_lists(config: RunnableConfig) -> list:
    """Listes d'emailing Listmonk disponibles (id, nom, nombre d'abonnés)."""
    client, _ = context(config)
    allowed = set((client.get("settings") or {}).get("listmonk_list_ids") or [])
    async with _listmonk() as http:
        data = await _get(http, "/lists", per_page="all")
    lists = [
        {"id": x["id"], "name": x["name"], "subscribers": x.get("subscriber_count")}
        for x in data.get("data", {}).get("results", [])
    ]
    return [x for x in lists if not allowed or x["id"] in allowed]


async def create_person(client: dict, payload: dict) -> dict:
    """payload : {first_name, last_name, email?, job_title?, linkedin?, company_name?}"""
    async with _twenty() as http:
        body = {
            "name": {"firstName": payload.get("first_name", ""), "lastName": payload.get("last_name", "")},
            "jobTitle": payload.get("job_title", ""),
        }
        if payload.get("email"):
            body["emails"] = {"primaryEmail": payload["email"]}
        if payload.get("linkedin"):
            body["linkedinLink"] = {"primaryLinkUrl": payload["linkedin"]}
        if payload.get("company_name"):
            company = await http.post("/companies", json={"name": payload["company_name"]})
            company.raise_for_status()
            body["companyId"] = company.json()["data"]["createCompany"]["id"]
        r = await http.post("/people", json=body)
        r.raise_for_status()
        return r.json()


async def create_company(client: dict, payload: dict) -> dict:
    """payload : {name, domain?}"""
    async with _twenty() as http:
        body = {"name": payload["name"]}
        if payload.get("domain"):
            body["domainName"] = {"primaryLinkUrl": payload["domain"]}
        r = await http.post("/companies", json=body)
        r.raise_for_status()
        return r.json()


async def email_campaign(client: dict, payload: dict) -> dict:
    """payload : {name, subject, body (HTML), list_ids: [...], send: bool}. Sans send=true, reste en brouillon."""
    list_ids = payload.get("list_ids") or (client.get("settings") or {}).get("listmonk_list_ids")
    if not list_ids:
        raise NotConfigured("Aucune liste Listmonk ciblée.")
    async with _listmonk() as http:
        r = await http.post(
            "/campaigns",
            json={
                "name": payload.get("name") or payload["subject"],
                "subject": payload["subject"],
                "lists": [int(x) for x in list_ids],
                "content_type": "html",
                "body": payload["body"],
                "type": "regular",
            },
        )
        r.raise_for_status()
        campaign = r.json()["data"]
        if payload.get("send"):
            s = await http.put(f"/campaigns/{campaign['id']}/status", json={"status": "running"})
            s.raise_for_status()
        return {"campaign_id": campaign["id"], "status": "running" if payload.get("send") else "draft"}
