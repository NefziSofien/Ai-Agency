from datetime import date, timedelta
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agence.config import settings
from agence.tools.common import as_tool_result, client_setting, context, require
from agence.tools.web import fetch_html


@tool
@as_tool_result
async def seo_audit(url: str) -> dict:
    """Audit SEO on-page d'une URL : title, meta description, titres, images sans alt, liens, volume de texte."""
    soup = BeautifulSoup(await fetch_html(url), "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"})
    description = meta.get("content", "") if meta else ""
    images = soup.find_all("img")
    links = soup.find_all("a", href=True)
    canonical = soup.find("link", rel="canonical")
    return {
        "url": url,
        "title": title,
        "title_length": len(title),
        "meta_description": description,
        "meta_description_length": len(description),
        "h1": [h.get_text(strip=True) for h in soup.find_all("h1")],
        "h2": [h.get_text(strip=True) for h in soup.find_all("h2")][:15],
        "word_count": len(soup.get_text(" ").split()),
        "images": len(images),
        "images_without_alt": sum(1 for i in images if not i.get("alt")),
        "internal_links": sum(1 for a in links if a["href"].startswith("/") or url.split("/")[2] in a["href"]),
        "external_links": sum(1 for a in links if a["href"].startswith("http") and url.split("/")[2] not in a["href"]),
        "canonical": canonical.get("href") if canonical else None,
        "has_viewport": bool(soup.find("meta", attrs={"name": "viewport"})),
        "lang": (soup.html or {}).get("lang") if soup.html else None,
    }


@tool
@as_tool_result
async def search_console_queries(config: RunnableConfig, days: int = 28, row_limit: int = 50) -> list:
    """Top requêtes Google Search Console du client (clics, impressions, CTR, position)."""
    client, _ = context(config)
    site = client_setting(client, "search_console_site")
    token = require(settings().google_oauth_access_token, "GOOGLE_OAUTH_ACCESS_TOKEN")
    end = date.today()
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"https://www.googleapis.com/webmasters/v3/sites/{quote(site, safe='')}/searchAnalytics/query",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "startDate": str(end - timedelta(days=days)),
                "endDate": str(end),
                "dimensions": ["query"],
                "rowLimit": row_limit,
            },
        )
        r.raise_for_status()
        return r.json().get("rows", [])
