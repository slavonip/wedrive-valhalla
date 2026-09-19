#!/usr/bin/env bash
# Где расходятся монолит и композит на длинном маршруте.
#
# Итоговые 456 против 469 км ничего не локализуют: разница может родиться на первом километре
# или на последнем. Нужна ПЕРВАЯ точка расхождения.
set -u
O=${1:-47.0105}; OL=${2:-28.8638}   # Кишинёв
D=${3:-44.4268}; DL=${4:-26.1025}   # Бухарест
THRESH=${5:-50}

req="{\"locations\":[{\"lat\":$O,\"lon\":$OL},{\"lat\":$D,\"lon\":$DL}],\"costing\":\"auto\"}"
docker exec vhdev valhalla_service /regions/mono.json route "$req" > /tmp/route_mono.json 2>/dev/null
docker exec vhdev valhalla_service /regions/mr.json   route "$req" > /tmp/route_mr.json   2>/dev/null

for f in /tmp/route_mono.json /tmp/route_mr.json; do
  if ! grep -q '"trip"' "$f"; then
    echo "   $f: маршрут не построен"; head -c 200 "$f"; echo; exit 1
  fi
done

python3 "$(dirname "${BASH_SOURCE[0]}")/shape_divergence.py" \
  /tmp/route_mono.json /tmp/route_mr.json "$THRESH"

echo
echo "=== манёвры вокруг расхождения (первые 12 каждого)"
for f in /tmp/route_mono.json /tmp/route_mr.json; do
  echo "--- $(basename "$f")"
  python3 -c "
import json,sys
raw=open('$f',encoding='utf-8').read()
d=json.loads(raw[raw.index('{'):])
for m in d['trip']['legs'][0]['maneuvers'][:12]:
    nm=(m.get('street_names') or [''])[0]
    print('   %7.2f км  %s' % (m.get('length',0), nm or m.get('instruction','')[:52]))
"
done
