#!/usr/bin/env bash
#
# Dumps the database to ./backups and drops anything older than KEEP_DAYS.
#
#     ./scripts/backup.sh              # nightly, from cron
#     ./scripts/backup.sh pre-migrate  # labelled, before a risky change
#
# The whole point of this bot is a training history that took months to
# accumulate. It lives in a Docker volume, which survives a container being
# rebuilt and does not survive a mistake - a bad migration, a stray
# `docker compose down -v`, a dead disk. So: a dump before every deploy that
# touches migrations, and one every night.
#
# Restore:
#     docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" \
#         -d "$POSTGRES_DB" --clean --if-exists < backups/<file>.dump
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "backup: no .env next to compose.yaml" >&2
    exit 1
fi

# Only the three values needed here, so a malformed line elsewhere in .env
# cannot take the backup down with it.
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2-)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2-)
KEEP_DAYS=${KEEP_DAYS:-14}

: "${POSTGRES_USER:?POSTGRES_USER missing from .env}"
: "${POSTGRES_DB:?POSTGRES_DB missing from .env}"

label=${1:-nightly}

# On the very first deploy there is no database container yet, and the deploy
# runs this before starting one. Nothing to protect is not a failure.
if [ -z "$(docker compose ps -q postgres 2>/dev/null)" ]; then
    echo "backup: postgres is not running, nothing to dump"
    exit 0
fi

mkdir -p backups
target="backups/${POSTGRES_DB}-$(date -u +%Y%m%dT%H%M%SZ)-${label}.dump"

# -Fc is the custom format: compressed, and pg_restore can pick single
# tables out of it. Writing through the host shell rather than into the
# container keeps the dump outside the volume it is protecting.
docker compose exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$target.partial"

# Rename only on success: a half-written file that looks like a backup is
# worse than no file, because it is only discovered when it is needed.
mv "$target.partial" "$target"

size=$(du -h "$target" | cut -f1)
echo "backup: $target ($size)"

deleted=$(find backups -name "${POSTGRES_DB}-*.dump" -mtime "+${KEEP_DAYS}" -print -delete | wc -l)
if [ "$deleted" -gt 0 ]; then
    echo "backup: removed $deleted dump(s) older than ${KEEP_DAYS} days"
fi

# Leftovers from dumps that failed. Kept for a day in case someone wants to
# look at one, then cleared: the backups directory is read during an
# incident, and it should hold backups, not debris.
find backups -name "*.dump.partial" -mtime +1 -delete
