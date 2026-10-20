#!/usr/bin/env bash
# Cuts the basemap the map page draws (decision W7-9, finding F1) out of the Protomaps daily build:
# one PMTiles file for the Caribbean, from zoom 0 to 14. Only the part we need is downloaded.
#
#   infra/scripts/extract-tiles.sh [BUILD_DATE] [OUTPUT_DIR]
#   infra/scripts/extract-tiles.sh 20261019 infra/tiles          # the defaults
#
# Needs the pmtiles CLI (https://github.com/protomaps/go-pmtiles/releases) on PATH. Takes about
# a minute and downloads about 600 MB. Then:
#   1. check the file opens:  pmtiles show infra/tiles/caribbean-<date>-z14.pmtiles
#   2. put the date in `TILES_URL` (frontend/src/features/map/tiles.ts) and release the app
#   3. copy the file to the host's tiles folder (staging: /opt/mms/tiles, owned by `mms`), and keep
#      the previous file there until phones have moved to the new release.
# Never overwrite a published file: its name is part of the browser's cache keys.
#
# The area is the UN geoscheme's Caribbean subregion plus its surrounding sea. Mainland members of
# CARICOM (Belize, Guyana, Suriname) are outside it: add a second --bbox run and merge, or widen
# BBOX, when stations are there. Data © OpenStreetMap contributors (ODbL); the style is Protomaps'.
set -euo pipefail

BUILD_DATE="${1:-20261019}"
OUT_DIR="${2:-infra/tiles}"
MAX_ZOOM=14
BBOX="-86,9.5,-58,28" # west,south,east,north
OUT="${OUT_DIR}/caribbean-${BUILD_DATE}-z${MAX_ZOOM}.pmtiles"

if [ -e "$OUT" ]; then
  echo "$OUT exists; names are never reused. Pick another build date." >&2
  exit 1
fi
mkdir -p "$OUT_DIR"
pmtiles extract "https://build.protomaps.com/${BUILD_DATE}.pmtiles" "$OUT" --bbox="$BBOX" --maxzoom="$MAX_ZOOM"
pmtiles show "$OUT"
ls -l "$OUT"
