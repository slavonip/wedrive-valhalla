#!/usr/bin/env bash
# Виноваты ли шорткаты в недосчёте 1234.44?
#
# Два независимых измерения:
#   1. сколько шорткатов в выигравшем пути и насколько он разворачивается при recost;
#   2. контрольный прогон вообще без шорткатов — если маршрут станет монолитным и недосчёт
#      вернётся к норме, гипотеза подтверждена; если нет, шорткаты невиновны.
set -u
REQ='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'

run() { # cfg метка доп-env
  local out=~/probe_$$.txt
  if [ -n "${3:-}" ]; then
    docker exec -e WEDRIVE_DEBUG_BIDIR=1 -e "$3" vhdev valhalla_service "$1" route "$REQ" > "$out" 2>&1
  else
    docker exec -e WEDRIVE_DEBUG_BIDIR=1 vhdev valhalla_service "$1" route "$REQ" > "$out" 2>&1
  fi
  echo "=== $2"
  grep -E 'WEDRIVE (SHORTCUTS|RECOST)' "$out" | sed 's/^/    /'
  python3 - "$out" <<'PY'
import json, sys
raw = open(sys.argv[1], encoding="utf-8").read()
i = raw.find("{")
try:
    d = json.loads(raw[i:])
    s = d["trip"]["summary"]
    print("    маршрут: %.3f км  %.1f с" % (s["length"], s["time"]))
except Exception:
    j = raw.rfind('{"error_code"')
    print("    маршрут:", json.loads(raw[j:])["error"][:60] if j >= 0 else "не разобрать")
PY
  rm -f "$out"
}

run /regions/mono.json "МОНОЛИТ, шорткаты как обычно"
echo
run /regions/mr.json   "КОМПОЗИТ, шорткаты как обычно"
echo
run /regions/mr.json   "КОМПОЗИТ БЕЗ ШОРТКАТОВ" "WEDRIVE_NO_SHORTCUTS=1"
echo
run /regions/mono.json "МОНОЛИТ БЕЗ ШОРТКАТОВ" "WEDRIVE_NO_SHORTCUTS=1"
