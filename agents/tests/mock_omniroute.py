"""Faux OmniRoute (API compatible OpenAI) pour tester le graphe sans fournisseur réel.

uv run uvicorn tests.mock_omniroute:app --port 20199
"""

import base64
import json
import time
import uuid

from fastapi import FastAPI, Request

app = FastAPI()

# PNG 1x1 transparent
PIXEL = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
).decode()


def _usage():
    return {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}


def _tool_call(name: str, args: dict) -> dict:
    return {
        "id": f"call_{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


def _reply(model: str, content: str | None = None, tool_calls: list | None = None) -> dict:
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": f"mock/{model}",
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "usage": _usage(),
    }


def _args_for(name: str, messages: list[dict]) -> dict:
    text = json.dumps(messages, ensure_ascii=False)
    if name == "Plan":
        return {
            "tasks": [
                {"department": "contenu", "instruction": "Rédige 2 posts LinkedIn sur le lancement."},
                {"department": "social", "instruction": "Programme les 2 posts sur LinkedIn."},
            ]
        }
    if name == "Review":
        first_pass = "Corrections demandées" not in text
        return {
            "approved": not first_pass,
            "score": 6 if first_pass else 9,
            "issues": ["Appel à l'action trop faible"] if first_pass else [],
            "feedback": "Renforce l'appel à l'action." if first_pass else "OK",
            "departments_to_revise": ["contenu"] if first_pass else [],
        }
    if name == "Judgement":
        return {
            "scores": [{"criterion": "Livrable complet", "score": 8, "comment": "Bon niveau."}],
            "overall": 8,
            "summary": "Livrable solide.",
        }
    if name == "DepartmentOutput":
        if "Social Media Manager" in text:
            return {
                "report": "## Calendrier\n| Date | Réseau | Post |\n|---|---|---|\n| lundi 9h | LinkedIn | Post 1 |",
                "actions": [
                    {
                        "kind": "postiz_schedule",
                        "summary": "Programmer le post 1 sur LinkedIn lundi 9h",
                        "payload": {"content": "Post 1", "date": "2026-10-12T09:00:00Z"},
                    },
                    {"kind": "action_inconnue", "summary": "doit être filtrée", "payload": {}},
                ],
            }
        return {"report": "## Posts\n**Post 1** : Lancement !\n- Point clé\n\n**Post 2** : Rejoignez-nous.", "actions": []}
    return {}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    model, messages, tools = body.get("model", "?"), body.get("messages", []), body.get("tools") or []
    tool_names = [t["function"]["name"] for t in tools]

    choice = body.get("tool_choice")
    forced = choice.get("function", {}).get("name") if isinstance(choice, dict) else None
    if forced:
        return _reply(model, tool_calls=[_tool_call(forced, _args_for(forced, messages))])

    if tools:
        already_used_tool = any(m.get("role") == "tool" for m in messages)
        for candidate in ("web_search", "list_social_channels", "generate_image"):
            if candidate in tool_names and not already_used_tool:
                arg = {"web_search": {"query": "tendances marketing"}, "generate_image": {"prompt": "Visuel de lancement"}}.get(candidate, {})
                return _reply(model, tool_calls=[_tool_call(candidate, arg)])
        structured = next((n for n in tool_names if n in ("DepartmentOutput", "Plan", "Review")), None)
        if structured:
            return _reply(model, tool_calls=[_tool_call(structured, _args_for(structured, messages))])

    return _reply(model, content="- Synthèse : 2 posts LinkedIn prêts et programmés après validation.")


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": "mock/model", "object": "model"}]}


@app.post("/v1/images/generations")
async def images():
    return {"created": int(time.time()), "data": [{"b64_json": PIXEL}]}
