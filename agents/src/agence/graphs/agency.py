"""Graphe principal de l'agence.

plan -> route -> department (boucle) -> brand_guardian -> (révision | assemble) -> approval -> execute
"""

import json
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agence.config import settings
from agence.graphs.departments import DEPARTMENT_SPECS, EXECUTORS, ORDER, actions_doc, prompt
from agence.llm import chat
from agence.memory import brand_context
from agence.reports import markdown_to_pdf
from agence.state import (
    DEPARTMENT_LABELS,
    REVIEWED_DEPARTMENTS,
    AgencyState,
    Department,
    DepartmentOutput,
    Task,
)
from agence.storage import save_asset
from agence.structured import run_agent, structured

AUTOMATED_SOURCES = {"n8n", "schedule"}
MAX_HUMAN_ROUNDS = 3


def _ctx(config: RunnableConfig) -> tuple[dict, str]:
    conf = config["configurable"]
    return conf["client"], conf["run_id"]


def _client_profile(client: dict) -> str:
    public_settings = {k: v for k, v in (client.get("settings") or {}).items() if not k.endswith("_token")}
    return f"Paramètres du client : {json.dumps(public_settings, ensure_ascii=False)}" if public_settings else ""


# ---------------- Planification ----------------
class PlannedTask(BaseModel):
    department: Department
    instruction: str = Field(description="Consigne précise et autonome pour ce département.")


class Plan(BaseModel):
    tasks: list[PlannedTask]


async def plan(state: AgencyState, config: RunnableConfig) -> dict:
    client, run_id = _ctx(config)
    requested = state.get("requested_departments") or []
    constraint = (
        f"Tu dois produire exactement une tâche pour chacun de ces départements : {', '.join(requested)}."
        if requested
        else "Choisis les départements nécessaires."
    )
    result = await structured(
        chat("strategie", client, run_id),
        Plan,
        [
            SystemMessage(prompt("superviseur")),
            HumanMessage(
                f"Contexte de marque :\n{await brand_context(client, state['brief'])}\n\n"
                f"Brief :\n{state['brief']}\n\n{constraint}"
            ),
        ],
        config,
    )
    tasks: dict[str, Task] = {}
    for t in result.tasks:
        if not requested or t.department in requested:
            tasks.setdefault(t.department, Task(department=t.department, instruction=t.instruction))
    for dep in requested:
        tasks.setdefault(dep, Task(department=dep, instruction=state["brief"]))
    ordered = [tasks[d] for d in ORDER if d in tasks]
    return {"plan": ordered, "pending": ordered, "revisions": 0, "human_rounds": 0, "status": "running"}


# ---------------- Exécution des départements ----------------
def route(state: AgencyState) -> dict:
    pending = list(state.get("pending") or [])
    return {"current": pending[0] if pending else None, "pending": pending[1:]}


def after_route(state: AgencyState) -> str:
    return "department" if state.get("current") else "brand_guardian"


async def department(state: AgencyState, config: RunnableConfig) -> dict:
    client, run_id = _ctx(config)
    task = state["current"]
    dep = task["department"]
    spec = DEPARTMENT_SPECS[dep]

    brand = await brand_context(client, f"{state['brief']}\n{task['instruction']}")
    system = "\n\n".join(
        [prompt("commun"), prompt(dep), actions_doc(dep), f"Contexte de marque :\n{brand}", _client_profile(client)]
    )
    previous = "\n\n".join(
        f"### Livrable {DEPARTMENT_LABELS[d]}\n{r}" for d, r in (state.get("results") or {}).items() if d != dep
    )
    message = f"Brief client :\n{state['brief']}\n\nTa mission :\n{task['instruction']}"
    if previous:
        message += f"\n\nTravaux des autres départements :\n{previous}"
    if (state.get("results") or {}).get(dep):
        message += f"\n\nTa version précédente, à améliorer :\n{state['results'][dep]}"

    response = await run_agent(
        chat(spec.role, client, run_id), spec.tools, system, message, DepartmentOutput, config, f"departement_{dep}"
    )
    actions = [
        {"id": uuid.uuid4().hex[:12], "department": dep, "kind": a.kind, "summary": a.summary, "payload": a.payload}
        for a in response.actions
        if a.kind in spec.actions
    ]
    return {"results": {dep: response.report}, "actions": {dep: actions}}


# ---------------- Contrôle qualité ----------------
class Review(BaseModel):
    approved: bool
    score: int = Field(ge=0, le=10)
    issues: list[str] = Field(default_factory=list)
    feedback: str = ""
    departments_to_revise: list[Department] = Field(default_factory=list)


async def brand_guardian(state: AgencyState, config: RunnableConfig) -> dict:
    client, run_id = _ctx(config)
    results = state.get("results") or {}
    reviewed = {d: r for d, r in results.items() if d in REVIEWED_DEPARTMENTS}
    if not reviewed:
        return {"review": {"approved": True, "score": 10, "issues": [], "feedback": "Aucun livrable à contrôler."}}

    actions = [a for acts in (state.get("actions") or {}).values() for a in acts]
    review = await structured(
        chat("rapide", client, run_id),
        Review,
        [
            SystemMessage(prompt("brand_guardian")),
            HumanMessage(
                f"Contexte de marque :\n{await brand_context(client, state['brief'])}\n\n"
                f"Brief :\n{state['brief']}\n\n"
                + "\n\n".join(f"## {DEPARTMENT_LABELS[d]}\n{r}" for d, r in reviewed.items())
                + f"\n\nActions proposées :\n{json.dumps(actions, ensure_ascii=False)}"
            ),
        ],
        config,
    )
    update: dict = {"review": review.model_dump()}
    to_revise = [d for d in review.departments_to_revise if d in reviewed]
    if not review.approved and to_revise and state.get("revisions", 0) < settings().max_revisions:
        instructions = {t["department"]: t["instruction"] for t in state["plan"]}
        update["pending"] = [
            Task(
                department=d,
                instruction=f"{instructions.get(d, state['brief'])}\n\nCorrections demandées par le Brand Guardian :\n"
                f"{review.feedback}\n- " + "\n- ".join(review.issues),
            )
            for d in ORDER
            if d in to_revise
        ]
        update["revisions"] = state.get("revisions", 0) + 1
    return update


def after_review(state: AgencyState) -> str:
    return "route" if state.get("pending") else "assemble"


# ---------------- Livrable final ----------------
async def assemble(state: AgencyState, config: RunnableConfig) -> dict:
    client, run_id = _ctx(config)
    results = state.get("results") or {}
    body = "\n\n".join(f"## {DEPARTMENT_LABELS[d]}\n\n{results[d]}" for d in ORDER if d in results)
    summary = await chat("rapide", client, run_id).ainvoke(
        [
            SystemMessage(
                "Tu es le Directeur de compte. Rédige une synthèse exécutive en Markdown (5 à 8 puces) "
                "des livrables ci-dessous, pour le client. Pas de titre, pas d'introduction."
            ),
            HumanMessage(f"Brief :\n{state['brief']}\n\n{body}"),
        ],
        config,
    )
    deliverable = f"## Synthèse\n\n{summary.content}\n\n{body}"
    pdf = markdown_to_pdf(deliverable, f"{client['name']} : livrable de l'agence")
    asset = await save_asset(client["id"], run_id, "report", pdf, "pdf", "application/pdf", state["brief"][:500])
    return {"deliverable": deliverable, "report_asset": asset}


# ---------------- Validation humaine et exécution ----------------
def _all_actions(state: AgencyState) -> list[dict]:
    return [a for acts in (state.get("actions") or {}).values() for a in acts]


async def approval(state: AgencyState) -> dict:
    actions = _all_actions(state)
    if not actions and state.get("source") in AUTOMATED_SOURCES:
        return {"decision": {"approved": True, "approved_action_ids": [], "feedback": "auto"}}

    decision = interrupt(
        {
            "type": "approval",
            "deliverable": state.get("deliverable"),
            "review": state.get("review"),
            "actions": actions,
        }
    )
    decision = {
        "approved": bool(decision.get("approved")),
        "approved_action_ids": list(decision.get("approved_action_ids") or []),
        "feedback": (decision.get("feedback") or "").strip(),
    }
    update: dict = {"decision": decision}
    if not decision["approved"] and decision["feedback"] and state.get("human_rounds", 0) < MAX_HUMAN_ROUNDS:
        update["pending"] = [
            Task(
                department=t["department"],
                instruction=f"{t['instruction']}\n\nRetour du client / de l'équipe :\n{decision['feedback']}",
            )
            for t in state["plan"]
        ]
        update["human_rounds"] = state.get("human_rounds", 0) + 1
        update["revisions"] = 0
    return update


def after_approval(state: AgencyState) -> str:
    decision = state.get("decision") or {}
    if decision.get("approved"):
        return "execute"
    return "route" if state.get("pending") else END


async def execute(state: AgencyState, config: RunnableConfig) -> dict:
    client, _ = _ctx(config)
    approved_ids = set(state["decision"]["approved_action_ids"])
    executed = []
    for action in _all_actions(state):
        if action["id"] not in approved_ids:
            continue
        try:
            result = await EXECUTORS[action["kind"]](client, action["payload"])
            executed.append({"id": action["id"], "kind": action["kind"], "ok": True, "result": result})
        except Exception as e:  # une action en échec ne bloque pas les autres
            executed.append({"id": action["id"], "kind": action["kind"], "ok": False, "error": str(e)[:1000]})
    return {"executed": executed, "status": "completed"}


def build_graph(checkpointer=None):
    g = StateGraph(AgencyState)
    g.add_node("plan", plan)
    g.add_node("route", route)
    g.add_node("department", department)
    g.add_node("brand_guardian", brand_guardian)
    g.add_node("assemble", assemble)
    g.add_node("approval", approval)
    g.add_node("execute", execute)

    g.add_edge(START, "plan")
    g.add_edge("plan", "route")
    g.add_conditional_edges("route", after_route, ["department", "brand_guardian"])
    g.add_edge("department", "route")
    g.add_conditional_edges("brand_guardian", after_review, ["route", "assemble"])
    g.add_edge("assemble", "approval")
    g.add_conditional_edges("approval", after_approval, ["execute", "route", END])
    g.add_edge("execute", END)
    return g.compile(checkpointer=checkpointer)
