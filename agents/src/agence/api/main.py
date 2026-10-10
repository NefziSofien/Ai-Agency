import logging
import re
import unicodedata
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from agence import db, memory, runner
from agence.config import settings
from agence.state import DEPARTMENT_LABELS, DEPARTMENTS
from agence.storage import presigned_url

logging.basicConfig(level=logging.INFO)
logging.getLogger("fontTools").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open_pool()
    await runner.init()
    await runner.recover_interrupted_runs()
    yield
    await db.close_pool()


def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = settings().agence_api_key
    if expected and x_api_key != expected:
        raise HTTPException(401, "Clé API invalide (en-tête X-API-Key).")


app = FastAPI(title="Agence IA", lifespan=lifespan, dependencies=[Depends(require_api_key)])


# ---------------- Santé ----------------
@app.get("/health")
async def health() -> dict:
    s = settings()
    status = {"api": "ok", "omniroute": "down", "models": 0}
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            r = await http.get(f"{s.omniroute_base_url}/models", headers={"Authorization": f"Bearer {s.omniroute_api_key}"})
        status["omniroute"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
        if r.status_code == 200:
            status["models"] = len(r.json().get("data", []))
    except httpx.HTTPError:
        pass
    status["roles"] = {"strategie": s.model_strategie, "redaction": s.model_redaction, "rapide": s.model_rapide}
    return status


@app.get("/departments")
async def departments() -> list[dict]:
    return [{"id": d, "label": DEPARTMENT_LABELS[d]} for d in DEPARTMENTS]


# ---------------- Clients ----------------
class ClientIn(BaseModel):
    name: str
    website: str | None = None
    omniroute_key: str | None = None
    brand_kit: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "client"


def _public_client(row: dict) -> dict:
    row = dict(row)
    key = row.pop("omniroute_key", None)
    row["has_omniroute_key"] = bool(key)
    return row


async def _get_client(client_id: str) -> dict:
    row = await db.fetchone("SELECT * FROM clients WHERE id = %s", client_id)
    if not row:
        raise HTTPException(404, "Client introuvable.")
    return row


@app.get("/clients")
async def list_clients() -> list[dict]:
    return [_public_client(r) for r in await db.fetch("SELECT * FROM clients ORDER BY name")]


@app.post("/clients", status_code=201)
async def create_client(body: ClientIn) -> dict:
    client_id = _slug(body.name)
    if await db.fetchone("SELECT id FROM clients WHERE id = %s", client_id):
        raise HTTPException(409, f"Le client '{client_id}' existe déjà.")
    await db.execute(
        "INSERT INTO clients (id, name, website, omniroute_key, brand_kit, settings) VALUES (%s, %s, %s, %s, %s, %s)",
        client_id,
        body.name,
        body.website,
        body.omniroute_key or None,
        Jsonb(body.brand_kit),
        Jsonb(body.settings),
    )
    client = await _get_client(client_id)
    await memory.reindex(client)
    return _public_client(client)


@app.get("/clients/{client_id}")
async def get_client(client_id: str) -> dict:
    return _public_client(await _get_client(client_id))


@app.put("/clients/{client_id}")
async def update_client(client_id: str, body: ClientIn) -> dict:
    current = await _get_client(client_id)
    await db.execute(
        "UPDATE clients SET name = %s, website = %s, omniroute_key = %s, brand_kit = %s, settings = %s WHERE id = %s",
        body.name,
        body.website,
        body.omniroute_key if body.omniroute_key is not None else current["omniroute_key"],
        Jsonb(body.brand_kit),
        Jsonb(body.settings),
        client_id,
    )
    client = await _get_client(client_id)
    await memory.reindex(client)
    return _public_client(client)


@app.delete("/clients/{client_id}", status_code=204)
async def delete_client(client_id: str) -> None:
    await db.execute("DELETE FROM clients WHERE id = %s", client_id)


# ---------------- Runs ----------------
class RunIn(BaseModel):
    client_id: str
    brief: str = Field(min_length=5)
    departments: list[str] = Field(default_factory=list)
    source: str = "dashboard"


class DecisionIn(BaseModel):
    approved: bool
    approved_action_ids: list[str] = Field(default_factory=list)
    feedback: str = ""


@app.post("/runs", status_code=202)
async def create_run(body: RunIn) -> dict:
    unknown = set(body.departments) - set(DEPARTMENTS)
    if unknown:
        raise HTTPException(422, f"Départements inconnus : {', '.join(sorted(unknown))}")
    client = await _get_client(body.client_id)
    run_id = await runner.start_run(client, body.brief, body.departments, body.source)
    return {"id": run_id, "status": "running"}


@app.get("/runs")
async def list_runs(client_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    return await db.fetch(
        "SELECT r.*, c.name AS client_name FROM runs r JOIN clients c ON c.id = r.client_id"
        " WHERE (%s::text IS NULL OR r.client_id = %s) AND (%s::text IS NULL OR r.status = %s)"
        " ORDER BY r.created_at DESC LIMIT %s",
        client_id,
        client_id,
        status,
        status,
        limit,
    )


async def _get_run(run_id: str) -> dict:
    run = await db.fetchone("SELECT * FROM runs WHERE id = %s", run_id)
    if not run:
        raise HTTPException(404, "Run introuvable.")
    return run


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = await _get_run(run_id)
    client = await _get_client(run["client_id"])
    state = await runner.snapshot(run, client)
    assets = await db.fetch("SELECT * FROM assets WHERE run_id = %s ORDER BY id", run_id)
    for a in assets:
        a["url"] = presigned_url(a["key"])
    usage = await db.fetchone(
        "SELECT COALESCE(SUM(input_tokens), 0) AS input_tokens, COALESCE(SUM(output_tokens), 0) AS output_tokens,"
        " COUNT(*) AS calls FROM usage WHERE run_id = %s",
        run_id,
    )
    return {"run": run, "client": _public_client(client), "state": state, "assets": assets, "usage": usage}


@app.post("/runs/{run_id}/decision", status_code=202)
async def decide(run_id: str, body: DecisionIn) -> dict:
    run = await _get_run(run_id)
    if run["status"] != "awaiting_approval":
        raise HTTPException(409, f"Ce run n'attend pas de validation (statut : {run['status']}).")
    client = await _get_client(run["client_id"])
    await runner.resume_run(run, client, body.model_dump())
    return {"id": run_id, "status": "running"}


# ---------------- Usage OmniRoute ----------------
@app.get("/usage")
async def usage(days: int = 30) -> dict:
    by_client = await db.fetch(
        "SELECT u.client_id, c.name AS client_name, COUNT(*) AS calls, SUM(u.input_tokens) AS input_tokens,"
        " SUM(u.output_tokens) AS output_tokens FROM usage u LEFT JOIN clients c ON c.id = u.client_id"
        " WHERE u.created_at > now() - make_interval(days => %s) GROUP BY u.client_id, c.name ORDER BY 4 DESC",
        days,
    )
    by_model = await db.fetch(
        "SELECT COALESCE(model, '?') AS model, role, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens,"
        " SUM(output_tokens) AS output_tokens FROM usage WHERE created_at > now() - make_interval(days => %s)"
        " GROUP BY 1, 2 ORDER BY 4 DESC",
        days,
    )
    daily = await db.fetch(
        "SELECT date_trunc('day', created_at)::date AS day, SUM(input_tokens + output_tokens) AS tokens"
        " FROM usage WHERE created_at > now() - make_interval(days => %s) GROUP BY 1 ORDER BY 1",
        days,
    )
    return {"days": days, "by_client": by_client, "by_model": by_model, "daily": daily}


# ---------------- Automatisations (appelées par n8n) ----------------
AUTOMATIONS = {
    "daily-watch": (
        "daily_watch",
        ["strategie"],
        "Veille quotidienne pour {name} : nouveautés du marché, actualités des concurrents, tendances et "
        "opportunités de contenu des dernières 24 heures. Termine par 3 idées de contenus à saisir.",
    ),
    "weekly-reports": (
        "weekly_report",
        ["analytics"],
        "Rapport de performance hebdomadaire pour {name} : 7 derniers jours comparés aux 7 précédents, "
        "tous canaux disponibles, avec recommandations pour la semaine à venir.",
    ),
    "crm-followups": (
        "crm_followups",
        ["crm"],
        "Relances CRM pour {name} : identifie les prospects à relancer ou à qualifier, propose les séquences "
        "d'emails adaptées et les mises à jour du CRM.",
    ),
}


@app.post("/automations/{name}", status_code=202)
async def run_automation(name: str, client_id: str | None = None) -> dict:
    if name not in AUTOMATIONS:
        raise HTTPException(404, f"Automatisation inconnue. Disponibles : {', '.join(AUTOMATIONS)}")
    flag, deps, brief = AUTOMATIONS[name]
    clients = await db.fetch(
        "SELECT * FROM clients WHERE (%s::text IS NOT NULL AND id = %s)"
        " OR (%s::text IS NULL AND COALESCE((settings->>%s)::boolean, false))",
        client_id,
        client_id,
        client_id,
        flag,
    )
    started = []
    for client in clients:
        run_id = await runner.start_run(client, brief.format(name=client["name"]), deps, "n8n")
        started.append({"client_id": client["id"], "run_id": run_id})
    return {"automation": name, "started": started}


@app.get("/approvals")
async def pending_approvals() -> list[dict]:
    return await db.fetch(
        "SELECT r.id, r.client_id, c.name AS client_name, r.brief, r.updated_at FROM runs r"
        " JOIN clients c ON c.id = r.client_id WHERE r.status = 'awaiting_approval' ORDER BY r.updated_at"
    )


class AlertIn(BaseModel):
    source: str = "n8n"
    level: str = "error"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


@app.post("/alerts", status_code=201)
async def create_alert(body: AlertIn) -> dict:
    await db.execute(
        "INSERT INTO alerts (source, level, message, details) VALUES (%s, %s, %s, %s)",
        body.source,
        body.level,
        body.message,
        Jsonb(body.details),
    )
    return {"ok": True}


@app.get("/alerts")
async def list_alerts(limit: int = 50) -> list[dict]:
    return await db.fetch("SELECT * FROM alerts ORDER BY created_at DESC LIMIT %s", limit)


def run() -> None:
    import uvicorn

    uvicorn.run("agence.api.main:app", host="0.0.0.0", port=8000)
