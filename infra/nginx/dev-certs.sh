#!/bin/sh
# Local only: a self-signed certificate for the app and files hosts, made once and kept in
# infra/nginx/certs (git-ignored). Staging and production mount real certificates instead.
set -eu
if [ -s /certs/tls.crt ] && [ -s /certs/tls.key ]; then
  echo "dev certificate exists"
  exit 0
fi
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout /certs/tls.key -out /certs/tls.crt \
  -subj "/CN=${MMS_HOST}" \
  -addext "subjectAltName=DNS:${MMS_HOST},DNS:${FILES_HOST}" 2> /dev/null
chmod 644 /certs/tls.crt /certs/tls.key
echo "dev certificate created for ${MMS_HOST} and ${FILES_HOST}"
