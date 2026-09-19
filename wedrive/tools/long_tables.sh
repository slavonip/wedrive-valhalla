#!/usr/bin/env bash
# Хватает ли порталов на НУЖНОМ уровне иерархии?
#
# portal_border нашёл 14 пар на level 0, 0 на level 1 и 2 на level 2. Если оптимальный маршрут
# требует перехода на level 1, его просто нет — и поиск делает крюк к ближайшему переходу.
# Полная таблица зоны перекрытия такого ограничения не имеет, поэтому она и есть проверка.
set -u
one() { # cfg-portals label
  local cfg=/tmp/cfg_$$.json
  docker exec vhdev python3 -c "
import json
c=json.load(open('/regions/mr.json'))
c['mjolnir']['wedrive_portals']='$1'
json.dump(c, open('$cfg','w'))
"
  local out
  out=$(docker exec vhdev valhalla_service "$cfg" route \
    "{\"locations\":[{\"lat\":47.0105,\"lon\":28.8638},{\"lat\":44.4268,\"lon\":26.1025}],\"costing\":\"auto\"}" 2>/dev/null)
  printf '   %-22s' "$2"
  echo "$out" | python3 -c '
import sys, json
raw=sys.stdin.read(); i=raw.find("{")
if i<0: print("нет ответа"); raise SystemExit
d=json.loads(raw[i:])
if "error" in d: print("ОШИБКА:", d["error"][:60]); raise SystemExit
s=d["trip"]["summary"]
print("%8.3f км %9.1f с" % (s["length"], s["time"]))
'
  docker exec vhdev rm -f "$cfg"
}

echo "=== Кишинёв -> Бухарест, разные таблицы порталов"
printf '   %-22s%8.3f км\n' "монолит (эталон)" 456.458
one /regions/portals_border.txt "16 погранпереходов"
docker exec vhdev bash -c 'cp /tmp/portals_all.txt /regions/portals_all.txt'
one /regions/portals_all.txt    "вся зона перекрытия"

echo
echo "=== распределение порталов по уровням"
echo "--- погранпереходы:"
docker exec vhdev bash -c "awk '{print \$1 % 8}' /regions/portals_border.txt | sort | uniq -c | awk '{print \"      level \" \$2 \": \" \$1 \" записей\"}'"
echo "--- зона перекрытия:"
docker exec vhdev bash -c "awk '{print \$1 % 8}' /regions/portals_all.txt | sort | uniq -c | awk '{print \"      level \" \$2 \": \" \$1 \" записей\"}'"
