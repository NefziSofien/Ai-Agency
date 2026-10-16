#!/usr/bin/env bash
# Sauvegarde locale : bases Postgres, stockage S3 (assets, Langfuse), base OmniRoute, .env.
# Conserve les 14 dernières sauvegardes. À planifier avec cron, par exemple :
#   0 2 * * * /chemin/vers/agence-ia/scripts/backup.sh >> /chemin/vers/agence-ia/logs/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

stamp=$(date +%Y-%m-%d_%H%M)
dest="backups/$stamp"
mkdir -p "$dest/s3"

echo "[$stamp] Postgres…"
docker compose --profile core exec -T postgres pg_dumpall --clean --if-exists -U "$POSTGRES_USER" | gzip > "$dest/postgres.sql.gz"

echo "[$stamp] Stockage S3…"
docker run --rm --network agence-ia_default --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" -e AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" -e AWS_DEFAULT_REGION=us-east-1 \
  -v "$(pwd)/$dest/s3:/backup" amazon/aws-cli:latest \
  --endpoint-url http://s3:9000 s3 sync s3://"$S3_BUCKET_ASSETS" /backup/"$S3_BUCKET_ASSETS" --only-show-errors

echo "[$stamp] OmniRoute…"
if command -v sqlite3 >/dev/null; then
  sqlite3 "$HOME/.omniroute/storage.sqlite" ".backup '$dest/omniroute-storage.sqlite'"
else
  cp "$HOME/.omniroute/storage.sqlite" "$dest/omniroute-storage.sqlite"
fi

cp .env "$dest/env"
chmod -R go-rwx "$dest"

ls -1d backups/*/ | sort | head -n -14 | xargs -r rm -rf
echo "[$stamp] Sauvegarde terminée : $dest ($(du -sh "$dest" | cut -f1))"
