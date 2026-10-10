import json
from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig


class NotConfigured(Exception):
    pass


def context(config: RunnableConfig) -> tuple[dict, str | None]:
    """Client et run courants, transmis via config["configurable"] par le graphe."""
    conf = (config or {}).get("configurable", {})
    return conf.get("client") or {}, conf.get("run_id")


def client_setting(client: dict, key: str) -> Any:
    value = (client.get("settings") or {}).get(key)
    if not value:
        raise NotConfigured(f"Paramètre client '{key}' non renseigné pour {client.get('name', '?')}.")
    return value


def require(value: str, name: str) -> str:
    if not value:
        raise NotConfigured(f"{name} non configuré dans .env.")
    return value


def as_tool_result(fn):
    """Les erreurs deviennent un texte lisible par l'agent au lieu d'interrompre le run."""
    import functools

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            result = await fn(*args, **kwargs)
        except NotConfigured as e:
            return f"NON DISPONIBLE : {e} Continue sans cette donnée et signale-le dans le livrable."
        except httpx.HTTPStatusError as e:
            return f"ERREUR API {e.response.status_code} : {e.response.text[:500]}"
        except httpx.HTTPError as e:
            return f"ERREUR RÉSEAU : {e}"
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)[:12000]

    return wrapper
