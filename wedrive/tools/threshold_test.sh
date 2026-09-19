#!/usr/bin/env bash
# Останавливается ли двунаправленный поиск слишком рано?
#
# Диагностика показала: композит завершает поиск с порогом 18336 против 18918 у монолита и с
# меньшими деревьями. Если увеличить threshold_delta, поиск продолжится дольше — и если при этом
# найдётся 456 км, гипотеза «остановился рано» подтверждается прямо.
set -u
REQ='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'

try() { # delta
  local cfg=/tmp/thr_$1.json
  docker exec vhdev python3 -c "
import json
c=json.load(open('/regions/mr.json'))
c.setdefault('thor',{}).setdefault('bidirectional_astar',{})['threshold_delta']=$1
json.dump(c, open('$cfg','w'))
"
  printf '   threshold_delta=%-8s' "$1"
  docker exec vhdev valhalla_service "$cfg" route "$REQ" 2>/dev/null | python3 -c '
import sys, json
raw=sys.stdin.read(); i=raw.find("{")
if i<0: print("нет ответа"); raise SystemExit
d=json.loads(raw[i:])
if "error" in d: print("ОШИБКА:", d["error"][:50]); raise SystemExit
s=d["trip"]["summary"]
print("%8.3f км %9.1f с" % (s["length"], s["time"]))
'
  docker exec vhdev rm -f "$cfg"
}

echo "=== эталон"
printf '   %-24s%8.3f км  %9.1f с\n' "монолит" 456.458 19396.8
printf '   %-24s%8.3f км  %9.1f с\n' "однонаправленный композит" 456.458 19396.5
echo
echo "=== двунаправленный композит при разных порогах"
try 50
try 500
try 5000
try 50000
