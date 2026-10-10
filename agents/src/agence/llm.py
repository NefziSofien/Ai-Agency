"""Toutes les requêtes de modèles passent par OmniRoute (API compatible OpenAI)."""

from typing import Any, Literal

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from agence import db
from agence.config import settings

Role = Literal["strategie", "redaction", "rapide"]


def model_for(role: Role) -> str:
    s = settings()
    return {"strategie": s.model_strategie, "redaction": s.model_redaction, "rapide": s.model_rapide}[role]


def api_key_for(client: dict | None) -> str:
    key = (client or {}).get("omniroute_key") or settings().omniroute_api_key
    if not key:
        raise RuntimeError(
            "Aucune clé OmniRoute : renseigne OMNIROUTE_API_KEY dans .env "
            "ou une clé dédiée sur la fiche client."
        )
    return key


class UsageRecorder(AsyncCallbackHandler):
    """Enregistre les tokens consommés par client, run et rôle."""

    def __init__(self, client_id: str | None, run_id: str | None, role: str):
        self.client_id, self.run_id, self.role = client_id, run_id, role

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        llm_output = response.llm_output or {}
        usage = llm_output.get("token_usage") or {}
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        if not usage:
            for gens in response.generations:
                for g in gens:
                    meta = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
                    input_tokens += meta.get("input_tokens", 0)
                    output_tokens += meta.get("output_tokens", 0)
        try:
            await db.execute(
                "INSERT INTO usage (client_id, run_id, role, model, input_tokens, output_tokens)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                self.client_id,
                self.run_id,
                self.role,
                llm_output.get("model_name"),
                input_tokens,
                output_tokens,
            )
        except RuntimeError:
            pass


def chat(role: Role, client: dict | None = None, run_id: str | None = None, **kwargs) -> ChatOpenAI:
    s = settings()
    return ChatOpenAI(
        model=model_for(role),
        base_url=s.omniroute_base_url,
        api_key=api_key_for(client),
        timeout=300,
        max_retries=2,
        callbacks=[UsageRecorder((client or {}).get("id"), run_id, role)],
        **kwargs,
    )


def raw_client(client: dict | None = None) -> AsyncOpenAI:
    """Client OpenAI brut vers OmniRoute, pour embeddings, images et audio."""
    return AsyncOpenAI(base_url=settings().omniroute_base_url, api_key=api_key_for(client))


async def embed(texts: list[str], client: dict | None = None) -> list[list[float]] | None:
    model = settings().model_embedding
    if not model or not texts:
        return None
    res = await raw_client(client).embeddings.create(model=model, input=texts)
    return [d.embedding for d in res.data]
