#!/usr/bin/env bash
# Цепочка forward-лейблов от точки встречи назад: где теряется накопленная стоимость.
set -u
REQ='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'
out=~/chain.txt
docker exec -e WEDRIVE_DEBUG_BIDIR=1 vhdev valhalla_service /regions/mr.json route "$REQ" > "$out" 2>&1
grep -E 'WEDRIVE (CHAIN|РАЗЛОЖЕНИЕ|RECOST|CUM итог)' "$out" | sed 's/^/    /'
