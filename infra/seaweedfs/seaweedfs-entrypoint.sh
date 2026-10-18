#!/bin/sh
# Renders the S3 identities from the environment, then starts SeaweedFS with the S3 gateway
# (master, volume, filer and S3 in one process, TRD §16.1). CORS allows only the app origin.
set -eu

render() {
  sed \
    -e "s|\${MEDIA_S3_ACCESS_KEY}|${MEDIA_S3_ACCESS_KEY}|" \
    -e "s|\${MEDIA_S3_SECRET_KEY}|${MEDIA_S3_SECRET_KEY}|" \
    -e "s|\${REPORT_S3_ACCESS_KEY}|${REPORT_S3_ACCESS_KEY}|" \
    -e "s|\${REPORT_S3_SECRET_KEY}|${REPORT_S3_SECRET_KEY}|" \
    -e "s|\${ADMIN_S3_ACCESS_KEY}|${ADMIN_S3_ACCESS_KEY}|" \
    -e "s|\${ADMIN_S3_SECRET_KEY}|${ADMIN_S3_SECRET_KEY}|" \
    /opt/mms/s3.template.json
}

umask 077
render > /tmp/s3.json

# Volume slots (found on the first multi-bucket upload, W6): the volume server allows 8
# volumes by default, a bucket takes 7 more the first time it receives data, and the filer's
# own volumes count too, so the second bucket to be written to failed with "No writable
# volumes". `-volume.max=0` sizes the limit from the free disk (free space / volume size),
# and 256 MB volumes give four times as many slots per GB as 1024 MB ones. A file bigger than
# a volume is stored in chunks, so the limit does not cap file size. Volumes are sparse: they
# take disk only as data arrives. `-volume.minFreeSpace` marks volumes read-only before the
# disk fills (the monitoring alert is at 80%, TRD §17).
exec /usr/bin/weed server \
  -dir=/data \
  -master.volumeSizeLimitMB=256 \
  -volume.max=0 \
  -volume.minFreeSpace=5 \
  -s3 \
  -s3.config=/tmp/s3.json \
  -s3.allowedOrigins="${APP_ORIGIN:?}"
