#!/bin/bash
# Writes the replica-set key file from the environment with the permissions mongod demands
# (owner-only, owned by mongodb), then hands over to the image's own entrypoint.
set -euo pipefail
# A restarted container (host reboot, crash, `docker restart`) still has the last start's file.
# /tmp is sticky and world-writable, so with fs.protected_regular (2 on Ubuntu and in Docker
# Desktop) even root may not reopen a file mongodb owns there: delete it and write a new one.
rm -f /tmp/mongo-keyfile
umask 077
printf '%s' "${MONGO_KEYFILE_CONTENT:?}" > /tmp/mongo-keyfile
chmod 400 /tmp/mongo-keyfile
chown mongodb:mongodb /tmp/mongo-keyfile
unset MONGO_KEYFILE_CONTENT
exec /usr/local/bin/docker-entrypoint.sh "$@"
