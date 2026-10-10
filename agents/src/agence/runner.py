"""Exécution des runs en arrière-plan, avec persistance LangGraph dans Postgres."""

import asyncio
import logging
import uuid

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from agence import db, observability
from agence.graphs.agency import build_graph

log = logging.getLogger("agence.runner")

_graph = None
_tasks: set[asyncio.Task] = set()


async def init() -> None:
    global _graph
    saver = AsyncPostgresSaver(db.pool())
    await saver.setup()
    _graph = build_graph(saver)


def graph():
    if _graph is None:
        raise RuntimeError("Runner non initialisé.")
    return _graph


def _config(run_id: str, client: dict, source: str) -> dict:
    return {
        "configurable": {"thread_id": run_id, "client": client, "run_id": run_id},
        "callbacks": observability.callbacks(),
        "metadata": observability.run_metadata(run_id, client, source),
        "recursion_limit": 100,
    }


async def _set_status(run_id: str, status: str, error: str | None = None) -> None:
    await db.execute("UPDATE runs SET status = %s, error = %s, updated_at = now() WHERE id = %s", status, error, run_id)


async def _drive(run_id: str, client: dict, source: str, payload) -> None:
    config = _config(run_id, client, source)
    try:
        await graph().ainvoke(payload, config)
        snapshot = await graph().aget_state(config)
        if snapshot.interrupts:
            status = "awaiting_approval"
        elif not (snapshot.values.get("decision") or {}).get("approved", True):
            status = "rejected"
        else:
            status = "completed"
        await _set_status(run_id, status)
    except Exception as e:
        log.exception("Run %s en échec", run_id)
        await _set_status(run_id, "failed", f"{type(e).__name__}: {e}"[:2000])


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def start_run(client: dict, brief: str, departments: list[str], source: str) -> str:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    await db.execute(
        "INSERT INTO runs (id, client_id, brief, departments, source) VALUES (%s, %s, %s, %s, %s)",
        run_id,
        client["id"],
        brief,
        departments,
        source,
    )
    inputs = {
        "client_id": client["id"],
        "run_id": run_id,
        "brief": brief,
        "requested_departments": departments,
        "source": source,
    }
    _spawn(_drive(run_id, client, source, inputs))
    return run_id


async def resume_run(run: dict, client: dict, decision: dict) -> None:
    await _set_status(run["id"], "running")
    _spawn(_drive(run["id"], client, run["source"], Command(resume=decision)))


async def snapshot(run: dict, client: dict) -> dict:
    snap = await graph().aget_state(_config(run["id"], client, run["source"]))
    values = dict(snap.values or {})
    values["interrupt"] = snap.interrupts[0].value if snap.interrupts else None
    values["next"] = list(snap.next or [])
    return values


async def recover_interrupted_runs() -> None:
    """Les runs 'running' au redémarrage de l'API ont été coupés : on les marque en échec."""
    await db.execute(
        "UPDATE runs SET status = 'failed', error = 'Interrompu par un redémarrage de l''API', updated_at = now()"
        " WHERE status = 'running'"
    )
