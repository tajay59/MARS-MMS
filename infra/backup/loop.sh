#!/bin/bash
# The backup container's main process (W20-6): runs `backup.sh all` once a day from BACKUP_HOUR
# (UTC), and again every 30 minutes after a failure until it works. Without a key to encrypt
# to it refuses to start, so a host never keeps unencrypted backups by mistake.
set -uo pipefail

if [ -z "${BACKUP_AGE_RECIPIENT:-}" ]; then
  echo "refusing to start: set BACKUP_AGE_RECIPIENT to the organization's age public key (age1...)" >&2
  exit 1
fi
hour="$((10#${BACKUP_HOUR:-2}))"
state="${BACKUP_STATE_DIR:-/state}"

echo "$(date -u +%FT%TZ) backup: waiting for ${hour}:00 UTC; remote ${BACKUP_REMOTE:-unset}"
while true; do
  today="$(date -u +%F)"
  if [ "$((10#$(date -u +%H)))" -ge "$hour" ] && [ "$(cat "$state/last_ok" 2> /dev/null)" != "$today" ]; then
    if /opt/backup/backup.sh all; then
      echo "$today" > "$state/last_ok"
    else
      echo "$(date -u +%FT%TZ) backup: failed, trying again in 30 minutes" >&2
      sleep 1800
      continue
    fi
  fi
  sleep 300
done
