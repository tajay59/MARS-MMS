#!/bin/sh
# Renders alertmanager.yml.tmpl from the environment, then starts Alertmanager (W20-2).
# Values never hold "|" or newlines (a host, a port, an address list, a password).
set -eu

: "${MMS_ALERT_EMAILS:?set MMS_ALERT_EMAILS to the admin addresses, separated by commas}"
out=/tmp/alertmanager.yml
sed \
  -e "s|__ALERT_SMTP_HOST__|${ALERT_SMTP_HOST:?}|g" \
  -e "s|__ALERT_SMTP_PORT__|${ALERT_SMTP_PORT:?}|g" \
  -e "s|__ALERT_FROM__|${ALERT_FROM:?}|g" \
  -e "s|__ALERT_SMTP_USERNAME__|${ALERT_SMTP_USERNAME:-}|g" \
  -e "s|__ALERT_SMTP_PASSWORD__|${ALERT_SMTP_PASSWORD:-}|g" \
  -e "s|__ALERT_SMTP_REQUIRE_TLS__|${ALERT_SMTP_REQUIRE_TLS:-false}|g" \
  -e "s|__ALERT_GROUP_WAIT__|${ALERT_GROUP_WAIT:-30s}|g" \
  -e "s|__MMS_ALERT_EMAILS__|${MMS_ALERT_EMAILS}|g" \
  -e "s|__MMS_ENVIRONMENT__|${MMS_ENVIRONMENT:-local}|g" \
  /etc/alertmanager/alertmanager.yml.tmpl > "$out"
chmod 600 "$out"
exec /bin/alertmanager --config.file="$out" --storage.path=/alertmanager "$@"
