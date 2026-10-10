"""Google Ads et Meta Ads : lecture des performances, création de campagnes en PAUSE uniquement."""

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agence.config import settings
from agence.tools.common import as_tool_result, client_setting, context, require


def _google_headers() -> dict:
    s = settings()
    headers = {
        "Authorization": f"Bearer {require(s.google_oauth_access_token, 'GOOGLE_OAUTH_ACCESS_TOKEN')}",
        "developer-token": require(s.google_ads_developer_token, "GOOGLE_ADS_DEVELOPER_TOKEN"),
    }
    if s.google_ads_login_customer_id:
        headers["login-customer-id"] = s.google_ads_login_customer_id.replace("-", "")
    return headers


def _google_base(customer_id: str) -> str:
    return f"https://googleads.googleapis.com/{settings().google_ads_api_version}/customers/{customer_id.replace('-', '')}"


@tool
@as_tool_result
async def google_ads_campaign_metrics(config: RunnableConfig, period: str = "LAST_30_DAYS") -> list:
    """Performances des campagnes Google Ads du client (coût, clics, impressions, conversions)."""
    client, _ = context(config)
    customer_id = client_setting(client, "google_ads_customer_id")
    query = (
        "SELECT campaign.name, campaign.status, metrics.cost_micros, metrics.clicks, metrics.impressions,"
        f" metrics.ctr, metrics.conversions FROM campaign WHERE segments.date DURING {period}"
    )
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(f"{_google_base(customer_id)}/googleAds:search", headers=_google_headers(), json={"query": query})
        r.raise_for_status()
        return r.json().get("results", [])


@tool
@as_tool_result
async def meta_ads_insights(config: RunnableConfig, date_preset: str = "last_30d") -> list:
    """Performances Meta Ads (Facebook/Instagram) du client par campagne."""
    client, _ = context(config)
    account = client_setting(client, "meta_ad_account_id")
    s = settings()
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.get(
            f"https://graph.facebook.com/{s.meta_api_version}/act_{account.removeprefix('act_')}/insights",
            params={
                "access_token": require(s.meta_access_token, "META_ACCESS_TOKEN"),
                "level": "campaign",
                "date_preset": date_preset,
                "fields": "campaign_name,spend,impressions,clicks,ctr,cpc,actions",
            },
        )
        r.raise_for_status()
        return r.json().get("data", [])


async def create_meta_campaign(client: dict, payload: dict) -> dict:
    account = client_setting(client, "meta_ad_account_id")
    s = settings()
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(
            f"https://graph.facebook.com/{s.meta_api_version}/act_{account.removeprefix('act_')}/campaigns",
            data={
                "access_token": require(s.meta_access_token, "META_ACCESS_TOKEN"),
                "name": payload["name"],
                "objective": payload.get("objective", "OUTCOME_TRAFFIC"),
                "status": "PAUSED",
                "special_ad_categories": "[]",
            },
        )
        r.raise_for_status()
        return r.json()


async def create_google_ads_campaign(client: dict, payload: dict) -> dict:
    customer_id = client_setting(client, "google_ads_customer_id")
    base = _google_base(customer_id)
    async with httpx.AsyncClient(timeout=60) as http:
        budget = await http.post(
            f"{base}/campaignBudgets:mutate",
            headers=_google_headers(),
            json={
                "operations": [
                    {
                        "create": {
                            "name": f"{payload['name']} - budget",
                            "amountMicros": str(int(payload.get("daily_budget_micros", 10_000_000))),
                            "deliveryMethod": "STANDARD",
                        }
                    }
                ]
            },
        )
        budget.raise_for_status()
        budget_rn = budget.json()["results"][0]["resourceName"]
        campaign = await http.post(
            f"{base}/campaigns:mutate",
            headers=_google_headers(),
            json={
                "operations": [
                    {
                        "create": {
                            "name": payload["name"],
                            "status": "PAUSED",
                            "advertisingChannelType": payload.get("channel", "SEARCH"),
                            "campaignBudget": budget_rn,
                            "manualCpc": {},
                            "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
                        }
                    }
                ]
            },
        )
        campaign.raise_for_status()
        return campaign.json()
