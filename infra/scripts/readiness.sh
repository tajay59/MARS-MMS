#!/usr/bin/env bash
# Is this site ready for people? (W23-3)
#
#   readiness.sh URL [--files HOST] [--expect-version X.Y.Z] [--insecure] [--via HOST:PORT]
#       From anywhere, with curl and openssl: what a browser and a phone meet at the gateway.
#       Only GET requests, no account, nothing written.
#   readiness.sh --on-host [DIR]
#       On the host, in the stack's folder (default /opt/mms/infra): the .env, the containers,
#       the audit chain and the backups. Reads only.
#
# Prints one line per check (PASS, FAIL, SKIP, INFO) and exits 1 when any failed. It prints
# names and counts, never a value from .env: the repository and its CI logs are public.
#
# --insecure accepts a self-signed certificate (the local stack); --via sends every request to
# HOST:PORT whatever the URL says (the local stack on 127.0.0.1:443, or staging's
# 127.0.0.1:8453 from the host itself).
set -u

PASSED=0
FAILED=0
SKIPPED=0
pass() { printf 'PASS  %s\n' "$1"; PASSED=$((PASSED + 1)); }
fail() { printf 'FAIL  %s%s\n' "$1" "${2:+: $2}"; FAILED=$((FAILED + 1)); }
skip() { printf 'SKIP  %s%s\n' "$1" "${2:+: $2}"; SKIPPED=$((SKIPPED + 1)); }
info() { printf 'INFO  %s\n' "$1"; }
# check NAME DETAIL test...: PASS when the test command succeeds
check() {
  local name="$1" detail="$2"
  shift 2
  if "$@"; then pass "$name"; else fail "$name" "$detail"; fi
}
finish() {
  printf '\n%d passed, %d failed, %d skipped\n' "$PASSED" "$FAILED" "$SKIPPED"
  [ "$FAILED" -eq 0 ]
  exit $?
}
usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

# =============================================================================================
# On the host
# =============================================================================================

on_host() {
  local dir="${1:-/opt/mms/infra}" env example environment key value missing copied
  env="$dir/.env"
  example="$dir/.env.example"
  [ -f "$env" ] || { fail ".env exists" "no $env"; finish; }
  cd "$dir" || { fail "stack folder" "cannot enter $dir"; finish; }

  envval() { grep -E "^$1=" "$env" | tail -n 1 | cut -d= -f2-; }
  haskey() { grep -qE "^$1=" "$env"; }

  environment="$(envval MMS_ENVIRONMENT)"
  info "environment: ${environment:-not set}"
  check "MMS_ENVIRONMENT is production or staging" "it is '${environment}'" \
    test "$environment" = production -o "$environment" = staging

  if [ "$(uname -s)" = Linux ]; then
    check ".env is readable by its owner only" "mode $(stat -c %a "$env"), expected 600" \
      test "$(stat -c %a "$env")" = 600
  else
    skip ".env is readable by its owner only" "not a Linux host"
  fi

  # Every key the example names, and the ones only a real host has. Dev-only keys are left out.
  missing=""
  for key in $(grep -oE '^[A-Z][A-Z0-9_]*=' "$example" 2> /dev/null | tr -d '=') \
    MMS_ENVIRONMENT MMS_REGISTRY MMS_TLS_DIR MMS_SECRETS_DIR; do
    case "$key" in MONGO_DEV_PORT | AUTH_SEED_PASSWORD | NODE_EXPORTER_ROOT_FLAGS) continue ;; esac
    haskey "$key" || missing="$missing $key"
  done
  if [ "$environment" = production ]; then
    check "every key of .env.example is in .env" "missing:$missing" test -z "$missing"
  elif [ -n "$missing" ]; then
    # Staging leaves out the overlays it does not run; Compose says below if one is needed
    info "keys of .env.example not set here:$missing"
  fi

  # A secret that still has the example's value was never regenerated
  copied=""
  while IFS='=' read -r key value; do
    case "$key" in *PASSWORD* | *SECRET* | *_KEY | KAFKA_CLUSTER_ID) ;; *) continue ;; esac
    [ -n "$value" ] && [ "$(envval "$key")" = "$value" ] && copied="$copied $key"
  done < <(grep -E '^[A-Z][A-Z0-9_]*=' "$example" 2> /dev/null)
  check "no secret has the example's value" "regenerate:$copied" test -z "$copied"

  check "the seed users' password is not set" "remove AUTH_SEED_PASSWORD" \
    test -z "$(envval AUTH_SEED_PASSWORD)"

  if [ "$environment" = production ]; then
    check "files are scanned (MEDIA_SCAN_MODE=clamd)" "it is '$(envval MEDIA_SCAN_MODE)'" \
      test "$(envval MEDIA_SCAN_MODE)" = clamd
    case ",$(envval COMPOSE_PROFILES)," in
      *,backup,*) pass "the backup profile is on" ;;
      *) fail "the backup profile is on" "COMPOSE_PROFILES needs backup" ;;
    esac
    case "$(envval BACKUP_AGE_RECIPIENT)" in
      age1*) pass "backups are encrypted to a public key" ;;
      *) fail "backups are encrypted to a public key" "BACKUP_AGE_RECIPIENT is not an age1 key" ;;
    esac
    check "alerts have a recipient" "MMS_ALERT_EMAILS is empty" test -n "$(envval MMS_ALERT_EMAILS)"
    # T3: the Gmail account is the interim sender for staff-only staging
    case "$(envval PLATFORM_SMTP_HOST)" in
      "" | smtp.gmail.com) fail "email goes through the organization's relay (T3)" "PLATFORM_SMTP_HOST is empty or Gmail" ;;
      *) pass "email goes through the organization's relay (T3)" ;;
    esac
  fi

  # mongod 8 refuses to start on Linux 6.19 to 7.0.13 (SERVER-121912); mongod 9 is not proven
  local kernel major minor patch
  kernel="${READINESS_KERNEL:-$(uname -r)}"
  IFS=.- read -r major minor patch _ <<< "$kernel"
  patch="${patch//[!0-9]/}"
  if { [ "$major" = 6 ] && [ "${minor:-0}" -ge 19 ]; } \
    || { [ "$major" = 7 ] && [ "${minor:-0}" = 0 ] && [ "${patch:-0}" -le 13 ]; }; then
    fail "the kernel is safe for mongod" "$kernel is in 6.19 to 7.0.13: set GLIBC_TUNABLES=glibc.pthread.rseq=1 for mongo"
  else
    pass "the kernel is safe for mongod"
  fi

  command -v docker > /dev/null || { fail "docker is installed"; finish; }
  local -a compose
  local files="${READINESS_COMPOSE_FILES:-}"
  if [ -z "$files" ]; then
    case "$environment" in
      production) files="compose.yml compose.prod.yml compose.production.yml compose.monitoring.yml compose.backup.yml" ;;
      *) files="compose.yml compose.prod.yml compose.staging.yml" ;;
    esac
  fi
  compose=(docker compose)
  for key in $files; do compose+=(-f "$key"); done

  # Compose refuses a missing required variable; -q prints nothing of what it rendered
  local words
  if words="$(MMS_TAG="${MMS_TAG:-check}" "${compose[@]}" config -q 2>&1)"; then
    pass "the stack's files accept this .env"
  else
    fail "the stack's files accept this .env" "$(echo "$words" | tail -n 1)"
  fi

  # Running and healthy, or a one-shot that ended well
  local rows bad
  rows="$("${compose[@]}" ps -a --format '{{.Service}} {{.State}} {{.Health}} {{.ExitCode}}' 2> /dev/null)"
  if [ -z "$rows" ]; then
    fail "every container is healthy" "nothing is running"
  else
    bad="$(echo "$rows" | awk '
      $2 == "running" && ($3 == "healthy" || NF == 3) { next }
      $2 == "exited" && $NF == "0" { next }
      { printf " %s", $1 }')"
    check "every container is healthy ($(echo "$rows" | wc -l | tr -d ' ') in all)" "look at:$bad" test -z "$bad"
  fi

  if [ -f "$dir/../.deployed-tag" ]; then
    info "release: $(cat "$dir/../.deployed-tag")"
  elif [ "$environment" = production ]; then
    fail "the release that runs is recorded" "no .deployed-tag beside the stack folder"
  fi

  if words="$("${compose[@]}" exec -T platform python -m app.cli verify-audit 2>&1)"; then
    pass "the audit chain verifies ($(echo "$words" | grep -oE '[0-9]+ records' | head -n 1))"
  else
    fail "the audit chain verifies" "$(echo "$words" | tail -n 1)"
  fi

  # The same readings the alerts use: BackupMissing fires at 26 hours, RestoreDrillOld at 8 days
  local now kind stamp age
  now="$(date +%s)"
  reading() {
    "${compose[@]}" exec -T backup cat "/textfile/mms_backup_$1.prom" 2> /dev/null \
      | grep -E "^$2\{" | awk '{ print int($NF) }' | tail -n 1
  }
  if echo "$rows" | grep -qE '^backup running'; then
    for kind in mongo config objects; do
      stamp="$(reading "$kind" backup_last_success_timestamp_seconds)"
      if [ -z "$stamp" ]; then
        fail "a $kind backup has been taken" "no reading yet"
        continue
      fi
      age=$(((now - stamp) / 3600))
      check "the last $kind backup is under 26 hours old" "$age hours" test "$age" -lt 26
    done
    stamp="$(reading drill restore_drill_last_success_timestamp_seconds)"
    if [ -z "$stamp" ]; then
      # restore.sh --drill writes it on the host it ran on: the drill into staging leaves none here
      info "no restore drill is recorded on this host"
    else
      age=$(((now - stamp) / 86400))
      check "the last restore drill is under 8 days old" "$age days" test "$age" -lt 8
    fi
  elif [ "$environment" = production ]; then
    fail "backups run" "the backup container is not running"
  else
    skip "backups" "the backup container is not running here"
  fi

  # Not a pass or a fail: a production backup restores only where this is the same or newer
  # shellcheck disable=SC2016
  words="$("${compose[@]}" exec -T mongo sh -c 'mongosh --quiet "mongodb://root:${MONGO_INITDB_ROOT_PASSWORD}@$(hostname):27017/admin?directConnection=true" --eval "db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion.version"' 2> /dev/null | tr -d '\r' | tail -n 1)"
  info "MongoDB feature compatibility version: ${words:-unknown}"

  local used
  used="$(df -P "$(docker info --format '{{.DockerRootDir}}' 2> /dev/null || echo "$dir")" 2> /dev/null | awk 'NR == 2 { print int($5) }')"
  if [ -n "$used" ]; then
    check "the disk is under 80% full" "$used% used" test "$used" -lt 80
  else
    skip "the disk is under 80% full" "could not read it"
  fi
  finish
}

# =============================================================================================
# From outside
# =============================================================================================

URL=""
FILES=""
VERSION=""
INSECURE=0
VIA=""

[ $# -gt 0 ] || usage
if [ "$1" = --on-host ]; then
  on_host "${2:-}"
fi
while [ $# -gt 0 ]; do
  case "$1" in
    --files) FILES="${2:?--files needs a host name}"; shift 2 ;;
    --expect-version) VERSION="${2:?--expect-version needs a version}"; shift 2 ;;
    --via) VIA="${2:?--via needs HOST:PORT}"; shift 2 ;;
    --insecure) INSECURE=1; shift ;;
    -h | --help) usage ;;
    -*) echo "unknown option $1" >&2; usage ;;
    *) URL="${1%/}"; shift ;;
  esac
done
[ -n "$URL" ] || usage

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
HDR="$TMP/headers"
BODY="$TMP/body"
CURL=(curl -sS --connect-timeout 10 --max-time 20)
[ "$INSECURE" = 1 ] && CURL+=(-k)
[ -n "$VIA" ] && CURL+=(--connect-to "::$VIA")

HOST="${URL#*://}"
HOST="${HOST%%/*}"
STATUS=000
# fetch URL: the status in STATUS, the headers and the body in files
fetch() {
  STATUS="$("${CURL[@]}" -o "$BODY" -D "$HDR" -w '%{http_code}' "$1" 2> /dev/null)" || STATUS=000
}
header() { tr -d '\r' < "$HDR" | grep -i "^$1:" | tail -n 1 | cut -d: -f2- | sed 's/^ *//'; }
# status_is PATH CODE NAME
status_is() {
  fetch "$URL$1"
  check "$3" "$1 answered $STATUS, expected $2" test "$STATUS" = "$2"
}

info "site: $URL"
check "the address is https" "a phone refuses a service worker without it" test "${URL%%://*}" = https

# --- The page and its headers ---------------------------------------------------------------

fetch "$URL/"
check "the app answers" "/ answered $STATUS" test "$STATUS" = 200
# Nothing there at all: thirty more lines saying so would hide the one that matters
[ "$STATUS" = 000 ] && finish
check "the page is the app" 'no <div id="app">' grep -q '<div id="app">' "$BODY"
cp "$BODY" "$TMP/index.html"
check "the page is never cached (index.html: no-cache)" "Cache-Control: $(header cache-control)" \
  test "$(header cache-control)" = no-cache

CSP="$(header content-security-policy)"
if [ -z "$FILES" ]; then
  FILES="$(echo "$CSP" | sed -n "s/.*img-src 'self' https:\/\/\([^ ;]*\).*/\1/p")"
fi
info "files host: ${FILES:-unknown}"
EXPECTED="default-src 'self'; img-src 'self' https://$FILES data: blob:; media-src 'self' https://$FILES blob:; connect-src 'self' https://$FILES wss://$HOST; script-src 'self'; worker-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
check "the content security policy is the TRD's (§15)" "it is: ${CSP:-missing}" test "$CSP" = "$EXPECTED"

# The same on a page and on an API error: Nginx adds them to every kind of response
security_headers() {
  local where="$1" missing=""
  [ "$(header x-content-type-options)" = nosniff ] || missing="$missing x-content-type-options"
  [ "$(header x-frame-options)" = DENY ] || missing="$missing x-frame-options"
  [ "$(header referrer-policy)" = strict-origin-when-cross-origin ] || missing="$missing referrer-policy"
  case "$(header strict-transport-security)" in max-age=31536000*) ;; *) missing="$missing strict-transport-security" ;; esac
  case "$(header permissions-policy)" in *"camera=(self)"*) ;; *) missing="$missing permissions-policy" ;; esac
  [ "$(header cross-origin-opener-policy)" = same-origin ] || missing="$missing cross-origin-opener-policy"
  [ "$(header cross-origin-resource-policy)" = same-origin ] || missing="$missing cross-origin-resource-policy"
  check "security headers on $where" "wrong or missing:$missing" test -z "$missing"
}
security_headers "the page"

# --- What the installed app needs (TRD §2.1, the pwa skill's contract 12) --------------------

for path in /sw.js /theme-init.js /manifest.webmanifest /index.html; do
  fetch "$URL$path"
  if [ "$STATUS" = 200 ] && [ "$(header cache-control)" = no-cache ]; then
    pass "$path is served and never cached"
  else
    fail "$path is served and never cached" "status $STATUS, Cache-Control: $(header cache-control)"
  fi
  if [ "$path" = /sw.js ]; then
    case "$(header content-type)" in
      *javascript*) pass "the service worker is JavaScript" ;;
      *) fail "the service worker is JavaScript" "Content-Type: $(header content-type)" ;;
    esac
  fi
  [ "$path" = /manifest.webmanifest ] && cp "$BODY" "$TMP/manifest"
done

if [ -s "$TMP/manifest" ]; then
  check "the manifest opens the app standalone" "no display: standalone" \
    grep -q '"display":"standalone"' <(tr -d ' \n\r' < "$TMP/manifest")
  broken=""
  count=0
  for src in $(tr -d ' \n\r' < "$TMP/manifest" | grep -oE '"src":"[^"]+"' | cut -d'"' -f4 | sort -u); do
    count=$((count + 1))
    fetch "$URL/${src#/}"
    [ "$STATUS" = 200 ] || broken="$broken $src"
  done
  check "the manifest's icons load ($count)" "missing:$broken" test "$count" -gt 0 -a -z "$broken"
else
  fail "the manifest opens the app standalone" "no manifest"
fi

ASSETS="$(grep -oE '/assets/[^"]+\.js' "$TMP/index.html" | sort -u)"
first="$(echo "$ASSETS" | head -n 1)"
if [ -n "$first" ]; then
  fetch "$URL$first"
  check "hashed files are kept for a year" "status $STATUS, Cache-Control: $(header cache-control)" \
    test "$STATUS" = 200 -a "$(header cache-control)" = "public, max-age=31536000, immutable"
else
  fail "hashed files are kept for a year" "the page names no /assets/ script"
fi

if [ -n "$VERSION" ]; then
  found=0
  for asset in $ASSETS; do
    fetch "$URL$asset"
    # The minifier picks the quote: "0.8.0", '0.8.0' or `0.8.0`
    grep -qF -e "\"$VERSION\"" -e "'$VERSION'" -e "\`$VERSION\`" "$BODY" && found=1 && break
  done
  check "the app is version $VERSION" "no script the page loads carries it" test "$found" = 1
else
  skip "the app's version" "no --expect-version"
fi

# --- Doors that stay shut --------------------------------------------------------------------

status_is /internal/users 404 "/internal/ is not routed"
status_is /metrics 404 "/metrics is not routed"
status_is /.well-known/x 404 "/.well-known/ is not routed"
status_is /.releases/x 404 "earlier releases' folder is not listed"
status_is /api/v1/integrations/x 501 "integrations answer 501"
fetch "$URL/api/v1/nope"
case "$STATUS $(header content-type)" in
  "404 application/problem+json"*) pass "an unknown API route is a 404 problem" ;;
  *) fail "an unknown API route is a 404 problem" "status $STATUS, $(header content-type)" ;;
esac
security_headers "an API error"

# --- Each service answers through the gateway (503 is Nginx saying it is down) ---------------

status_is /api/v1/auth/branding 200 "auth answers (public brand colours)"
status_is /api/v1/users 401 "auth asks for a session"
status_is /api/v1/stations 401 "operations answers"
status_is /api/v1/media/x 401 "media answers"
status_is /api/v1/dashboard 401 "report answers"
status_is /api/v1/notifications 401 "platform answers"

# --- Transport -------------------------------------------------------------------------------

if [ -n "$VIA" ] || [ "$HOST" != "${HOST%:*}" ]; then
  skip "http goes to https" "not through --via or a port"
else
  STATUS="$(curl -sS --max-time 20 -o /dev/null -D "$HDR" -w '%{http_code}' "http://$HOST/x" 2> /dev/null)" || STATUS=000
  check "http goes to https" "status $STATUS, Location: $(header location)" \
    test "$STATUS" = 301 -a "$(header location)" = "https://$HOST/x"
fi

# cert_ok NAME: fails when the certificate is invalid for the name or ends within 21 days
cert_ok() {
  local target="${VIA:-$1:443}"
  echo | openssl s_client -connect "$target" -servername "$1" -verify_return_error 2> /dev/null \
    | openssl x509 -noout -checkend $((21 * 86400)) > /dev/null 2>&1
}
if [ "$INSECURE" = 1 ]; then
  skip "certificates" "--insecure"
elif ! command -v openssl > /dev/null; then
  skip "certificates" "no openssl here"
else
  check "the app's certificate is trusted and lasts 21 days more" "check $HOST" cert_ok "$HOST"
  [ -n "$FILES" ] && check "the files host's certificate is trusted and lasts 21 days more" "check $FILES" cert_ok "$FILES"
fi

# --- The files host --------------------------------------------------------------------------

if [ -n "$FILES" ]; then
  fetch "https://$FILES/"
  check "the files host answers" "no answer from $FILES" test "$STATUS" != 000
  check "the files host lists nothing to a stranger" "/ answered 200" test "$STATUS" != 200
  missing=""
  [ "$(header x-content-type-options)" = nosniff ] || missing="$missing x-content-type-options"
  case "$(header strict-transport-security)" in max-age=31536000*) ;; *) missing="$missing strict-transport-security" ;; esac
  check "security headers on the files host" "wrong or missing:$missing" test -z "$missing"
else
  fail "the files host is known" "give --files HOST"
fi

finish
