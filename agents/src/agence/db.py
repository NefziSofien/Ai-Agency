from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from agence.config import settings

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    website TEXT,
    omniroute_key TEXT,
    brand_kit JSONB NOT NULL DEFAULT '{}',
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS brand_chunks (
    id BIGSERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    brief TEXT NOT NULL,
    departments TEXT[] NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'dashboard',
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage (
    id BIGSERIAL PRIMARY KEY,
    client_id TEXT,
    run_id TEXT,
    role TEXT,
    model TEXT,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS assets (
    id BIGSERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    run_id TEXT,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    prompt TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    source TEXT,
    level TEXT,
    message TEXT,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS runs_client_idx ON runs(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS usage_client_idx ON usage(client_id, created_at);
"""

_pool: AsyncConnectionPool | None = None


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            settings().database_url,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        )
        await _pool.open()
        async with _pool.connection() as conn:
            await conn.execute(SCHEMA, prepare=False)
    return _pool


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Pool Postgres non initialisé (appeler open_pool()).")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def fetch(query: str, *params) -> list[dict]:
    async with pool().connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchall() if cur.description else []


async def fetchone(query: str, *params) -> dict | None:
    rows = await fetch(query, *params)
    return rows[0] if rows else None


async def execute(query: str, *params) -> None:
    async with pool().connection() as conn:
        await conn.execute(query, params)
