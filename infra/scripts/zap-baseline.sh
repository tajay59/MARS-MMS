#!/bin/bash
# A passive OWASP ZAP baseline of a running site, with the details the CI job does not print
# (the repository is public, so its logs show counts only). W20 slice 5.
#
#   infra/scripts/zap-baseline.sh https://rnd.yanacreations.com          # staging
#   infra/scripts/zap-baseline.sh https://mms.localhost --local          # the local stack
#
# --local maps the name to this machine (the local stack answers on 127.0.0.1 with a
# self-signed certificate). The report lands in ./zap-report/ (git-ignored): keep it out of the
# repository, issues and chat until each finding is fixed. Passive means it spiders the site and
# reads the responses; it sends no attack. Never point it at a shared server's other sites.
set -euo pipefail
export MSYS_NO_PATHCONV=1

target="${1:?usage: zap-baseline.sh URL [--local]}"
extra=()
if [ "${2:-}" = "--local" ]; then
  host="${target#*://}"; host="${host%%/*}"
  extra=(--add-host "$host:host-gateway")
fi

out="$(pwd)/zap-report"
mkdir -p "$out"
cp "$(dirname "$0")/../../.zap/rules.tsv" "$out/rules.tsv"
chmod 777 "$out" 2> /dev/null || true

docker run --rm "${extra[@]}" -v "$out:/zap/wrk:rw" ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t "$target" -c rules.tsv -r report.html -J report.json -I -m 3 || true

"$(command -v python3 || command -v python)" "$(dirname "$0")/../../.zap/summarize.py" "$out/report.json" || true
echo "report: $out/report.html"
