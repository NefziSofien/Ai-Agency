#!/usr/bin/env bash
# Génère .env à partir de .env.example en remplissant les secrets vides.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  echo ".env existe déjà, rien à faire."
  exit 0
fi

rand() { openssl rand -hex "${1:-24}"; }

cp .env.example .env
set_var() { sed -i "s|^$1=.*|$1=$2|" .env; }

pg_pass=$(rand)
set_var POSTGRES_PASSWORD "$pg_pass"
set_var DATABASE_URL "postgresql://agence:${pg_pass}@localhost:5433/agence"
set_var ADMIN_PASSWORD "$(rand 12)"
set_var AGENCE_API_KEY "$(rand)"
set_var REDIS_PASSWORD "$(rand)"
set_var S3_SECRET_KEY "$(rand)"
set_var LANGFUSE_PUBLIC_KEY "pk-lf-$(rand 16)"
set_var LANGFUSE_SECRET_KEY "sk-lf-$(rand 16)"
set_var LANGFUSE_SALT "$(rand)"
set_var LANGFUSE_ENCRYPTION_KEY "$(rand 32)"
set_var LANGFUSE_NEXTAUTH_SECRET "$(rand)"
set_var CLICKHOUSE_PASSWORD "$(rand)"
set_var N8N_ENCRYPTION_KEY "$(rand)"
set_var SEARXNG_SECRET "$(rand)"
set_var POSTIZ_JWT_SECRET "$(rand)"
set_var TWENTY_APP_SECRET "$(rand)"

chmod 600 .env
echo ".env créé. Renseigne OMNIROUTE_API_KEY (dashboard OmniRoute -> API Keys)."
