#!/bin/sh
# Creates the four private buckets (TRD §10.1). Idempotent.
set -eu
MASTER="${SEAWEEDFS_MASTER:-seaweedfs:9333}"

for _ in $(seq 1 60); do
  if echo "s3.bucket.list" | /usr/bin/weed shell -master="$MASTER" > /tmp/buckets 2>/dev/null; then
    break
  fi
  sleep 1
done

for bucket in mms-originals mms-media mms-documents mms-reports; do
  if grep -q "^  $bucket" /tmp/buckets || grep -qw "$bucket" /tmp/buckets; then
    echo "exists $bucket"
  else
    echo "s3.bucket.create -name $bucket" | /usr/bin/weed shell -master="$MASTER" > /dev/null
    echo "created $bucket"
  fi
done
echo "seaweedfs-init done"
