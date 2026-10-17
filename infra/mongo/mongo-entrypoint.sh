#!/bin/bash
# Writes the replica-set key file from the environment with the permissions mongod demands
# (owner-only, owned by mongodb), then hands over to the image's own entrypoint.
set -euo pipefail
printf '%s' "${MONGO_KEYFILE_CONTENT:?}" > /tmp/mongo-keyfile
chmod 400 /tmp/mongo-keyfile
chown mongodb:mongodb /tmp/mongo-keyfile
unset MONGO_KEYFILE_CONTENT
exec /usr/local/bin/docker-entrypoint.sh "$@"
