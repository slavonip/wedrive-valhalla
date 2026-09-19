#!/usr/bin/env bash
# Решающий вопрос: Молдова ВНУТРИ монолита и Молдова, собранная отдельно, — один ли это граф?
#
# Расхождение на длинном маршруте началось на 33-м километре ВНУТРИ Молдовы, за 40 км до границы.
# Значит ни порталы, ни румынская часть ни при чём. Остаётся различие самих графов: Mjolnir
# строит иерархию и шорткаты по ВСЕМУ набору входных данных, поэтому Молдова, собранная вместе с
# Румынией, может отличаться от Молдовы, собранной одна.
#
# Если чистый MD-граф даёт тот же маршрут, что композит, а монолит — другой, то это не дефект
# рантайма, а цена независимой сборки.
set -u
one() { # cfg lat lon lat lon label
  local out
  out=$(docker exec vhdev valhalla_service "$1" route \
    "{\"locations\":[{\"lat\":$2,\"lon\":$3},{\"lat\":$4,\"lon\":$5}],\"costing\":\"auto\"}" 2>/dev/null)
  echo "$out" | python3 -c '
import sys, json
raw=sys.stdin.read(); i=raw.find("{")
if i<0: print("   нет ответа"); raise SystemExit
d=json.loads(raw[i:])
if "error" in d: print("   ОШИБКА:", d["error"]); raise SystemExit
t=d["trip"]; s=t["summary"]
names=[]
for m in t["legs"][0]["maneuvers"]:
    n=(m.get("street_names") or [""])[0]
    if n and n not in names: names.append(n)
print("   %8.3f км %9.1f с  манёвров %3d   %s" % (s["length"], s["time"],
      sum(len(l["maneuvers"]) for l in t["legs"]), " > ".join(names[:9])))
'
}

echo "=== Кишинёв -> Леушень (ЦЕЛИКОМ внутри Молдовы, через зону расхождения)"
printf '   %-12s' "монолит";   one /regions/mono.json           47.0105 28.8638 46.8233 28.1407
printf '   %-12s' "чистый MD"; one /regions/regress-valhalla.json 47.0105 28.8638 46.8233 28.1407
printf '   %-12s' "мультирег";  one /regions/mr.json             47.0105 28.8638 46.8233 28.1407

echo
echo "=== Кишинёв -> Кагул (тоже внутри Молдовы, длиннее)"
printf '   %-12s' "монолит";   one /regions/mono.json           47.0105 28.8638 45.9081 28.1944
printf '   %-12s' "чистый MD"; one /regions/regress-valhalla.json 47.0105 28.8638 45.9081 28.1944
printf '   %-12s' "мультирег";  one /regions/mr.json             47.0105 28.8638 45.9081 28.1944
