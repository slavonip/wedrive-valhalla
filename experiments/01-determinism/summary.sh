#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/det"

echo "input url:    https://download.geofabrik.de/europe/moldova-latest.osm.pbf"
echo "input bytes:  $(stat -c%s src/moldova.osm.pbf)"
echo "input sha256: $(sha256sum src/moldova.osm.pbf | cut -d' ' -f1)"
echo

# One digest over the WHOLE tile set, computed from paths relative to each build root so the
# build's own name cannot leak into the hash.
for L in A B C D E; do
  d=$(cd "$L/tiles" && find . -name '*.gph' | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)
  n=$(find "$L/tiles" -name '*.gph' | wc -l)
  c=$(grep -oE 'Building [0-9]+ tiles with [0-9]+ threads' "$L/tiles.log" | grep -oE '[0-9]+ threads')
  printf '%s  %3d tiles  %-12s  %s\n' "$L" "$n" "$c" "$d"
done
