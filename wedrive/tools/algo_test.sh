#!/usr/bin/env bash
# Двунаправленный A* против однонаправленного на длинном трансграничном маршруте.
#
# Путь доказанно ДОСТУПЕН: через промежуточную точку композит даёт 456.453 км против 456.458 у
# монолита. Значит вопрос в поиске. date_time форсирует timedep_forward, то есть ОДНОнаправленный
# алгоритм: если он находит 456 км, дело в двунаправленном поиске и его критерии встречи/останова,
# а не в графе и не в порталах.
set -u
ask() { # cfg json label
  printf '   %-30s' "$3"
  docker exec vhdev valhalla_service "$1" route "$2" 2>/dev/null | python3 -c '
import sys, json
raw=sys.stdin.read(); i=raw.find("{")
if i<0: print("нет ответа"); raise SystemExit
d=json.loads(raw[i:])
if "error" in d: print("ОШИБКА:", d["error"][:60]); raise SystemExit
s=d["trip"]["summary"]
print("%8.3f км %9.1f с" % (s["length"], s["time"]))
'
}

BI='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'
UNI='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto","date_time":{"type":1,"value":"2026-09-19T08:00"}}'

echo "=== двунаправленный (по умолчанию)"
ask /regions/mono.json "$BI" "монолит"
ask /regions/mr.json   "$BI" "мультирегион"
echo
echo "=== однонаправленный (date_time forward)"
ask /regions/mono.json "$UNI" "монолит"
ask /regions/mr.json   "$UNI" "мультирегион"
