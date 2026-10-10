"""Évaluation de la qualité des agents sur des briefs de référence (evals/briefs.json).

    uv run agence-eval                     # tous les cas
    uv run agence-eval --case lancement-linkedin --min-score 7

Chaque livrable est noté par un juge (rôle « strategie ») sur les critères du cas.
Les scores sont envoyés dans Langfuse (session = id du run) si Langfuse est actif.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from agence import db, observability
from agence.graphs.agency import build_graph
from agence.llm import chat

CASES_FILE = Path(__file__).resolve().parents[2] / "evals" / "briefs.json"


class CriterionScore(BaseModel):
    criterion: str
    score: int = Field(ge=0, le=10)
    comment: str


class Judgement(BaseModel):
    scores: list[CriterionScore]
    overall: int = Field(ge=0, le=10, description="Note globale de qualité professionnelle du livrable.")
    summary: str


async def _ensure_client(spec: dict) -> dict:
    await db.execute(
        "INSERT INTO clients (id, name, website, brand_kit, settings) VALUES (%s, %s, %s, %s, %s)"
        " ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, brand_kit = EXCLUDED.brand_kit",
        spec["id"],
        spec["name"],
        spec.get("website"),
        Jsonb(spec["brand_kit"]),
        Jsonb(spec.get("settings", {})),
    )
    return await db.fetchone("SELECT * FROM clients WHERE id = %s", spec["id"])


def _push_scores(run_id: str, judgement: Judgement) -> None:
    if not observability.langfuse_enabled():
        return
    try:
        from langfuse import get_client

        lf = get_client()
        lf.create_score(name="eval_overall", value=judgement.overall, session_id=run_id, comment=judgement.summary)
        for s in judgement.scores:
            lf.create_score(name=f"eval:{s.criterion[:60]}", value=s.score, session_id=run_id, comment=s.comment)
        lf.flush()
    except Exception as e:  # les scores sont un bonus, ils ne doivent pas faire échouer l'évaluation
        print(f"  (scores Langfuse non envoyés : {e})")


async def evaluate(case: dict, client: dict, graph) -> Judgement:
    run_id = f"eval_{case['name']}_{uuid.uuid4().hex[:6]}"
    config = {
        "configurable": {"thread_id": run_id, "client": client, "run_id": run_id},
        "callbacks": observability.callbacks(),
        "metadata": observability.run_metadata(run_id, client, "eval"),
        "recursion_limit": 100,
    }
    await graph.ainvoke(
        {
            "client_id": client["id"],
            "run_id": run_id,
            "brief": case["brief"],
            "requested_departments": case.get("departments", []),
            "source": "eval",
        },
        config,
    )
    state = (await graph.aget_state(config)).values
    deliverable = state.get("deliverable", "")
    actions = [a for acts in (state.get("actions") or {}).values() for a in acts]

    judge = chat("strategie", client, run_id).with_structured_output(Judgement, method="function_calling")
    judgement: Judgement = await judge.ainvoke(
        [
            SystemMessage(
                "Tu es directeur qualité d'une agence marketing. Évalue le livrable avec exigence, critère par critère, "
                "de 0 (inexistant) à 10 (excellent, publiable tel quel)."
            ),
            HumanMessage(
                f"Brand kit :\n{json.dumps(client['brand_kit'], ensure_ascii=False)}\n\nBrief :\n{case['brief']}\n\n"
                f"Critères :\n- " + "\n- ".join(case["criteria"]) + f"\n\nLivrable :\n{deliverable}\n\n"
                f"Actions proposées :\n{json.dumps(actions, ensure_ascii=False)}"
            ),
        ]
    )
    _push_scores(run_id, judgement)
    return judgement


async def run(args) -> int:
    data = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    cases = [c for c in data["cases"] if not args.case or c["name"] in args.case]
    await db.open_pool()
    try:
        client = await _ensure_client(data["client"])
        graph = build_graph(InMemorySaver())
        overall = []
        for case in cases:
            print(f"\n=== {case['name']} ===")
            judgement = await evaluate(case, client, graph)
            for s in judgement.scores:
                print(f"  {s.score:>2}/10  {s.criterion}\n         {s.comment}")
            print(f"  Global : {judgement.overall}/10 - {judgement.summary}")
            overall.append(judgement.overall)
    finally:
        await db.close_pool()

    average = sum(overall) / len(overall) if overall else 0
    print(f"\nMoyenne : {average:.1f}/10 sur {len(overall)} cas")
    return 0 if average >= args.min_score else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation des agents de l'agence")
    parser.add_argument("--case", action="append", help="Nom du cas à évaluer (répétable)")
    parser.add_argument("--min-score", type=float, default=0, help="Échoue si la moyenne est inférieure")
    sys.exit(asyncio.run(run(parser.parse_args())))
