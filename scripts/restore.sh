#!/usr/bin/env bash
# Restaure une sauvegarde créée par backup.sh : scripts/restore.sh backups/2026-10-10_0200
# Arrête l'API et le dashboard avant (scripts/start.sh --stop puis docker compose --profile core up -d).
set -euo pipefail
cd "$(dirname "$0")/.."
src=${1:?Usage : scripts/restore.sh backups/<date>}
set -a; source .env; set +a

read -rp "Restaurer $src ? Les données actuelles seront écrasées. [o/N] " ok
[[ $ok == "o" ]] || exit 1

gunzip -c "$src/postgres.sql.gz" | docker compose --profile core exec -T postgres psql -U "$POSTGRES_USER" -d postgres -q

docker run --rm --network agence-ia_default --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" -e AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" -e AWS_DEFAULT_REGION=us-east-1 \
  -v "$(pwd)/$src/s3:/backup:ro" amazon/aws-cli:latest \
  --endpoint-url http://s3:9000 s3 sync /backup/"$S3_BUCKET_ASSETS" s3://"$S3_BUCKET_ASSETS" --only-show-errors

echo "Pour OmniRoute : arrête-le puis copie $src/omniroute-storage.sqlite vers ~/.omniroute/storage.sqlite."
