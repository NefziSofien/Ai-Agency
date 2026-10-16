"""Sorties structurées et agents à outils, en mode natif ou par prompt.

Mode `native` : appels de fonctions OpenAI (tool calling).
Mode `prompt` : pour les modèles OmniRoute dont le fournisseur ignore `tools` et `response_format`
(passerelles web) ; outils et schéma JSON sont décrits dans le prompt, la réponse est parsée et validée.
"""

import json
import re
from typing import TypeVar

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_core.utils.json import parse_json_markdown
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from agence.config import settings

T = TypeVar("T", bound=BaseModel)

MAX_FORMAT_RETRIES = 2
TOOL_RESULT_CHARS = 8000


def prompt_mode() -> bool:
    return settings().tool_mode == "prompt"


def _schema(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=False)


def _format_rules(model: type[BaseModel]) -> str:
    return (
        "FORMAT DE RÉPONSE OBLIGATOIRE : réponds uniquement avec un objet JSON valide, sans texte autour, "
        f"conforme à ce schéma JSON :\n{_schema(model)}\n"
        "Utilise exactement ces noms de champs. Échappe les retours à la ligne dans les chaînes (\\n)."
    )


_TAGGED_CALL = re.compile(r"<(\w+)>\s*(\{.*\})\s*</\1>", re.S)


def _first_json_object(text: str) -> dict:
    """Les modèles agentiques (pont Devin) entourent souvent le JSON de texte ou de balises XML."""
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == "{":
            try:
                data, _ = decoder.raw_decode(text, i)
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
    raise ValueError("aucun objet JSON dans la réponse")


def _parse(text: str) -> dict:
    try:
        data = parse_json_markdown(text)
    except ValueError:
        data = _first_json_object(text)
    if not isinstance(data, dict):
        raise ValueError("la réponse n'est pas un objet JSON")
    return data


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, list):
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return content or ""


def _with_rules(messages: list[BaseMessage], rules: str) -> list[BaseMessage]:
    """Les règles de format vont en fin de dernier message : c'est la partie la mieux suivie."""
    if messages and isinstance(messages[-1], HumanMessage):
        return [*messages[:-1], HumanMessage(f"{_text(messages[-1])}\n\n{rules}")]
    return [*messages, HumanMessage(rules)]


async def structured(llm: ChatOpenAI, model: type[T], messages: list[BaseMessage], config: RunnableConfig) -> T:
    if not prompt_mode():
        return await llm.with_structured_output(model, method="function_calling").ainvoke(messages, config)

    history = _with_rules(messages, _format_rules(model))
    error = None
    for _ in range(MAX_FORMAT_RETRIES + 1):
        reply = await llm.ainvoke(history, config)
        try:
            return model.model_validate(_parse(_text(reply)))
        except (ValueError, ValidationError) as e:
            error = e
            history += [reply, HumanMessage(f"Réponse invalide ({str(e)[:500]}). {_format_rules(model)}")]
    raise RuntimeError(f"Sortie structurée invalide après {MAX_FORMAT_RETRIES + 1} essais : {error}")


def _tools_doc(tools: list[BaseTool]) -> str:
    return "\n".join(
        f"- {t.name} : {t.description.strip()}\n  arguments : {json.dumps(t.args, ensure_ascii=False)}" for t in tools
    )


async def run_agent(
    llm: ChatOpenAI,
    tools: list[BaseTool],
    system: str,
    message: str,
    output: type[T],
    config: RunnableConfig,
    name: str,
    max_steps: int = 8,
) -> T:
    if not prompt_mode():
        agent = create_agent(llm, tools, system_prompt=system, response_format=ToolStrategy(output), name=name)
        out = await agent.ainvoke({"messages": [HumanMessage(message)]}, config)
        return out["structured_response"]

    by_name = {t.name: t for t in tools}
    rules = (
        "FORMAT DE RÉPONSE OBLIGATOIRE : chaque réponse est uniquement un objet JSON valide, sans texte autour.\n"
        + (
            "Pour utiliser un outil (un seul à la fois), réponds : "
            '{"tool": "nom_outil", "args": {...}}\n'
            f"Le résultat te sera renvoyé. Outils disponibles :\n{_tools_doc(tools)}\n"
            if tools
            else ""
        )
        + 'Quand tu as fini, réponds : {"final": {...}} où l\'objet "final" respecte ce schéma JSON :\n'
        f"{_schema(output)}\nÉchappe les retours à la ligne dans les chaînes (\\n)."
    )
    history: list[BaseMessage] = [SystemMessage(system), HumanMessage(f"{message}\n\n{rules}")]
    failures = 0
    for step in range(max_steps + MAX_FORMAT_RETRIES + 1):
        if step >= max_steps:
            history.append(HumanMessage('Plus d\'outils : réponds maintenant avec {"final": {...}}.'))
        reply = await llm.ainvoke(history, config)
        history.append(reply)
        try:
            text = _text(reply)
            call = _TAGGED_CALL.fullmatch(text.strip())
            if call and call.group(1) in by_name:
                text = json.dumps({"tool": call.group(1), "args": json.loads(call.group(2))})
            data = _parse(text)
            if "final" in data or "report" in data:
                return output.model_validate(data.get("final", data))
            tool = by_name.get(data.get("tool", ""))
            if not tool or step >= max_steps:
                raise ValueError(f"outil inconnu ou indisponible : {data.get('tool')!r}")
        except (ValueError, ValidationError) as e:
            failures += 1
            if failures > MAX_FORMAT_RETRIES:
                raise RuntimeError(f"Agent {name} : réponse invalide ({e})") from e
            history.append(HumanMessage(f"Réponse invalide ({str(e)[:500]}). Respecte le format.\n{rules}"))
            continue
        try:
            result = await tool.ainvoke(data.get("args") or {}, config)
        except Exception as e:
            result = f"ERREUR de l'outil : {e}"
        history.append(
            HumanMessage(
                f"Résultat de {tool.name} :\n{str(result)[:TOOL_RESULT_CHARS]}\n\n"
                'Continue : réponds uniquement en JSON, {"tool": ..., "args": ...} ou {"final": {...}}.'
            )
        )
    raise RuntimeError(f"Agent {name} : pas de livrable final")
