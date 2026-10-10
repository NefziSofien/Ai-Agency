"""Postiz auto-hébergé : canaux sociaux connectés et programmation des posts (après validation)."""

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agence import db
from agence.config import settings
from agence.storage import read_asset
from agence.tools.common import NotConfigured, as_tool_result, context, require


def _api() -> httpx.AsyncClient:
    s = settings()
    return httpx.AsyncClient(
        base_url=f"{s.postiz_url.rstrip('/')}/api/public/v1",
        headers={"Authorization": require(s.postiz_api_key, "POSTIZ_API_KEY")},
        timeout=60,
    )


async def integrations(client: dict) -> list[dict]:
    allowed = set((client.get("settings") or {}).get("postiz_integration_ids") or [])
    async with _api() as http:
        try:
            r = await http.get("/integrations")
        except httpx.ConnectError as e:
            raise NotConfigured("Postiz injoignable (docker compose --profile social up -d).") from e
        r.raise_for_status()
    items = [
        {"id": i["id"], "name": i.get("name"), "network": i.get("identifier"), "disabled": i.get("disabled")}
        for i in r.json()
    ]
    return [i for i in items if not allowed or i["id"] in allowed]


@tool
@as_tool_result
async def list_social_channels(config: RunnableConfig) -> list[dict]:
    """Liste les comptes sociaux du client connectés dans Postiz (id, nom, réseau)."""
    client, _ = context(config)
    return await integrations(client)


async def _upload(http: httpx.AsyncClient, asset_id: int) -> dict:
    row = await db.fetchone("SELECT key FROM assets WHERE id = %s", int(asset_id))
    if not row:
        raise NotConfigured(f"Asset {asset_id} introuvable.")
    data = await read_asset(row["key"])
    r = await http.post("/upload", files={"file": (row["key"].rsplit("/", 1)[-1], data)})
    r.raise_for_status()
    up = r.json()
    return {"id": up["id"], "path": up["path"]}


async def schedule_post(client: dict, payload: dict) -> dict:
    """payload : {content, date (ISO 8601), integration_ids?: [...], asset_ids?: [...]}"""
    channels = await integrations(client)
    wanted = payload.get("integration_ids") or [c["id"] for c in channels if not c["disabled"]]
    by_id = {c["id"]: c for c in channels}
    async with _api() as http:
        images = [await _upload(http, a) for a in payload.get("asset_ids") or []]
        body = {
            "type": "schedule" if payload.get("date") else "now",
            "date": payload.get("date"),
            "shortLink": False,
            "tags": [],
            "posts": [
                {
                    "integration": {"id": iid},
                    "value": [{"content": payload["content"], "image": images}],
                    "settings": {"__type": by_id.get(iid, {}).get("network")},
                }
                for iid in wanted
            ],
        }
        r = await http.post("/posts", json=body)
        r.raise_for_status()
        return r.json()
