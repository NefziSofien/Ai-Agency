from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    omniroute_base_url: str = "http://localhost:20129/v1"
    omniroute_api_key: str = ""
    model_strategie: str = "auto"
    model_redaction: str = "auto"
    model_rapide: str = "auto/fast"
    model_fallback: str = ""
    model_embedding: str = ""
    model_image: str = ""
    model_tts: str = ""
    max_revisions: int = 1
    tool_mode: Literal["native", "prompt"] = "native"
    max_user_message_chars: int = 5500

    agence_api_key: str = ""
    api_public_url: str = "http://localhost:8000"
    database_url: str = "postgresql://agence:agence@localhost:5433/agence"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_assets: str = "assets"

    langfuse_host: str = "http://localhost:3001"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    searxng_url: str = "http://localhost:8888"
    tavily_api_key: str = ""

    postiz_url: str = "http://localhost:4007"
    postiz_api_key: str = ""

    twenty_url: str = "http://localhost:3002"
    twenty_api_key: str = ""
    listmonk_url: str = "http://localhost:9002"
    listmonk_api_user: str = ""
    listmonk_api_token: str = ""

    google_oauth_access_token: str = ""
    google_ads_developer_token: str = ""
    google_ads_login_customer_id: str = ""
    google_ads_api_version: str = "v21"
    meta_access_token: str = ""
    meta_api_version: str = "v21.0"


@lru_cache
def settings() -> Settings:
    return Settings()
