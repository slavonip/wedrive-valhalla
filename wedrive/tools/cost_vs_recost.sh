#!/usr/bin/env bash
# Весь вывод (stdout+stderr) сохраняем НА ХОСТЕ и анализируем там же — прошлая версия
# перенаправляла внутри контейнера через слой кавычек и потеряла файл.
set -u
REQ='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'

for cfg in mono mr; do
  out=~/dbg_$cfg.txt
  docker exec -e WEDRIVE_DEBUG_BIDIR=1 vhdev valhalla_service "/regions/$cfg.json" route "$REQ" > "$out" 2>&1
  echo "=== $cfg: строк всего $(wc -l < "$out")"
  echo "--- все строки WEDRIVE (кроме REGION LOST):"
  grep 'WEDRIVE' "$out" | grep -v 'REGION LOST' | sed 's/^/    /'
  echo "--- маршрут:"
  python3 - "$out" <<'PY'
import json, sys
raw = open(sys.argv[1], encoding="utf-8").read()
i = raw.find('{"trip"')
if i < 0:
    i = raw.find("{")
try:
    d = json.loads(raw[i:])
    s = d["trip"]["summary"]
    print("    %.3f км  %.1f с" % (s["length"], s["time"]))
except Exception as e:
    print("    не разобрать:", str(e)[:60])
PY
  echo
done
