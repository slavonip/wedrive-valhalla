#!/usr/bin/env bash
# EXPERIMENT 2: the radius of one change.
#
# Build the two mutated PBFs with the same stock 3.6.3 and the same settings as build A, then map
# every .gph that moved. The question is not "did it change" but HOW FAR the change reached.
set -euo pipefail

IMAGE="ghcr.io/valhalla/valhalla@sha256:2b19ea46551a9687b245022551183829d817fdee9b58c5e7b2adb6e422749c43"
ROOT="$HOME/det"

build() {
  local label="$1" pbf="$2"
  local out="$ROOT/$label"
  rm -rf "$out"; mkdir -p "$out/tiles"
  docker run --rm --user root -v "$ROOT":/data \
    -e label="$label" -e pbf="$pbf" "$IMAGE" bash -c '
      set -e
      out=/data/$label
      valhalla_build_config --mjolnir-tile-dir $out/tiles \
        --mjolnir-admin $out/admins.sqlite --mjolnir-concurrency 22 > $out/valhalla.json
      python3 - "$out/valhalla.json" <<PY
import json, sys
c = json.load(open(sys.argv[1]))
c["mjolnir"].pop("tile_extract", None)
c["mjolnir"].pop("timezone", None)
json.dump(c, open(sys.argv[1], "w"), indent=2)
PY
      valhalla_build_admins -c $out/valhalla.json /data/src/$pbf > $out/admins.log 2>&1
      valhalla_build_tiles  -c $out/valhalla.json /data/src/$pbf > $out/tiles.log 2>&1
    ' >/dev/null 2>&1
  echo "    $label from $pbf: $(find "$out/tiles" -name '*.gph' | wc -l) tiles"
}

echo "==> M1: one tag changed on one primary way"
build M1 moldova-m1.osm.pbf
echo "==> M2: one new residential way plus two new nodes"
build M2 moldova-m2.osm.pbf
echo

python3 "$ROOT/closure_report.py"
