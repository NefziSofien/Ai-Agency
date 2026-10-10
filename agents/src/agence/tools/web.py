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


async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 AgenceIA"}) as http:
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
