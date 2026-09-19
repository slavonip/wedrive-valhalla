#!/usr/bin/env bash
# Разложение стоимости соединения и сравнение с recost того же набора рёбер.
#
# Отвечает на вопрос: connection_cost = F + R + correction, а recost(те же рёбра) = X.
# Разность X - connection_cost и есть искомая потеря, измеренная напрямую, а не через пропорции.
set -u
REQ='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'

show() { # cfg label
  echo "=== $2"
  docker exec -e WEDRIVE_DEBUG_BIDIR=1 vhdev valhalla_service "$1" route "$REQ" 2>&1 \
    | grep 'WEDRIVE' | grep -vE 'REGION LOST' | head -40
}

show /regions/mono.json "МОНОЛИТ"
echo
show /regions/mr.json "КОМПОЗИТ"
