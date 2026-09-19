#!/usr/bin/env bash
# Полный production pipeline: HTTP/JSON -> Loki -> Thor -> recost -> TripPath -> Odin -> JSON.
#
# Odin СПЕЦИАЛЬНО не патчен. Если Thor отдаёт дальше tagged GraphId и какой-то код ниже примет
# наши верхние биты за часть обычного идентификатора Valhalla — это проявится именно здесь.
set -u
MD=/regions/moldova/tiles
RO=/regions/romania/tiles
MONO=/regions/mono/tiles
PORTALS=/regions/portals_border.txt

docker exec vhdev bash -c "cp /tmp/portals_border.txt $PORTALS 2>/dev/null || true"

# Конфиг мультирегиона: tile_dir остаётся молдавским (регион по умолчанию), плюс два региона и
# таблица переходов.
docker exec vhdev bash -c "valhalla_build_config \
    --mjolnir-tile-dir $MD --mjolnir-tile-extract '' --mjolnir-timezone '' --mjolnir-admin '' \
    > /regions/mr.json 2>/dev/null
  python3 - <<'PY'
import json
c = json.load(open('/regions/mr.json'))
c['mjolnir']['wedrive_regions'] = [{'id': 1, 'dir': '$MD'}, {'id': 2, 'dir': '$RO'}]
c['mjolnir']['wedrive_portals'] = '$PORTALS'
json.dump(c, open('/regions/mr.json','w'))
print('конфиг:', c['mjolnir']['wedrive_regions'], c['mjolnir']['wedrive_portals'])
PY"

# Монолитный конфиг для сравнения.
docker exec vhdev bash -c "valhalla_build_config \
    --mjolnir-tile-dir $MONO --mjolnir-tile-extract '' --mjolnir-timezone '' --mjolnir-admin '' \
    > /regions/mono.json 2>/dev/null"

ask() { # cfg olat olon dlat dlon label
  local out
  out=$(docker exec vhdev valhalla_service "$1" route \
    "{\"locations\":[{\"lat\":$2,\"lon\":$3},{\"lat\":$4,\"lon\":$5}],\"costing\":\"auto\"}" 2>&1)
  echo "$out" | python3 -c '
import sys, json
raw = sys.stdin.read()
start = raw.find("{")
if start < 0:
    print("   ОТВЕТ НЕ JSON:", raw.strip()[:160]); raise SystemExit
try:
    d = json.loads(raw[start:])
except Exception as e:
    print("   JSON НЕ РАЗБИРАЕТСЯ:", str(e)[:80], "|", raw[start:start+160]); raise SystemExit
if "error" in d:
    print("   ОШИБКА:", d.get("error"), d.get("error_code")); raise SystemExit
t = d["trip"]; s = t["summary"]
man = sum(len(l["maneuvers"]) for l in t["legs"])
shp = sum(len(l["shape"]) for l in t["legs"])
print("   %9.3f км %9.1f с  legs %d  манёвров %3d  shape %5d симв." %
      (s["length"], s["time"], len(t["legs"]), man, shp))
'
}

pair() { # olat olon dlat dlon label
  echo "=== $5"
  printf '   %-10s' "монолит"; ask /regions/mono.json "$1" "$2" "$3" "$4" | sed 's/^   //'
  printf '   %-10s' "мультирег"; ask /regions/mr.json "$1" "$2" "$3" "$4" | sed 's/^   //'
}

pair 47.0105 28.8638 47.2075 27.8000 "внутри MD: Кишинёв -> Унгены"
pair 47.1585 27.6014 44.4268 26.1025 "внутри RO: Яссы -> Бухарест"
pair 47.0105 28.8638 47.1585 27.6014 "MD -> RO: Кишинёв -> Яссы"
pair 47.1585 27.6014 47.0105 28.8638 "RO -> MD: Яссы -> Кишинёв"
pair 47.0105 28.8638 44.4268 26.1025 "длинный: Кишинёв -> Бухарест"
pair 46.8233 28.1407 47.0105 28.8638 "из перекрытия: переход -> Кишинёв"
