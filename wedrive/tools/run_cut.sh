#!/usr/bin/env bash
# Production-таблица: только настоящие пересечения линии разреза.
set -u
SP="/mnt/c/Users/vpere/AppData/Local/Temp/claude/C--Users-vpere-AndroidStudioProjects-wedrive/9d672018-fcd7-4735-9e25-f33a3c723c7f/scratchpad"
sed 's/\r$//' "$SP/portal_cut.cc" > /tmp/portal_cut.cc
docker cp /tmp/portal_cut.cc vhdev:/tmp/ >/dev/null
docker exec vhdev rm -f /tmp/portal_cut
docker exec vhdev bash -c 'cd /tmp && g++ -std=c++20 -O2 portal_cut.cc -o portal_cut \
  $(pkg-config --cflags --libs libvalhalla) 2>&1 | head -15'
docker exec vhdev bash -c 'test -x /tmp/portal_cut && echo BUILD_OK || exit 1' || exit 1

A=/regions/split/a/tiles
B=/regions/split/b/tiles
MD=/regions/moldova/tiles

: > /tmp/portals_prod.txt
for lvl in 0 1 2; do
  docker exec vhdev /tmp/portal_cut "$A" "$B" 47.00 0.02 26.0 30.5 "$lvl" >> /tmp/portals_prod.txt
done
echo "   production-таблица: $(wc -l < /tmp/portals_prod.txt) записей"
echo "   (для сравнения: полоса 1 км дала 11672, вся зона перекрытия 235022)"
docker cp /tmp/portals_prod.txt vhdev:/tmp/ >/dev/null
echo
echo "   где именно стоят порталы:"
sort -u -k4 /tmp/portals_prod.txt | awk '{print "      " $4, $5}' | sort -u | head -20

T="docker exec vhdev /tmp/thor_route"
N="47.7615 27.9297"; S="45.9081 28.1944"
keep() { grep -E 'МАРШРУТ|NO ROUTE|region lost|переход|НЕПРЕРЫВНОСТЬ'; }

echo
echo "===== ЭТАЛОН цельная Moldova"
$T $MD $MD $N $S r1 2>&1 | keep
$T $MD $MD $S $N r1 2>&1 | keep
echo
echo "===== A+B, production-таблица"
$T "$A" "$B" $N $S both+portal /tmp/portals_prod.txt 2>&1 | keep
echo "   обратно:"
$T "$A" "$B" $S $N both+portal /tmp/portals_prod.txt 2>&1 | keep
