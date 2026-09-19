#!/usr/bin/env bash
# Одинаково ли выглядит Молдова в монолите и в отдельной сборке — именно в зоне расхождения?
#
# Отсечение в bidirectional идёт по hierarchy_limits и расстоянию до цели: вдали от цели поиск
# не спускается на нижние уровни. Если R3.1 в монолите лежит на более высоком уровне, чем в
# отдельной сборке MD, то монолит её увидит, а композит нет — и это будет разница СБОРКИ, а не
# рантайма.
set -u
ask() { # cfg lat lon lat lon
  docker exec vhdev valhalla_service "$1" route \
    "{\"locations\":[{\"lat\":$2,\"lon\":$3},{\"lat\":$4,\"lon\":$5}],\"costing\":\"auto\"}" 2>/dev/null \
  | python3 -c '
import sys, json
raw=sys.stdin.read(); i=raw.find("{")
if i<0: print("нет ответа"); raise SystemExit
d=json.loads(raw[i:])
if "error" in d: print("ОШИБКА:", d["error"][:44]); raise SystemExit
t=d["trip"]; s=t["summary"]
names=[]
for m in t["legs"][0]["maneuvers"]:
    n=(m.get("street_names") or [""])[0]
    if n and n not in names: names.append(n)
print("%8.3f км %8.1f с  %s" % (s["length"], s["time"], " > ".join(names[-5:])))
'
}

# Точка, где монолит уходит на R3.1, а композит идёт прямо.
X=46.841253; Y=28.614655

echo "=== Кишинёв -> точка расхождения (ЦЕЛИКОМ внутри Молдовы)"
printf '   %-12s' "монолит";   ask /regions/mono.json 47.0105 28.8638 $X $Y
printf '   %-12s' "чистый MD"; ask /regions/regress-valhalla.json 47.0105 28.8638 $X $Y
printf '   %-12s' "мультирег";  ask /regions/mr.json 47.0105 28.8638 $X $Y

echo
echo "=== Кишинёв -> Джурджулешть (юг MD, длинный, внутри страны)"
printf '   %-12s' "монолит";   ask /regions/mono.json 47.0105 28.8638 45.4709 28.1968
printf '   %-12s' "чистый MD"; ask /regions/regress-valhalla.json 47.0105 28.8638 45.4709 28.1968
printf '   %-12s' "мультирег";  ask /regions/mr.json 47.0105 28.8638 45.4709 28.1968

echo
echo "=== на каком уровне иерархии лежит R3.1 в каждом графе"
docker exec vhdev bash -c '
for d in /regions/moldova/tiles /regions/mono/tiles; do
  echo "--- $d"
  /tmp/portal_probe "$d" "$d" 46.841253 28.614655 2>/dev/null | head -4
done'
