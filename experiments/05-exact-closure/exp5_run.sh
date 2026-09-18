#!/usr/bin/env bash
set -euo pipefail
IMAGE="ghcr.io/valhalla/valhalla@sha256:2b19ea46551a9687b245022551183829d817fdee9b58c5e7b2adb6e422749c43"
ROOT="$HOME/exp4"

docker run --rm --user root -v "$ROOT":/data "$IMAGE" bash -c '
  set -e
  python3 /data/exp5_assemble.py
  echo
  for l in EXACT_MIXED MINUS_0 MINUS_1 MINUS_2 MINUS_3 MINUS_4 MINUS_5; do
    [ -d /data/$l/tiles ] || continue
    valhalla_build_config --mjolnir-tile-dir /data/$l/tiles > /data/$l/valhalla.json
    python3 - "/data/$l/valhalla.json" <<PY
import json, sys
c = json.load(open(sys.argv[1]))
c["mjolnir"].pop("tile_extract", None); c["mjolnir"].pop("timezone", None)
json.dump(c, open(sys.argv[1], "w"), indent=2)
PY
  done
  echo "=== SUFFICIENCY: does the computed closure reproduce the reference? ==="
  python3 /data/exp4_routes.py REF EXACT_MIXED BROKEN_MIXED
  echo
  echo "=== MINIMALITY: remove one closure tile at a time ==="
  python3 /data/exp4_routes.py REF EXACT_MIXED MINUS_0 MINUS_1 MINUS_2
  echo
  python3 /data/exp4_routes.py REF MINUS_3 MINUS_4 MINUS_5
' 2>&1 | grep -v WARN
