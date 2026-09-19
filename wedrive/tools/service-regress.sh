#!/usr/bin/env bash
# Полная приёмка multi-region через valhalla_service: композит против когерентного монолита.
#
# Четыре службы, и у каждой СВОЙ обход графа — это и есть причина, по которой одной проверки
# маршрута недостаточно:
#
#     route / timed route   thor/bidirectional_astar.cc, unidirectional_astar.cc
#     sources_to_targets    thor/costmatrix.cc
#     isochrone             thor/dijkstras.cc
#     trace_route           meili/routing.cc  (+ свой поиск кандидатов)
#
# Допуск в 0.1 км — не косметика: два графа собраны из разных экстрактов, и совпадение до метра
# не требуется и не ожидается. Требуется, чтобы композит не выбирал ДРУГОЙ коридор.
#
# Потеря региона допускается ровно нулевая: это не расхождение чисел, а признак того, что где-то
# тайл взят из чужого каталога.
set -u
MONO=${1:-/regions/mono_full.json}
MULTI=${2:-/regions/mr_bc.json}
TOL=${3:-0.1}
lost=0
bad=0

metric() { # cfg действие запрос -> число
  local out=/tmp/svc_$$.txt
  docker exec vhdev valhalla_service "$1" "$2" "$3" > "$out" 2>&1
  lost=$(( lost + $(grep -c 'WEDRIVE REGION LOST' "$out") ))
  python3 - "$out" "$2" <<'PY'
import json, sys
t = open(sys.argv[1], encoding='utf-8', errors='replace').read()
action = sys.argv[2]
def jload(prefix):
    i = t.find(prefix)
    return json.loads(t[i:]) if i >= 0 else None
try:
    if action in ('route', 'trace_route'):
        print('%.3f' % jload('{"trip"')['trip']['summary']['length'])
    elif action == 'sources_to_targets':
        # Среднее по ячейке, а не сумма: допуск задан НА ЯЧЕЙКУ, и сумма четырёх ячеек
        # накапливала бы вчетверо большее расхождение при том же качестве ответа.
        d = jload('{"sources_to_targets')
        cells = [c['distance'] for r in d['sources_to_targets'] for c in r]
        print('%.3f' % (sum(cells) / len(cells)))
    else:  # isochrone: сравниваем охват, а не форму
        d = None
        for line in reversed(t.splitlines()):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    d = json.loads(line); break
                except Exception:
                    pass
        lons = []
        for f in d.get('features', []):
            g = f['geometry']
            rings = g['coordinates'] if g['type'] == 'Polygon' else [r for p in g['coordinates'] for r in p]
            for r in rings:
                lons += [c[0] for c in r]
        print('%.3f' % (max(lons) - min(lons)))
except Exception:
    print('ОШИБКА')
PY
  rm -f "$out"
}

check() { # подпись действие запрос
  local a b d
  a=$(metric "$MONO" "$2" "$3")
  b=$(metric "$MULTI" "$2" "$3")
  if [ "$a" = "ОШИБКА" ] || [ "$b" = "ОШИБКА" ]; then
    printf '%-30s %10s %10s   РАСХОЖДЕНИЕ (нет ответа)\n' "$1" "$a" "$b"
    bad=$((bad + 1)); return
  fi
  d=$(python3 -c "print('%.3f' % abs($a - $b))")
  if python3 -c "import sys; sys.exit(0 if abs($a-$b) <= $TOL else 1)"; then
    printf '%-30s %10s %10s   +-%s\n' "$1" "$a" "$b" "$d"
  else
    printf '%-30s %10s %10s   РАСХОЖДЕНИЕ %s\n' "$1" "$a" "$b" "$d"
    bad=$((bad + 1))
  fi
}

R() { echo "{\"locations\":[{\"lat\":$1,\"lon\":$2},{\"lat\":$3,\"lon\":$4}],\"costing\":\"auto\"}"; }

echo "маршрут (км)                      монолит   композит"
check "MD: Кишинёв-Бельцы"      route "$(R 47.0105 28.8638 47.7615 27.9297)"
check "MD: Кишинёв-Кагул"       route "$(R 47.0105 28.8638 45.9081 28.1944)"
check "RO: Яссы-Бухарест"       route "$(R 47.1585 27.6014 44.4268 26.1025)"
check "RO: Бухарест-Клуж"       route "$(R 44.4268 26.1025 46.7712 23.6236)"
check "граница: Кишинёв-Яссы"   route "$(R 47.0105 28.8638 47.1585 27.6014)"
check "граница: Яссы-Кишинёв"   route "$(R 47.1585 27.6014 47.0105 28.8638)"
check "граница: Кишинёв-Бухарест" route "$(R 47.0105 28.8638 44.4268 26.1025)"
check "граница: Бухарест-Кишинёв" route "$(R 44.4268 26.1025 47.0105 28.8638)"
check "граница: Кишинёв-Бырлад" route "$(R 47.0105 28.8638 46.2333 27.6667)"

echo
echo "по времени (однонаправленный)"
check "Кишинёв-Бухарест timed" route \
  '{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto","date_time":{"type":1,"value":"2026-09-19T08:00"}}'

echo
echo "матрица (среднее по ячейке, км)"
check "2x2 MD->RO" sources_to_targets \
  '{"sources":[{"lat":47.0105,"lon":28.8638},{"lat":47.7615,"lon":27.9297}],"targets":[{"lat":47.1585,"lon":27.6014},{"lat":46.2333,"lon":27.6667}],"costing":"auto"}'

echo
echo "изолиния (ширина охвата по долготе, градусы)"
check "45 мин от границы" isochrone \
  '{"locations":[{"lat":46.4806,"lon":28.2321}],"costing":"auto","contours":[{"time":45}],"polygons":true}'
check "60 мин из Кишинёва" isochrone \
  '{"locations":[{"lat":47.0105,"lon":28.8638}],"costing":"auto","contours":[{"time":60}],"polygons":true}'

# Трасса строится здесь же, а не приносится извне: иначе в свежем клоне этот пункт молча
# пропускался бы — то есть проверка сопоставления отсутствовала бы ровно там, где она нужна.
# Геометрия берётся у МОНОЛИТА, чтобы точки заведомо лежали на реальной дороге, и прореживается
# до шага в 150 м — это похоже на GPS, а не на исходную геометрию.
docker exec -i vhdev python3 - "$MONO" <<'PY' >/dev/null 2>&1
import json, math, subprocess, sys

def decode(s, prec=1e-6):
    pts, i, lat, lon = [], 0, 0, 0
    while i < len(s):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63; i += 1
                result |= (b & 0x1f) << shift; shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if (result & 1) else (result >> 1)
            if which == 0:
                lat += d
            else:
                lon += d
        pts.append((lat * prec, lon * prec))
    return pts

req = {"locations": [{"lat": 47.0105, "lon": 28.8638}, {"lat": 47.1585, "lon": 27.6014}],
       "costing": "auto"}
out = subprocess.run(["valhalla_service", sys.argv[1], "route", json.dumps(req)],
                     capture_output=True, text=True).stdout
trip = json.loads(out[out.find('{"trip"'):])["trip"]
shape = []
for leg in trip["legs"]:
    shape += decode(leg["shape"])
kept = [shape[0]]
for p in shape[1:]:
    a = kept[-1]
    d = math.hypot((a[0] - p[0]) * 111320,
                   (a[1] - p[1]) * 111320 * math.cos(math.radians(a[0])))
    if d >= 150:
        kept.append(p)
kept.append(shape[-1])
pts = [{"lat": round(la, 6), "lon": round(lo, 6), "type": "via"} for la, lo in kept]
pts[0]["type"] = pts[-1]["type"] = "break"
json.dump({"shape": pts, "costing": "auto", "shape_match": "map_snap"},
          open("/tmp/trace_req.json", "w"))
PY

if docker exec vhdev test -f /tmp/trace_req.json; then
  echo
  n=$(docker exec vhdev python3 -c 'import json;print(len(json.load(open("/tmp/trace_req.json"))["shape"]))')
  echo "сопоставление трассы (км), точек: $n"
  check "Кишинёв-Яссы по GPS" trace_route "$(docker exec vhdev cat /tmp/trace_req.json)"
else
  echo
  echo "сопоставление трассы ПРОПУЩЕНО: не удалось построить трассу"
  bad=$((bad + 1))
fi

echo
echo "ПОТЕРЬ РЕГИОНА ЗА ВСЮ РЕГРЕССИЮ: $lost"
echo "РАСХОЖДЕНИЙ СВЕРХ ДОПУСКА: $bad"
[ "$lost" = "0" ] && [ "$bad" = "0" ]
