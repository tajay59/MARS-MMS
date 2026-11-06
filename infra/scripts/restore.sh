#!/bin/bash
# Restore AWS-MMS from a backup (TRD §16.4; W20-8, W20-9). Run from a shell on the host:
#
#   infra/scripts/restore.sh --file mms-20261029T020000Z.archive.age --identity /safe/age-key.txt
#
# What it does, in this order (each step stops the script if it fails):
#   1. fetches the file and checks it against its manifest (SHA-256), decrypts it and reads it
#      through once without writing (mongorestore --dryRun): a bad file is found before anything
#      is deleted
#   2. stops the application services and queue workers
#   3. drops the six service databases, restores the dump and makes the MongoDB users of this
#      host's .env again (the dump brings the users it was taken with)
#   4. empties Redis (queues, caches, leases and locks refer to the state that was just replaced)
#   5. resets every consumer group to the start, so events produced after the backup are applied
#      again (`processed_events` makes the replay safe; the audit chain continues from the dump)
#   6. starts the services, ends every session (a dump brings back users and sessions as they
#      were: finding F18), and rebuilds the report read model from operations' snapshots
#   7. waits for the consumers to catch up, then checks the audit chain is intact and holds the
#      record the backup noted (the head it saw before dumping)
#
# The private key stays with you: pass the file that holds it with --identity. Nothing from it is
# kept. `--drill` also records the time the restore took for the alert RestoreDrillOld.
#
# What a restore cannot do: bring back work done after the backup. A phone that synced a visit
# after the dump deleted its local copy once the server confirmed (OFF-8), so that visit is gone;
# say so to the technicians (docs site, Infrastructure > Backups and restore).
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: do not rewrite container paths

cd "$(dirname "$0")/.."
COMPOSE_FILES="${COMPOSE_FILES:--f compose.yml -f compose.dev.yml -f compose.backup.yml}"
CATCH_UP_S="${RESTORE_CATCH_UP_S:-900}"
SERVICES="auth operations media report platform media-worker report-worker"
GROUPS_TO_RESET="operations media report audit notification"

file="" identity="" drill=0 yes=0
while [ $# -gt 0 ]; do
  case "$1" in
    --file) file="$2"; shift 2 ;;
    --identity) identity="$2"; shift 2 ;;
    --drill) drill=1; shift ;;
    --yes) yes=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[ -n "$file" ] && [ -n "$identity" ] || { echo "usage: restore.sh --file NAME.archive.age --identity KEYFILE [--yes] [--drill]" >&2; exit 2; }
[ -f "$identity" ] || { echo "no such identity file: $identity" >&2; exit 2; }

# shellcheck disable=SC2086
dc() { docker compose $COMPOSE_FILES "$@"; }
say() { echo "$(date -u +%FT%TZ) restore: $*"; }
env_value() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }

ROOT_URI="mongodb://root:$(env_value MONGO_ROOT_PASSWORD)@mongo:27017/?authSource=admin&directConnection=true"
REDIS_PASSWORD="$(env_value REDIS_PASSWORD)"

if [ "$yes" != 1 ]; then
  echo "This REPLACES every database on this host with the contents of $file."
  echo "Work done after that backup is lost. Type the word restore to go on:"
  read -r answer
  [ "$answer" = restore ] || { echo "stopped"; exit 1; }
fi
started="$(date +%s)"

# One-off containers of the backup image, with the key mounted for this run only
in_backup() {
  dc run --rm --no-deps -T -v "$identity:/id/key.txt:ro" -e "RESTORE_URI=$ROOT_URI" \
    --entrypoint bash backup -c "$1"
}
stream='rclone cat "${BACKUP_REMOTE}/mongo/'"$file"'" | age -d -i /id/key.txt'

say "1/7 checking the file"
manifest="$(in_backup 'rclone cat "${BACKUP_REMOTE}/mongo/'"${file%.age}"'.json"')"
expect_sha="$(echo "$manifest" | sed -n 's/.*"sha256":"\([0-9a-f]*\)".*/\1/p')"
head_seq="$(echo "$manifest" | sed -n 's/.*"audit_head":{"seq":\([0-9]*\),.*/\1/p')"
head_hash="$(echo "$manifest" | sed -n 's/.*"audit_head":{"seq":[0-9]*,"hash":"\([0-9a-f]*\)".*/\1/p')"
[ -n "$expect_sha" ] || { echo "the manifest of $file could not be read" >&2; exit 1; }
got_sha="$(in_backup 'rclone cat "${BACKUP_REMOTE}/mongo/'"$file"'" | sha256sum | cut -d" " -f1')"
[ "$got_sha" = "$expect_sha" ] || { echo "$file does not match its manifest: it is damaged or was changed" >&2; exit 1; }
in_backup "$stream"' | mongorestore --uri "$RESTORE_URI" --archive --gzip --dryRun --quiet'

say "2/7 stopping the services"
# shellcheck disable=SC2086
dc stop $SERVICES

say "3/7 restoring MongoDB"
in_backup 'mongosh --quiet "$RESTORE_URI" --eval "for (const d of [\"auth\",\"operations\",\"media\",\"report\",\"notification\",\"audit\"]) db.getSiblingDB(d).dropDatabase()"'
# The whole dump with its oplog, which is how it is a single moment in time (mongorestore cannot
# replay an oplog and leave namespaces out). It brings the dump's MongoDB users with it, so the
# users this host's .env expects are made again from it afterwards.
in_backup "$stream"' | mongorestore --uri "$RESTORE_URI" --archive --gzip --oplogReplay --quiet'
dc run --rm --no-deps -T mongo-init > /dev/null

say "4/7 emptying Redis"
dc exec -T redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning FLUSHALL > /dev/null

say "5/7 resetting the consumer groups"
for group in $GROUPS_TO_RESET; do
  for _ in $(seq 1 30); do
    # A group is inactive once its members' sessions have timed out (up to 45 s)
    if dc exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server 127.0.0.1:9094 \
        --group "$group" --reset-offsets --to-earliest --all-topics --execute > /dev/null 2>&1; then
      break
    fi
    sleep 3
  done
done

say "6/7 starting the services, ending every session, rebuilding the read model"
# shellcheck disable=SC2086
dc up -d $SERVICES
for svc in auth operations media report platform; do
  for _ in $(seq 1 90); do
    cid="$(dc ps -q "$svc")"
    [ -n "$cid" ] && [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy ] && break
    sleep 2
  done
done
dc exec -T auth python -m app.cli revoke-all-sessions --reason restore
dc exec -T report python -m app.cli backfill

say "7/7 waiting for the consumers, then checking the audit chain"
deadline=$(($(date +%s) + CATCH_UP_S))
while true; do
  lag=0
  for group in $GROUPS_TO_RESET; do
    n="$(dc exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server 127.0.0.1:9094 \
          --describe --group "$group" 2> /dev/null | awk 'NR > 1 && $6 ~ /^[0-9]+$/ { s += $6 } END { print s + 0 }')"
    lag=$((lag + n))
  done
  [ "$lag" = 0 ] && break
  [ "$(date +%s)" -lt "$deadline" ] || { echo "the consumers did not catch up in ${CATCH_UP_S} s ($lag messages left)" >&2; exit 1; }
  sleep 5
done
if [ -n "$head_seq" ] && [ "$head_seq" != 0 ]; then
  dc exec -T platform python -m app.cli verify-audit --at-seq "$head_seq" --hash "$head_hash"
else
  dc exec -T platform python -m app.cli verify-audit
fi

took=$(($(date +%s) - started))
if [ "$drill" = 1 ]; then
  dc run --rm --no-deps -T --entrypoint /opt/backup/backup.sh backup drill-ok "$took" > /dev/null
fi
say "done in ${took} s. Everyone has to sign in again. Tell the technicians which visits were synced after $(echo "$manifest" | sed -n 's/.*"taken_at":"\([^"]*\)".*/\1/p')."
