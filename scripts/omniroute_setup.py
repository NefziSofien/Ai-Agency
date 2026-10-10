"""Crée les combos par rôle d'agent et une clé API par client dans OmniRoute.

Usage :
    OMNIROUTE_ADMIN_TOKEN=oma_live_xxx uv run --project agents python scripts/omniroute_setup.py combos
    OMNIROUTE_ADMIN_TOKEN=oma_live_xxx uv run --project agents python scripts/omniroute_setup.py key "Client ACME"
    uv run --project agents python scripts/omniroute_setup.py models

Le token d'administration se crée dans le dashboard OmniRoute (Settings -> Access Tokens).
Les modèles de chaque combo se règlent via COMBO_<ROLE>_MODELS="provider/model,provider/model".
"""

import os
import sys

import httpx

BASE = os.environ.get("OMNIROUTE_URL", "http://localhost:20128").rstrip("/")
ROLES = {
    "agence-strategie": "Raisonnement : stratégie, analyse, planification",
    "agence-redaction": "Rédaction : contenus, copywriting, emails",
    "agence-rapide": "Tâches légères : routage, classification, QA",
}


def _client() -> httpx.Client:
    token = os.environ.get("OMNIROUTE_ADMIN_TOKEN") or os.environ.get("OMNIROUTE_API_KEY")
    if not token:
        sys.exit("OMNIROUTE_ADMIN_TOKEN manquant (Settings -> Access Tokens dans OmniRoute).")
    return httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=30)


def list_models() -> None:
    with _client() as c:
        r = c.get("/v1/models")
        r.raise_for_status()
        for m in r.json().get("data", []):
            print(m["id"])


def create_combos() -> None:
    with _client() as c:
        existing = {x.get("name") for x in _as_list(c.get("/api/combos").json())}
        for name, description in ROLES.items():
            env = "COMBO_" + name.split("-", 1)[1].upper() + "_MODELS"
            models = [m.strip() for m in os.environ.get(env, "").split(",") if m.strip()]
            if not models:
                print(f"- {name}: ignoré, définir {env}=provider/model,... (voir la commande 'models')")
                continue
            body = {"name": name, "models": models, "strategy": "priority", "description": description}
            if name in existing:
                combo_id = next(x["id"] for x in _as_list(c.get("/api/combos").json()) if x.get("name") == name)
                r = c.put(f"/api/combos/{combo_id}", json=body)
            else:
                r = c.post("/api/combos", json=body)
            r.raise_for_status()
            print(f"- {name}: {', '.join(models)}")


def create_key(label: str) -> None:
    with _client() as c:
        r = c.post("/api/keys", json={"label": label})
        r.raise_for_status()
        data = r.json()
        key = data.get("key") or data.get("apiKey", {}).get("key") or data
        print(f"Clé créée pour {label} : {key}")
        print("Renseigne-la dans le dashboard de l'agence (fiche client -> clé OmniRoute).")


def _as_list(payload):
    if isinstance(payload, list):
        return payload
    return payload.get("combos") or payload.get("data") or []


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "models"
    if cmd == "models":
        list_models()
    elif cmd == "combos":
        create_combos()
    elif cmd == "key" and len(sys.argv) > 2:
        create_key(sys.argv[2])
    else:
        sys.exit(__doc__)
