#!/usr/bin/env bash
# Адреса в имена. valhalla_service слинкован статически, backtrace_symbols отдаёт голые смещения.
set -u
ADDRS=$(docker exec vhdev bash -c 'valhalla_service /regions/mr.json route "{\"locations\":[{\"lat\":47.1585,\"lon\":27.6014},{\"lat\":44.4268,\"lon\":26.1025}],\"costing\":\"auto\"}" 2>&1' \
  | grep -A 8 'REGION LOST #0' | grep -oP 'valhalla_service\(\+\K0x[0-9a-f]+')
echo "адреса: $(echo $ADDRS | tr '\n' ' ')"
echo
for a in $ADDRS; do
  out=$(docker exec vhdev addr2line -e /usr/local/bin/valhalla_service -f -C -i "$a" 2>/dev/null | head -2 | tr '\n' ' ')
  printf '   %-10s %s\n' "$a" "${out:0:150}"
done
