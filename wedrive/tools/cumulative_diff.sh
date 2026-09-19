#!/usr/bin/env bash
# Где вдоль пути накапливается недосчёт: сумма EdgeCost + transition против recost, ребро за ребром.
set -u
REQ='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'
out=~/cum.txt
docker exec -e WEDRIVE_DEBUG_BIDIR=1 vhdev valhalla_service /regions/mr.json route "$REQ" > "$out" 2>&1

echo "=== скачки расхождения и швы"
grep 'WEDRIVE CUM поз' "$out" | head -24 | sed 's/^/    /'
echo
echo "=== итог по пути"
grep 'WEDRIVE CUM итог' "$out" | sed 's/^/    /'
grep -E 'WEDRIVE (SEAM|RECOST)' "$out" | sed 's/^/    /'
