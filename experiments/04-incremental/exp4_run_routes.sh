#!/usr/bin/env bash
set -euo pipefail
IMAGE="ghcr.io/valhalla/valhalla@sha256:2b19ea46551a9687b245022551183829d817fdee9b58c5e7b2adb6e422749c43"
ROOT="$HOME/exp4"

docker run --rm --user root -v "$ROOT":/data "$IMAGE" bash -c '
  set -e
  for l in REF MIXED MINIMAL_MIXED BROKEN_MIXED; do
    valhalla_build_config --mjolnir-tile-dir /data/$l/tiles > /data/$l/valhalla.json
    python3 - "/data/$l/valhalla.json" <<PY
import json, sys
c = json.load(open(sys.argv[1]))
c["mjolnir"].pop("tile_extract", None)
c["mjolnir"].pop("timezone", None)
json.dump(c, open(sys.argv[1], "w"), indent=2)
PY
  done
  python3 /data/exp4_routes.py REF MIXED MINIMAL_MIXED BROKEN_MIXED
' 2>&1 | grep -v WARN
