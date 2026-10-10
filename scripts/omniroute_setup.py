"""Administration d'OmniRoute pour l'agence : combos par rôle, clés et quotas par client.

Le token d'administration se crée dans le dashboard OmniRoute (Settings -> Access Tokens).

    export OMNIROUTE_ADMIN_TOKEN=oma_live_xxx
    uv run --project agents python scripts/omniroute_setup.py models
    uv run --project agents python scripts/omniroute_setup.py combos
    uv run --project agents python scripts/omniroute_setup.py key "Client ACME" --daily 5 --weekly 25
    uv run --project agents python scripts/omniroute_setup.py quota <key_id> --daily 10 --weekly 50
    uv run --project agents python scripts/omniroute_setup.py keys

Modèles des combos : COMBO_STRATEGIE_MODELS, COMBO_REDACTION_MODELS, COMBO_RAPIDE_MODELS
(listes "provider/model,provider/model" par ordre de priorité, voir la commande `models`).
Une fois les combos créés, mets MODEL_STRATEGIE=agence-strategie, etc. dans .env.
"""

import argparse
import os
import sys

import httpx

BASE = os.environ.get("OMNIROUTE_URL", "http://localhost:20128").rstrip("/")
ROLES = {
    "agence-strategie": ("COMBO_STRATEGIE_MODELS", "Raisonnement : stratégie, analyse, planification"),
    "agence-redaction": ("COMBO_REDACTION_MODELS", "Rédaction : contenus, copywriting, emails"),
    "agence-rapide": ("COMBO_RAPIDE_MODELS", "Tâches légères : contrôle qualité, synthèses"),
}


def _client() -> httpx.Client:
    token = os.environ.get("OMNIROUTE_ADMIN_TOKEN")
    if not token:
        sys.exit("OMNIROUTE_ADMIN_TOKEN manquant (dashboard OmniRoute -> Settings -> Access Tokens).")
    return httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=30)


def _check(r: httpx.Response) -> dict:
    if r.is_error:
        sys.exit(f"Erreur OmniRoute {r.status_code} : {r.text[:500]}")
    return r.json() if r.content else {}


def _items(payload, key: str) -> list:
    if isinstance(payload, list):
        return payload
    return payload.get(key) or payload.get("data") or []


def models(_args) -> None:
    with _client() as c:
        for m in _items(_check(c.get("/v1/models")), "data"):
            print(m["id"])


def combos(_args) -> None:
    with _client() as c:
        existing = {x.get("name"): x for x in _items(_check(c.get("/api/combos")), "combos")}
        for name, (env, description) in ROLES.items():
            chosen = [m.strip() for m in os.environ.get(env, "").split(",") if m.strip()]
            if not chosen:
                print(f"- {name} : ignoré, définir {env}")
                continue
            body = {"name": name, "models": chosen, "strategy": "priority", "description": description}
            if name in existing:
                _check(c.put(f"/api/combos/{existing[name]['id']}", json=body))
            else:
                _check(c.post("/api/combos", json=body))
            print(f"- {name} : {' > '.join(chosen)}")


def _limits(args) -> dict:
    limits = {}
    if args.daily is not None:
        limits["dailyUsageLimitUsd"] = args.daily
    if args.weekly is not None:
        limits["weeklyUsageLimitUsd"] = args.weekly
    if limits:
        limits["usageLimitEnabled"] = True
    return limits


def key(args) -> None:
    with _client() as c:
        data = _check(c.post("/api/keys", json={"name": args.name, **_limits(args)}))
    value = data.get("key") or (data.get("apiKey") or {}).get("key")
    print(f"Clé créée pour {args.name} : {value or data}")
    print("Colle-la dans la fiche client du dashboard de l'agence (champ « Clé OmniRoute dédiée »).")


def quota(args) -> None:
    limits = _limits(args)
    if not limits:
        sys.exit("Indique --daily et/ou --weekly (en dollars).")
    with _client() as c:
        _check(c.patch(f"/api/keys/{args.key_id}", json=limits))
    print(f"Quotas appliqués à {args.key_id} : {limits}")


def keys(_args) -> None:
    with _client() as c:
        for k in _items(_check(c.get("/api/keys")), "keys"):
            print(f"{k.get('id')}  {k.get('name') or k.get('label')}  actif={k.get('isActive', k.get('is_active'))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models").set_defaults(fn=models)
    sub.add_parser("combos").set_defaults(fn=combos)
    sub.add_parser("keys").set_defaults(fn=keys)
    for name, fn in (("key", key), ("quota", quota)):
        p = sub.add_parser(name)
        p.add_argument("name" if name == "key" else "key_id")
        p.add_argument("--daily", type=float)
        p.add_argument("--weekly", type=float)
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)
