#!/usr/bin/env bash
# Build M3 and M4, then index every OSM way to its edge GraphIds in all three builds.
#
# `valhalla_ways_to_edges` is the instrument that matters here: it is Valhalla's own reader
# answering "which GraphIds does this OSM way own", so ID churn can be measured per OSM OBJECT
# instead of inferred from byte offsets.
set -euo pipefail

IMAGE="ghcr.io/valhalla/valhalla@sha256:2b19ea46551a9687b245022551183829d817fdee9b58c5e7b2adb6e422749c43"
ROOT="$HOME/det"

build() {
  local label="$1" pbf="$2"
  local out="$ROOT/$label"
  rm -rf "$out"; mkdir -p "$out/tiles"
  docker run --rm --user root -v "$ROOT":/data -e label="$label" -e pbf="$pbf" "$IMAGE" bash -c '
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
      valhalla_ways_to_edges -c $out/valhalla.json > $out/w2e.log 2>&1
    ' >/dev/null 2>&1
  echo "    $label: $(find "$out/tiles" -name '*.gph' | wc -l) tiles, "\
"$(wc -l < "$out/tiles/way_edges.txt") ways indexed"
}

echo "==> M3: new living_street attached deep inside the tile, local classes only"
build M3 moldova-m3.osm.pbf
echo "==> M4: the same, on the tile boundary — the new way crosses into the next L2"
build M4 moldova-m4.osm.pbf

# A already has tiles; make sure it has the way index too.
if [ ! -f "$ROOT/A/tiles/way_edges.txt" ]; then
  docker run --rm --user root -v "$ROOT":/data "$IMAGE" \
    valhalla_ways_to_edges -c /data/A/valhalla.json >/dev/null 2>&1
fi
echo "    A:  $(wc -l < "$ROOT/A/tiles/way_edges.txt") ways indexed"
