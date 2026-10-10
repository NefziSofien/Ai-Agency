import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

Department = Literal["strategie", "contenu", "visuels", "social", "seo", "analytics", "crm"]
DEPARTMENTS: tuple[str, ...] = Department.__args__

DEPARTMENT_LABELS = {
    "strategie": "Stratégie et veille",
    "contenu": "Contenu et copywriting",
    "visuels": "Visuels et vidéo IA",
    "social": "Social media",
    "seo": "SEO et SEA",
    "analytics": "Analytics et reporting",
    "crm": "CRM et prospection",
}

# Livrables relus par le Brand Guardian avant validation humaine.
REVIEWED_DEPARTMENTS = {"contenu", "visuels", "social", "crm", "seo"}


class Task(TypedDict):
    department: str
    instruction: str


class Action(TypedDict):
    id: str
    department: str
    kind: str
    summary: str
    payload: dict[str, Any]


class ProposedAction(BaseModel):
    """Action externe proposée ; exécutée seulement après validation humaine."""

    kind: str = Field(description="Type d'action, parmi ceux listés dans les consignes du département.")
    summary: str = Field(description="Résumé lisible de l'action pour le validateur humain.")
    payload: dict[str, Any] = Field(default_factory=dict, description="Paramètres de l'action.")


class DepartmentOutput(BaseModel):
    report: str = Field(description="Livrable complet du département, en Markdown.")
    actions: list[ProposedAction] = Field(default_factory=list)


def merge_dicts(left: dict, right: dict) -> dict:
    return {**(left or {}), **(right or {})}


class AgencyState(TypedDict, total=False):
    client_id: str
    run_id: str
    brief: str
    requested_departments: list[str]
    plan: list[Task]
    pending: list[Task]
    current: Task | None
    results: Annotated[dict[str, str], merge_dicts]
    actions: Annotated[dict[str, list[Action]], merge_dicts]
    review: dict
    revisions: int
    human_feedback: str
    decision: dict
    executed: list[dict]
    deliverable: str
    report_asset: dict
    status: str
    source: str
    human_rounds: int
