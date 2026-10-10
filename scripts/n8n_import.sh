#!/usr/bin/env bash
# Importe (ou met à jour) les workflows de n8n/workflows dans l'instance n8n locale.
# Les workflows sont importés désactivés : active-les dans l'interface après vérification.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --profile automation exec -T n8n n8n import:workflow --separate --input=/workflows
echo "Workflows importés. Ouvre http://localhost:5678 pour les activer."
