#!/bin/bash
# Is it safe to deploy TARGET over what runs now (DEPLOYED)? (W20-12; TRD §18)
#
#   infra/scripts/rollback-guard.sh TARGET DEPLOYED [--allow-older-schema]
#
# A new release (TARGET descends from DEPLOYED) is always allowed. Going back (TARGET is an ancestor
# of DEPLOYED) is allowed only when the releases in between changed neither
# - a database migration: migrations run forward only, so the older code would run on a database
#   the newer code changed, or
# - an event schema: a consumer must never run an older image than the events it reads, or the
#   events land in the dead-letter topics (found on the first run of the monitoring stack, W20-2).
# Anything else (a different history, a commit that is not an ancestor either way) is refused.
# --allow-older-schema is for the day the operator has checked the changes by hand.
#
# Exit 0 = go ahead (it prints what it found), 1 = refused, 2 = bad arguments.
set -euo pipefail

target="${1:?usage: rollback-guard.sh TARGET DEPLOYED [--allow-older-schema]}"
deployed="${2:?usage: rollback-guard.sh TARGET DEPLOYED [--allow-older-schema]}"
allow=0
[ "${3:-}" = "--allow-older-schema" ] && allow=1

git cat-file -e "$target^{commit}" 2> /dev/null || { echo "unknown commit $target" >&2; exit 2; }
git cat-file -e "$deployed^{commit}" 2> /dev/null || { echo "unknown commit $deployed" >&2; exit 2; }
target="$(git rev-parse "$target^{commit}")"
deployed="$(git rev-parse "$deployed^{commit}")"

if [ "$target" = "$deployed" ]; then
  echo "same release ($target): nothing to guard"
  exit 0
fi
if git merge-base --is-ancestor "$deployed" "$target"; then
  echo "a newer release: $deployed -> $target"
  exit 0
fi
if ! git merge-base --is-ancestor "$target" "$deployed"; then
  echo "refused: $target and $deployed are on different lines of history" >&2
  exit 1
fi

echo "a rollback: $deployed -> $target"
changed="$(git diff --name-only "$target" "$deployed" -- \
  ':(glob)services/*/app/migrations/**' ':(glob)libs/mms_common/mms_common/events/**' || true)"
if [ -z "$changed" ]; then
  echo "no migration or event schema changed in between: safe to go back"
  exit 0
fi
echo "these changed between the two releases:" >&2
echo "$changed" | sed 's/^/  /' >&2
if [ "$allow" = 1 ]; then
  echo "going back anyway (--allow-older-schema)"
  exit 0
fi
echo "refused: going back over a migration or event change needs --allow-older-schema (see the runbook)" >&2
exit 1
