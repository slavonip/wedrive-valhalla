#!/usr/bin/env bash
# Путь через R3.1 композиту НЕДОСТУПЕН или он его НЕ НАХОДИТ?
#
# Если с промежуточной точкой на R3.1 композит выдаёт примерно монолитные 456 км, значит граф
# позволяет, а поиск не нашёл — это вопрос эвристики/иерархии. Если не выдаёт, значит участок
# действительно недостижим, и надо смотреть связность.
set -u
ask() { # cfg json label
  printf '   %-26s' "$2"
  docker exec vhdev valhalla_service "$1" route "$3" 2>/dev/null | python3 -c '
import sys, json
raw=sys.stdin.read(); i=raw.find("{")
if i<0: print("нет ответа"); raise SystemExit
d=json.loads(raw[i:])
if "error" in d: print("ОШИБКА:", d["error"][:60]); raise SystemExit
s=d["trip"]["summary"]
print("%8.3f км %9.1f с" % (s["length"], s["time"]))
'
}

DIRECT='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'
# 46.841253, 28.614655 — точка, где монолит уходит на R3.1, а композит идёт прямо.
VIA='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":46.841253,"lon":28.614655},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'

echo "=== прямой запрос"
ask /regions/mono.json "монолит" "$DIRECT"
ask /regions/mr.json   "мультирегион" "$DIRECT"
echo
echo "=== через точку на R3.1 (46.841253, 28.614655)"
ask /regions/mono.json "монолит" "$VIA"
ask /regions/mr.json   "мультирегион" "$VIA"
