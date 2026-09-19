#!/usr/bin/env bash
# Если отключить иерархические ограничения, найдёт ли двунаправленный поиск оптимум?
#
# Отсечение идёт по hierarchy_limits и расстоянию до цели. Reverse-дерево композита не проходит
# портал, поэтому встреча смещается вглубь Румынии, и forward-дереву приходится идти через всю
# Молдову вдали от обоих концов — там, где на нижние уровни оно уже не спускается.
set -u
run() { # cfg json label
  printf '   %-34s' "$3"
  docker exec vhdev valhalla_service "$1" route "$2" 2>/dev/null | python3 -c '
import sys, json
raw=sys.stdin.read(); i=raw.find("{")
if i<0: print("нет ответа"); raise SystemExit
d=json.loads(raw[i:])
if "error" in d: print("ОШИБКА:", d["error"][:44]); raise SystemExit
s=d["trip"]["summary"]
print("%8.3f км %9.1f с" % (s["length"], s["time"]))
'
}

PLAIN='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'
NOHIER='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto","costing_options":{"auto":{"hierarchy_limits":{"1":{"max_up_transitions":0},"2":{"max_up_transitions":0}}}}}'

echo "=== обычный двунаправленный"
run /regions/mono.json "$PLAIN" "монолит"
run /regions/mr.json   "$PLAIN" "композит"
echo
echo "=== с ослабленными hierarchy_limits"
run /regions/mono.json "$NOHIER" "монолит"
run /regions/mr.json   "$NOHIER" "композит"
