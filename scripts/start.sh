#!/usr/bin/env bash
# Démarre l'écosystème en local : Docker (profils choisis), OmniRoute, API des agents, dashboard.
#   scripts/start.sh                      -> profil core
#   scripts/start.sh observability social -> core + profils supplémentaires
#   scripts/start.sh --stop               -> arrête l'API, le dashboard et les conteneurs
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
mkdir -p logs

stop_pid() {
  local f="logs/$1.pid"
  if [[ -f $f ]] && kill -0 "$(cat "$f")" 2>/dev/null; then
    kill -- "-$(cat "$f")" 2>/dev/null || kill "$(cat "$f")"
  fi
  rm -f "$f"
}

if [[ ${1:-} == "--stop" ]]; then
  stop_pid api
  stop_pid dashboard
  docker compose --profile core --profile observability --profile automation --profile social --profile crm stop
  exit 0
fi

[[ -f .env ]] || scripts/init_env.sh

profiles=(--profile core)
for p in "$@"; do profiles+=(--profile "$p"); done
docker compose "${profiles[@]}" up -d

wait_http() {
  for _ in $(seq 1 60); do
    curl -s -o /dev/null "$1" && return 0
    sleep 2
  done
  echo "  $1 ne répond pas (voir logs/)." >&2
}

if ! curl -s -o /dev/null http://localhost:20129; then
  echo "Démarrage d'OmniRoute…"
  setsid nohup npx -y omniroute serve --port 20129 > logs/omniroute.log 2>&1 &
  wait_http http://localhost:20129
fi

start_bg() {
  local name=$1 dir=$2
  shift 2
  stop_pid "$name"
  (cd "$dir" && setsid nohup "$@" > "$ROOT/logs/$name.log" 2>&1 & echo $! > "$ROOT/logs/$name.pid")
}

(cd agents && uv sync -q)
start_bg api agents uv run uvicorn agence.api.main:app --host 0.0.0.0 --port 8000
wait_http http://localhost:8000/docs

[[ -d dashboard/node_modules ]] || (cd dashboard && npm install --silent)
start_bg dashboard dashboard npm run dev
wait_http http://localhost:3000

cat <<EOF

Écosystème démarré :
  Dashboard agence   http://localhost:3000
  API des agents     http://localhost:8000/docs
  OmniRoute          http://localhost:20129
  Stockage S3        http://localhost:9001
  Langfuse           http://localhost:3001   (profil observability)
  n8n                http://localhost:5678   (profil automation)
  Postiz             http://localhost:4007   (profil social)
  Twenty CRM         http://localhost:3002   (profil crm)
  Listmonk           http://localhost:9002   (profil crm)
Logs : $ROOT/logs/
EOF
