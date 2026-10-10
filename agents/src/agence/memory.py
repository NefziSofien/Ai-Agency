"""Brand kit client : stocké en JSON, découpé et indexé dans pgvector si un modèle d'embedding est configuré."""

import json

from agence import db
from agence.llm import embed

MAX_FULL_KIT_CHARS = 6000


def brand_kit_text(client: dict) -> str:
    kit = client.get("brand_kit") or {}
    lines = [f"Client : {client['name']}"]
    if client.get("website"):
        lines.append(f"Site : {client['website']}")
    for key, value in kit.items():
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key} : {value}")
    return "\n".join(lines)


def _chunks(text: str, size: int = 800) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) > size and current:
            chunks.append(current)
            current = ""
        current = f"{current}\n{p}".strip()
    if current:
        chunks.append(current)
    return chunks


async def reindex(client: dict) -> int:
    chunks = _chunks(brand_kit_text(client))
    vectors = await embed(chunks, client)
    await db.execute("DELETE FROM brand_chunks WHERE client_id = %s", client["id"])
    for i, chunk in enumerate(chunks):
        vector = str(vectors[i]) if vectors else None
        await db.execute(
            "INSERT INTO brand_chunks (client_id, content, embedding) VALUES (%s, %s, %s::vector)",
            client["id"],
            chunk,
            vector,
        )
    return len(chunks)


async def brand_context(client: dict, query: str, k: int = 6) -> str:
    """Contexte de marque injecté dans chaque agent : recherche sémantique si possible, sinon kit complet."""
    full = brand_kit_text(client)
    if len(full) <= MAX_FULL_KIT_CHARS:
        return full
    vectors = await embed([query], client)
    if vectors:
        rows = await db.fetch(
            "SELECT content FROM brand_chunks WHERE client_id = %s AND embedding IS NOT NULL"
            " ORDER BY embedding <=> %s::vector LIMIT %s",
            client["id"],
            str(vectors[0]),
            k,
        )
        if rows:
            return "\n---\n".join(r["content"] for r in rows)
    return full[:MAX_FULL_KIT_CHARS]
