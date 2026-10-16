"""Registre des départements : rôle de modèle OmniRoute, outils et actions externes autorisées."""

from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from typing import Awaitable, Callable

from langchain_core.tools import BaseTool

from agence.config import settings
from agence.llm import Role
from agence.tools import ads, crm, postiz
from agence.tools.analytics import ga4_report
from agence.tools.crm import crm_list_companies, crm_search_people, email_lists
from agence.tools.postiz import list_social_channels
from agence.tools.seo import search_console_queries, seo_audit
from agence.tools.visuals import generate_image, generate_voiceover
from agence.tools.web import fetch_page, web_search

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

Executor = Callable[[dict, dict], Awaitable[dict]]


@dataclass(frozen=True)
class DepartmentSpec:
    role: Role
    tools: list[BaseTool]
    actions: dict[str, Executor] = field(default_factory=dict)


DEPARTMENT_SPECS: dict[str, DepartmentSpec] = {
    "strategie": DepartmentSpec("strategie", [web_search, fetch_page]),
    "seo": DepartmentSpec(
        "strategie",
        [web_search, fetch_page, seo_audit, search_console_queries, ads.google_ads_campaign_metrics, ads.meta_ads_insights],
        {
            "google_ads_create_campaign": ads.create_google_ads_campaign,
            "meta_create_campaign": ads.create_meta_campaign,
        },
    ),
    "analytics": DepartmentSpec(
        "strategie",
        [ga4_report, search_console_queries, ads.google_ads_campaign_metrics, ads.meta_ads_insights, list_social_channels],
    ),
    "contenu": DepartmentSpec("redaction", [web_search, fetch_page]),
    "visuels": DepartmentSpec("redaction", [generate_image, generate_voiceover]),
    "social": DepartmentSpec("redaction", [list_social_channels], {"postiz_schedule": postiz.schedule_post}),
    "crm": DepartmentSpec(
        "redaction",
        [crm_search_people, crm_list_companies, email_lists, web_search, fetch_page],
        {
            "crm_create_company": crm.create_company,
            "crm_create_person": crm.create_person,
            "email_campaign": crm.email_campaign,
        },
    ),
}

EXECUTORS: dict[str, Executor] = {kind: fn for spec in DEPARTMENT_SPECS.values() for kind, fn in spec.actions.items()}

# Ordre d'exécution : les départements d'analyse alimentent la production, qui alimente la diffusion.
ORDER = ["strategie", "seo", "analytics", "contenu", "visuels", "social", "crm"]


@cache
def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def spec_for(department: str) -> DepartmentSpec:
    """Sans clé Postiz, pas de lecture des canaux ni de programmation : les publications restent des brouillons."""
    spec = DEPARTMENT_SPECS[department]
    if settings().postiz_api_key:
        return spec
    return replace(
        spec,
        tools=[t for t in spec.tools if t is not list_social_channels],
        actions={k: v for k, v in spec.actions.items() if k != "postiz_schedule"},
    )


def actions_doc(department: str) -> str:
    actions = spec_for(department).actions
    if not actions:
        return "Actions externes autorisées : aucune."
    lines = ["Actions externes autorisées (champ `kind`, puis `payload` attendu) :"]
    for kind, fn in actions.items():
        lines.append(f"- `{kind}` : {(fn.__doc__ or '').strip()}")
    return "\n".join(lines)
