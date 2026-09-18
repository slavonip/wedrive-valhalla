#!/usr/bin/env bash
# A development container: the stock build kept alive so a patch recompiles only what changed.
#
# Rebuilding the image after every edit costs 17 minutes, because `COPY . .` invalidates the layer
# and everything compiles again. Keeping one container with the build tree intact turns that into
# an incremental `make` of a handful of objects.
set -u

pkill -f "docker build" 2>/dev/null || true
docker rm -f vhdev >/dev/null 2>&1 || true

docker run -d --name vhdev \
  -v "$HOME/exp7":/regions \
  wedrive-valhalla:stock sleep infinity >/dev/null

echo "container: $(docker ps --filter name=vhdev --format '{{.Status}}')"
docker exec vhdev bash -c 'ls /src/valhalla | head -6; echo "---"; ls /src/valhalla/build/CMakeCache.txt'
echo
echo "the two regions, as the container sees them:"
docker exec vhdev bash -c 'for d in moldova romania; do
  printf "  %-9s %5s tiles\n" "$d" "$(find /regions/$d/tiles -name "*.gph" | wc -l)"; done'
