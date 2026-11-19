#!/usr/bin/env bash
# The pilot triage labels (W23-6). Safe to run again: --force updates a label that exists.
# Usage: bash infra/scripts/pilot-labels.sh [owner/repo]
set -euo pipefail
repo="${1:-tajay59/MARS-MMS}"

label() { gh label create "$1" --repo "$repo" --color "$2" --description "$3" --force; }

label pilot             0A6780 "Found during the pilot (W24, W25) or hypercare"
label triage            D4C5F9 "New: not triaged yet"
label severity:critical B60205 "Work lost or sent twice, another organization's data seen, nobody can sign in, or the site is down"
label severity:high     D93F0B "A journey is blocked for someone and there is no other way to finish it"
label severity:medium   FBCA04 "Wrong, but there is another way to finish the job"
label severity:low      C2E0C6 "Looks wrong, reads badly, or a small inconvenience"
