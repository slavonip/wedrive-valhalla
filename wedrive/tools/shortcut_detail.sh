#!/usr/bin/env bash
# Каждый шорткат выигравшего пути: входы расчёта, EdgeCost и фактический прирост при recost.
# Плюс позиция смены региона — чтобы увидеть, сидят шорткаты до портала или после.
set -u
REQ='{"locations":[{"lat":47.0105,"lon":28.8638},{"lat":44.4268,"lon":26.1025}],"costing":"auto"}'
out=~/scdetail.txt
docker exec -e WEDRIVE_DEBUG_BIDIR=1 vhdev valhalla_service /regions/mr.json route "$REQ" > "$out" 2>&1

echo "=== смена региона в пути"
grep 'WEDRIVE SEAM' "$out" | sed 's/^/    /' || echo "    шва не найдено"
echo
echo "=== шорткаты"
grep 'WEDRIVE SC #' "$out" | sed 's/^/    /'
echo
echo "=== итог"
grep -E 'WEDRIVE (SHORTCUTS|RECOST)' "$out" | sed 's/^/    /'
echo
echo "=== сумма расхождений по шорткатам"
grep 'WEDRIVE SC #' "$out" | python3 -c '
import re, sys
tot_ec = tot_rc = 0.0
n = 0
for line in sys.stdin:
    ec = re.search(r"EdgeCost=([0-9.]+)", line)
    rc = re.search(r"приростRecost=(-?[0-9.]+)", line)
    if ec and rc:
        tot_ec += float(ec.group(1)); tot_rc += float(rc.group(1)); n += 1
print("    шорткатов %d:  Σ EdgeCost=%.1f   Σ приростRecost=%.1f   разница=%.1f"
      % (n, tot_ec, tot_rc, tot_rc - tot_ec))
'
