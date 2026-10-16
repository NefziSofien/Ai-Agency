import asyncio
import ipaddress
import socket

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from agence.config import settings
from agence.tools.common import NotConfigured, as_tool_result


@tool
@as_tool_result
async def web_search(query: str, max_results: int = 8) -> list[dict]:
    """Recherche web (SearXNG local, ou Tavily si configuré). Retourne titre, URL et extrait."""
    s = settings()
    async with httpx.AsyncClient(timeout=30) as http:
        if s.tavily_api_key:
            r = await http.post(
                "https://api.tavily.com/search",
                json={"api_key": s.tavily_api_key, "query": query, "max_results": max_results},
            )
            r.raise_for_status()
            return [{"title": x["title"], "url": x["url"], "snippet": x["content"]} for x in r.json()["results"]]
        try:
            r = await http.get(f"{s.searxng_url}/search", params={"q": query, "format": "json"})
        except httpx.ConnectError as e:
            raise NotConfigured("SearXNG injoignable (docker compose --profile core up -d).") from e
        r.raise_for_status()
        return [
            {"title": x.get("title"), "url": x.get("url"), "snippet": x.get("content")}
            for x in r.json().get("results", [])[:max_results]
        ]


async def _check_public_url(request: httpx.Request) -> None:
    """Anti-SSRF : refuse les URL (et redirections) vers le réseau local, les métadonnées cloud ou un schéma non HTTP."""
    if request.url.scheme not in ("http", "https"):
        raise httpx.RequestError(f"Schéma refusé : {request.url.scheme}")
    host = request.url.host
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise httpx.RequestError(f"Hôte introuvable : {host}") from e
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise httpx.RequestError(f"Adresse non publique refusée : {host}")


async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 AgenceIA"},
        event_hooks={"request": [_check_public_url]},
    ) as http:
        r = await http.get(url)
        r.raise_for_status()
        return r.text


@tool
@as_tool_result
async def fetch_page(url: str) -> str:
    """Lit le texte principal d'une page web (concurrent, article, page produit)."""
    soup = BeautifulSoup(await fetch_html(url), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:8000]
