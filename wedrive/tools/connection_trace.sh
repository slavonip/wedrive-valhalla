#!/usr/bin/env bash
# Где именно встречаются деревья в монолите и в композите.
#
# Оптимальная ветка существует — timedep_forward на тех же графах и той же таблице порталов даёт
# монолитные 456.458 км. Значит вопрос в том, почему она не побеждает в двунаправленном поиске.
# Первое, что нужно увидеть: совпадают ли ТОЧКИ ВСТРЕЧИ.
set -u
REQ='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'

# Узел, на котором монолит уходит на R3.1, а композит идёт прямо (46.841253, 28.614655).
# В графе Молдовы это tile 788514 id 3878 на level 2; с регионом 1 значение ниже.
WATCH=${WATCH:-70498874573074}

echo "=== МОНОЛИТ"
docker exec -e WEDRIVE_DEBUG_BIDIR=1 vhdev valhalla_service /regions/mono.json route "$REQ" 2>&1 \
  | grep -E 'WEDRIVE (CONN|BIDIR|WATCH)' | head -16

echo
echo "=== КОМПОЗИТ"
docker exec -e WEDRIVE_DEBUG_BIDIR=1 -e WEDRIVE_WATCH_NODE="$WATCH" vhdev \
  valhalla_service /regions/mr.json route "$REQ" 2>&1 \
  | grep -E 'WEDRIVE (CONN|BIDIR|WATCH)' | head -16
