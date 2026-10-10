"""Traces Langfuse, activées seulement si les clés sont configurées."""

from functools import lru_cache

import httpx

from agence.config import settings


@lru_cache
def langfuse_enabled() -> bool:
    s = settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return False
    try:
        httpx.get(f"{s.langfuse_host}/api/public/health", timeout=2).raise_for_status()
    except httpx.HTTPError:
        return False
    from langfuse import Langfuse

    Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, host=s.langfuse_host)
    return True


def callbacks() -> list:
    if not langfuse_enabled():
        return []
    from langfuse.langchain import CallbackHandler

    return [CallbackHandler(public_key=settings().langfuse_public_key)]


def run_metadata(run_id: str, client: dict, source: str) -> dict:
    return {
        "langfuse_session_id": run_id,
        "langfuse_user_id": client["id"],
        "langfuse_tags": [client["id"], source],
    }
