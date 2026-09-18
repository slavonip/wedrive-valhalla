#!/usr/bin/env bash
# Experiment 4: fetch two dated generations of Romania and every country it borders.
#
# Romania borders Hungary, Serbia, Bulgaria, Moldova and Ukraine. All five are included so that
# Romania's cut has no artificial frontier -- a missing neighbour would make the measurement of
# what must travel with a Romanian update wrong in the one direction that matters.
set -euo pipefail
BASE=https://download.geofabrik.de/europe
ROOT="$HOME/exp4"
mkdir -p "$ROOT/src"

for d in 260901 260914; do
  for c in romania hungary serbia bulgaria moldova ukraine; do
    f="$ROOT/src/$c-$d.osm.pbf"
    if [ ! -f "$f" ]; then
      curl -fSL --retry 3 --retry-delay 5 -o "$f.part" "$BASE/$c-$d.osm.pbf"
      mv "$f.part" "$f"
    fi
    printf '%-26s %10s  %s\n' "$(basename "$f")" \
      "$(du -h "$f" | cut -f1)" "$(sha256sum "$f" | cut -c1-16)"
  done
done

for d in 260901 260914; do
  for c in romania hungary serbia bulgaria moldova ukraine; do
    p="$ROOT/src/$c.poly"
    [ -f "$p" ] || curl -fsSL -o "$p" "$BASE/$c.poly"
  done
done
echo
echo "polys: $(ls "$ROOT/src"/*.poly | wc -l)"
echo "total: $(du -sh "$ROOT/src" | cut -f1)"
