#!/usr/bin/env bash
# Сколько раз сервис запросил тайл по id без региона. Ноль — обязательное условие.
set -u
check() {
  local n
  n=$(docker exec vhdev valhalla_service /regions/mr.json route \
        "{\"locations\":[{\"lat\":$1,\"lon\":$2},{\"lat\":$3,\"lon\":$4}],\"costing\":\"auto\"}" 2>&1 \
      | grep -c 'REGION LOST' || true)
  printf '   %-34s потерь %s\n' "$5" "$n"
}
check 47.0105 28.8638 47.2075 27.8000 "внутри MD"
check 47.1585 27.6014 44.4268 26.1025 "внутри RO"
check 47.0105 28.8638 47.1585 27.6014 "MD -> RO"
check 47.1585 27.6014 47.0105 28.8638 "RO -> MD"
check 47.0105 28.8638 44.4268 26.1025 "Кишинёв -> Бухарест"
check 46.8233 28.1407 47.0105 28.8638 "из перекрытия"
