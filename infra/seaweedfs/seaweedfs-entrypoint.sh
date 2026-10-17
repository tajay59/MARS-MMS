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

exec /usr/bin/weed server \
  -dir=/data \
  -master.volumeSizeLimitMB=1024 \
  -s3 \
  -s3.config=/tmp/s3.json \
  -s3.allowedOrigins="${APP_ORIGIN:?}"
