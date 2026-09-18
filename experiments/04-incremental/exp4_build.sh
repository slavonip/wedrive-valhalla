#!/usr/bin/env bash
# Experiment 4, part 1: two masters differing in exactly one country's data.
#
#   T0    RO,HU,RS,BG,MD,UA  all at 2026-09-01
#   REF   HU,RS,BG,MD,UA at 2026-09-01  +  RO at 2026-09-14
#
# One variable. Anything that differs between them traces to Romania's fortnight, because
# experiment 1 established the builder is deterministic for identical input.
set -euo pipefail

IMAGE="ghcr.io/valhalla/valhalla@sha256:2b19ea46551a9687b245022551183829d817fdee9b58c5e7b2adb6e422749c43"
ROOT="$HOME/exp4"
SRC="$ROOT/src"

merge_one() {
  local label="$1" ro_date="$2"
  local master="$SRC/master-$label.osm.pbf"
  [ -f "$master" ] && { echo "    $label master present: $(du -h "$master" | cut -f1)"; return; }
  echo "    merging $label (romania @ $ro_date, everything else @ 260901)"
  osmium merge \
    "$SRC/romania-$ro_date.osm.pbf" \
    "$SRC/hungary-260901.osm.pbf" \
    "$SRC/serbia-260901.osm.pbf" \
    "$SRC/bulgaria-260901.osm.pbf" \
    "$SRC/moldova-260901.osm.pbf" \
    "$SRC/ukraine-260901.osm.pbf" \
    -o "$master" --overwrite
  echo "    $label master: $(du -h "$master" | cut -f1)"
}

build_one() {
  local label="$1"
  local out="$ROOT/$label"
  [ -d "$out/tiles" ] && [ "$(find "$out/tiles" -name '*.gph' | wc -l)" -gt 0 ] && {
    echo "    $label already built: $(find "$out/tiles" -name '*.gph' | wc -l) tiles"; return; }
  rm -rf "$out"; mkdir -p "$out/tiles"
  docker run --rm --user root -v "$ROOT":/data -e label="$label" "$IMAGE" bash -c '
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
      valhalla_build_admins -c $out/valhalla.json /data/src/master-$label.osm.pbf \
        > $out/admins.log 2>&1
      valhalla_build_tiles  -c $out/valhalla.json /data/src/master-$label.osm.pbf \
        > $out/tiles.log 2>&1
    ' >/dev/null 2>&1
  echo "    $label: $(find "$out/tiles" -name '*.gph' | wc -l) tiles, $(du -sh "$out/tiles" | cut -f1)"
}

cut_one() {
  local label="$1"
  local out="$ROOT/$label"
  [ -d "$out/cuts" ] && { echo "    $label already cut"; return; }
  docker run --rm --user root -v "$ROOT":/data -e label="$label" "$IMAGE" \
    python3 /data/cut-by-country.py "/data/$label/tiles" "/data/$label/cuts" \
      "RO:/data/src/romania.poly" "HU:/data/src/hungary.poly" "RS:/data/src/serbia.poly" \
      "BG:/data/src/bulgaria.poly" "MD:/data/src/moldova.poly" "UA:/data/src/ukraine.poly" \
    2>&1 | tail -3
}

echo "=== merge ==="
merge_one T0  260901
merge_one REF 260914

echo "=== build ==="
time build_one T0
time build_one REF

echo "=== cut ==="
cut_one T0
cut_one REF

echo "=== sizes ==="
for l in T0 REF; do
  echo "  $l  master tiles $(du -sh "$ROOT/$l/tiles" | cut -f1)   cuts $(du -sh "$ROOT/$l/cuts" | cut -f1)"
  for c in RO HU RS BG MD UA; do
    d="$ROOT/$l/cuts/$c"
    [ -d "$d" ] && printf '     %s %8s  %5d tiles\n' "$c" "$(du -sh "$d" | cut -f1)" \
      "$(find "$d" -name '*.gph' | wc -l)"
  done
done
