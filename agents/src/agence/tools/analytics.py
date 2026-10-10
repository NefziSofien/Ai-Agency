import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agence.config import settings
from agence.tools.common import as_tool_result, client_setting, context, require


@tool
@as_tool_result
async def ga4_report(config: RunnableConfig, days: int = 7, dimension: str = "sessionDefaultChannelGroup") -> dict:
    """Rapport Google Analytics 4 du client : sessions, utilisateurs, conversions par canal (ou autre dimension GA4)."""
    client, _ = context(config)
    property_id = client_setting(client, "ga4_property_id")
    token = require(settings().google_oauth_access_token, "GOOGLE_OAUTH_ACCESS_TOKEN")
    body = {
        "dateRanges": [
            {"startDate": f"{days}daysAgo", "endDate": "today", "name": "current"},
            {"startDate": f"{days * 2}daysAgo", "endDate": f"{days + 1}daysAgo", "name": "previous"},
        ],
        "dimensions": [{"name": dimension}],
        "metrics": [{"name": m} for m in ("sessions", "totalUsers", "conversions", "engagementRate")],
        "limit": 25,
    }
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    headers = [h["name"] for h in data.get("dimensionHeaders", [])] + [h["name"] for h in data.get("metricHeaders", [])]
    rows = [
        dict(zip(headers, [v["value"] for v in row.get("dimensionValues", [])] + [v["value"] for v in row.get("metricValues", [])]))
        for row in data.get("rows", [])
    ]
    return {"columns": headers, "rows": rows}
