# Contribuer

## Environnement

```bash
scripts/init_env.sh
scripts/start.sh                # Docker (core) + OmniRoute + API + dashboard
cd agents && uv sync            # Python 3.12+, géré par uv
cd dashboard && npm install     # Node 20+
```

## Avant une pull request

```bash
cd agents && uv run pytest -q tests/test_tools.py tests/test_llm.py
cd dashboard && npm run typecheck
```

- N'ajoute jamais de secret, de jeton ou de chemin personnel dans le code, les workflows n8n ou la documentation : utilise `.env.example` avec des valeurs vides.
- Les prompts des agents (`agents/src/agence/prompts/`) et la documentation sont en français ; le code reste en anglais/français comme dans les fichiers existants.
- Toute nouvelle action externe d'un agent doit passer par la validation humaine (voir `graphs/departments.py`).
- Un outil non configuré doit renvoyer `NotConfigured`, pas lever d'exception.
