"""Test de bout en bout contre une API lancée sur le faux OmniRoute (voir tests/mock_omniroute.py).

AGENCE_TEST_URL=http://localhost:8010 uv run python tests/e2e.py
"""

import os
import time

import httpx

from agence.config import settings

BASE = os.environ.get("AGENCE_TEST_URL", "http://localhost:8010")
http = httpx.Client(base_url=BASE, headers={"X-API-Key": settings().agence_api_key}, timeout=30)


def wait(run_id: str, until: set[str]) -> dict:
    for _ in range(120):
        data = http.get(f"/runs/{run_id}").raise_for_status().json()
        if data["run"]["status"] in until:
            return data
        time.sleep(0.5)
    raise TimeoutError(run_id)


def main() -> None:
    assert http.get("/health").json()["api"] == "ok"
    http.delete("/clients/client-test-e2e")
    client = http.post(
        "/clients",
        json={
            "name": "Client Test E2E",
            "website": "https://example.com",
            "brand_kit": {"ton": "chaleureux et expert", "interdits": ["jargon"], "cibles": "PME"},
            "settings": {"daily_watch": False},
        },
    ).raise_for_status().json()
    assert client["id"] == "client-test-e2e" and not client["has_omniroute_key"]

    run = http.post("/runs", json={"client_id": client["id"], "brief": "Lancement de notre offre IA sur LinkedIn"}).json()
    data = wait(run["id"], {"awaiting_approval", "failed"})
    assert data["run"]["status"] == "awaiting_approval", data["run"]["error"]

    state = data["state"]
    assert [t["department"] for t in state["plan"]] == ["contenu", "social"]
    assert state["revisions"] == 1, "le Brand Guardian aurait dû demander une révision"
    actions = state["interrupt"]["actions"]
    assert [a["kind"] for a in actions] == ["postiz_schedule"], actions
    report = next(a for a in data["assets"] if a["kind"] == "report")
    assert httpx.get(report["url"]).content.startswith(b"%PDF"), "PDF illisible"
    assert data["usage"]["calls"] > 0

    http.post(f"/runs/{run['id']}/decision", json={"approved": True, "approved_action_ids": [actions[0]["id"]]}).raise_for_status()
    data = wait(run["id"], {"completed", "failed"})
    executed = data["state"]["executed"]
    assert len(executed) == 1 and executed[0]["kind"] == "postiz_schedule"
    # Sans Postiz configuré, l'action échoue proprement sans faire échouer le run.
    assert data["run"]["status"] == "completed"

    auto = http.post("/automations/daily-watch", params={"client_id": client["id"]}).json()
    assert len(auto["started"]) == 1
    watch = wait(auto["started"][0]["run_id"], {"completed", "failed", "awaiting_approval"})
    assert watch["run"]["status"] == "completed", "une veille sans action doit se terminer sans validation"

    assert httpx.get(f"{BASE}/runs").status_code == 401, "l'API doit exiger X-API-Key"

    print("OK", run["id"], "| action exécutée :", executed[0])
    print("Usage :", http.get("/usage").json()["by_client"])


if __name__ == "__main__":
    main()
