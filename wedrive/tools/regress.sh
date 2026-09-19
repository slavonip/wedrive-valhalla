#!/usr/bin/env bash
# The gate nobody had run: does the multi-region patch change ORDINARY, single-region routing?
#
# Answered by diffing our patched build against stock upstream 3.6.3 on the same tiles, with the
# same requests. Anything other than an identical answer is a regression, and "it still routes"
# is not the same claim as "it routes the same".
set -u

SRC=$(docker inspect vhdev --format '{{range .Mounts}}{{if eq .Destination "/regions"}}{{.Source}}{{end}}{{end}}')
echo "=== /regions comes from: $SRC"
[ -n "$SRC" ] || { echo "!! cannot find the mount; aborting rather than guessing"; exit 1; }

CFG=/regions/regress-valhalla.json
docker exec vhdev bash -c "valhalla_build_config --mjolnir-tile-dir /regions/moldova/tiles \
  --mjolnir-tile-extract '' --mjolnir-timezone '' --mjolnir-admin '' > $CFG 2>/dev/null; \
  python3 -c \"import json;d=json.load(open('$CFG'));print('tile_dir',d['mjolnir']['tile_dir'])\""

run() { # container-or-image, label
  local how="$1" label="$2"
  echo "--- $label"
  for req in \
    '{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":47.2075,"lon":27.8000}],"costing":"auto"}' \
    '{"locations":[{"lat":47.0269,"lon":28.8416},{"lat":47.0105,"lon":28.8638}],"costing":"auto"}' \
    '{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":47.0269,"lon":28.8416}],"costing":"auto"}'
  do
    $how valhalla_service "$CFG" route "$req" 2>/dev/null \
      | python3 -c 'import sys,json
try:
    t=json.load(sys.stdin)["trip"]
    s=t["summary"]
    print("   %10.3f km  %8.1f s  %3d legs  %3d maneuvers" % (
        s["length"], s["time"], len(t["legs"]),
        sum(len(l["maneuvers"]) for l in t["legs"])))
except Exception as e:
    print("   FAILED:", e)'
  done
}

echo
echo "=== patched build (our multi-region runtime)"
run "docker exec vhdev" "patched"

echo
echo "=== stock upstream 3.6.3, same tiles, same requests"
run "docker run --rm -v $SRC:/regions ghcr.io/valhalla/valhalla:3.6.3" "stock"
