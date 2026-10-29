#!/bin/bash
# AWS-MMS backups (TRD §16.4; W20-6, W20-7). Run by loop.sh every night, or by hand:
#
#   backup.sh mongo     dump every database, encrypt, copy to the backup host, apply retention
#   backup.sh config    archive the .env and secrets when they changed, encrypted
#   backup.sh objects   compare the SeaweedFS replica with the primary (rclone check)
#   backup.sh all       the three; exits 1 if any failed (the others still ran)
#   backup.sh drill-ok SECONDS   restore.sh --drill reports a passed restore
#
# Nothing here can decrypt a backup: files are encrypted to BACKUP_AGE_RECIPIENT (a public key)
# and the matching private key is kept by the organization, not on any host the stack runs on.
# Each job leaves a reading for node-exporter's textfile collector, which the alerts use.
set -euo pipefail

TEXTFILE="${BACKUP_TEXTFILE_DIR:-/textfile}"
STATE="${BACKUP_STATE_DIR:-/state}"
REMOTE="${BACKUP_REMOTE:?BACKUP_REMOTE is not set (an rclone path such as backup:mms or :local:/backups)}"
KEEP_DAILY="${BACKUP_KEEP_DAILY:-14}"
KEEP_MONTHLY="${BACKUP_KEEP_MONTHLY:-12}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "$(date -u +%FT%TZ) backup: $*"; }

help_for() {
  case "$1" in
    backup_last_success_timestamp_seconds) echo "Unix time of the last good backup job" ;;
    backup_last_size_bytes) echo "Size of the last backup file" ;;
    backup_last_duration_seconds) echo "How long the last backup job took" ;;
    backup_check_ok) echo "1 when the last check found the copy identical, 0 when it did not" ;;
    restore_drill_last_success_timestamp_seconds) echo "Unix time of the last restore drill that passed" ;;
    restore_drill_duration_seconds) echo "How long the last restore drill took (RTO is 8 hours)" ;;
    *) echo "$1" ;;
  esac
}

# prom KIND name=value ... : the node-exporter textfile for one kind of job, written atomically
prom() {
  local kind="$1" tmp name pair
  shift
  tmp="$TEXTFILE/.mms_backup_${kind}.$$"
  for pair in "$@"; do
    name="${pair%%=*}"
    printf '# HELP %s %s\n# TYPE %s gauge\n%s{kind="%s"} %s\n' \
      "$name" "$(help_for "$name")" "$name" "$name" "$kind" "${pair#*=}"
  done > "$tmp"
  mv "$tmp" "$TEXTFILE/mms_backup_${kind}.prom"
}

audit_head() {
  mongosh --quiet "${BACKUP_MONGO_URI:?}" --eval '
    const h = db.getSiblingDB("audit").audit_events.find({}, {seq: 1, hash: 1}).sort({seq: -1}).limit(1).toArray()[0];
    print(JSON.stringify(h ? {seq: h.seq, hash: h.hash} : {seq: 0, hash: null}));' | tail -1
}

backup_mongo() {
  : "${BACKUP_MONGO_URI:?}" "${BACKUP_AGE_RECIPIENT:?}"
  local started stamp work file head size sha
  started="$(date +%s)"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  work="$(mktemp -d)"
  file="mms-${stamp}.archive.age"
  # The head of the audit chain before the dump: a restore must hold this record and have the
  # same hash at that sequence number.
  head="$(audit_head)"
  # Whole instance (--oplog is only valid for that), streamed: no plaintext on disk.
  mongodump --uri="$BACKUP_MONGO_URI" --oplog --archive --gzip --quiet \
    | age -r "$BACKUP_AGE_RECIPIENT" -o "$work/$file"
  size="$(stat -c %s "$work/$file")"
  sha="$(sha256sum "$work/$file" | cut -d' ' -f1)"
  printf '{"file":"%s","taken_at":"%s","size":%s,"sha256":"%s","audit_head":%s,"mongo":"%s"}\n' \
    "$file" "$(date -u +%FT%TZ)" "$size" "$sha" "$head" "$(mongodump --version | head -1 | awk '{print $NF}')" \
    > "$work/${file%.age}.json"
  rclone copy "$work/$file" "$REMOTE/mongo/"
  rclone copy "$work/${file%.age}.json" "$REMOTE/mongo/"
  # The copy on the backup host must be byte for byte the file that was made
  rclone check "$work" "$REMOTE/mongo" --one-way --include "mms-${stamp}.*" --quiet
  rm -rf "$work"
  prune_mongo
  prom mongo "backup_last_success_timestamp_seconds=$(date +%s)" "backup_last_size_bytes=$size" \
    "backup_last_duration_seconds=$(($(date +%s) - started))"
  log "mongo: $file, $size bytes"
}

prune_mongo() {
  local name
  rclone lsf "$REMOTE/mongo" --include 'mms-*.archive.age' \
    | python3 "$HERE/retention.py" --daily "$KEEP_DAILY" --monthly "$KEEP_MONTHLY" \
    | while read -r name; do
        log "retention: removing $name"
        rclone deletefile "$REMOTE/mongo/$name"
        rclone deletefile "$REMOTE/mongo/${name%.age}.json" || true
      done
}

# The .env and the secrets folder, when they changed since the last archive; the last 10 are kept
backup_config() {
  : "${BACKUP_AGE_RECIPIENT:?}"
  local dir="${BACKUP_CONFIG_DIR:-/config}" work stamp sum
  if [ ! -d "$dir" ] || [ -z "$(ls -A "$dir" 2> /dev/null)" ]; then
    log "config: nothing mounted at $dir, skipped"
    return 0
  fi
  work="$(mktemp -d)"
  sum="$(find "$dir" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
  if [ "$(cat "$STATE/config.sha256" 2> /dev/null || true)" = "$sum" ]; then
    log "config: unchanged"
    rm -rf "$work"
    prom config "backup_last_success_timestamp_seconds=$(date +%s)"
    return 0
  fi
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  tar -C "$dir" -cz . | age -r "$BACKUP_AGE_RECIPIENT" -o "$work/config-${stamp}.tar.gz.age"
  rclone copy "$work/config-${stamp}.tar.gz.age" "$REMOTE/config/"
  rm -rf "$work"
  echo "$sum" > "$STATE/config.sha256"
  rclone lsf "$REMOTE/config" --include 'config-*.tar.gz.age' | sort | head -n -10 \
    | while read -r name; do rclone deletefile "$REMOTE/config/$name"; done
  prom config "backup_last_success_timestamp_seconds=$(date +%s)"
  log "config: archived"
}

# The replica is filled continuously by `weed filer.sync`; this proves it matches the primary
check_objects() {
  if [ -z "${BACKUP_REPLICA_S3_ENDPOINT:-}" ]; then
    log "objects: no replica configured, skipped"
    return 0
  fi
  export RCLONE_CONFIG_PRIMARY_TYPE=s3 RCLONE_CONFIG_PRIMARY_PROVIDER=Other
  export RCLONE_CONFIG_PRIMARY_ENDPOINT="${BACKUP_PRIMARY_S3_ENDPOINT:-http://seaweedfs:8333}"
  export RCLONE_CONFIG_PRIMARY_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY:?}"
  export RCLONE_CONFIG_PRIMARY_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY:?}"
  export RCLONE_CONFIG_REPLICA_TYPE=s3 RCLONE_CONFIG_REPLICA_PROVIDER=Other
  export RCLONE_CONFIG_REPLICA_ENDPOINT="$BACKUP_REPLICA_S3_ENDPOINT"
  export RCLONE_CONFIG_REPLICA_ACCESS_KEY_ID="${BACKUP_REPLICA_S3_ACCESS_KEY:-$BACKUP_S3_ACCESS_KEY}"
  export RCLONE_CONFIG_REPLICA_SECRET_ACCESS_KEY="${BACKUP_REPLICA_S3_SECRET_KEY:-$BACKUP_S3_SECRET_KEY}"
  local bucket ok=1
  # BACKUP_BUCKETS narrows the check to some buckets (the tests); the default is every bucket
  for bucket in ${BACKUP_BUCKETS:-$(rclone lsf primary: | tr -d /)}; do
    # One way: files the replica holds that the primary deleted are for the replica's own versioning
    if ! rclone check "primary:$bucket" "replica:$bucket" --one-way --quiet; then
      log "objects: $bucket differs from its replica"
      ok=0
    fi
  done
  if [ "$ok" = 1 ]; then
    prom objects "backup_check_ok=1" "backup_last_success_timestamp_seconds=$(date +%s)"
    log "objects: replica matches"
  else
    prom objects "backup_check_ok=0"
    return 1
  fi
}

case "${1:?usage: backup.sh mongo|config|objects|all}" in
  mongo) backup_mongo ;;
  config) backup_config ;;
  objects) check_objects ;;
  drill-ok) prom drill "restore_drill_last_success_timestamp_seconds=$(date +%s)" "restore_drill_duration_seconds=${2:?seconds}" ;;
  all)
    # Each job in a shell of its own: inside `||` a failing step would not stop the function, and
    # a success reading must never be written after a failure.
    failed=0
    for job in mongo config objects; do
      "$0" "$job" || { log "$job failed"; failed=1; }
    done
    exit "$failed"
    ;;
  *) echo "unknown job: $1" >&2; exit 2 ;;
esac
