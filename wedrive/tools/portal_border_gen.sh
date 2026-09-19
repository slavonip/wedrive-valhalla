#!/usr/bin/env bash
set -u
SP="/mnt/c/Users/vpere/AppData/Local/Temp/claude/C--Users-vpere-AndroidStudioProjects-wedrive/9d672018-fcd7-4735-9e25-f33a3c723c7f/scratchpad"
sed 's/\r$//' "$SP/fork/wedrive/tools/portal_border.cc" > /tmp/portal_border.cc
docker cp /tmp/portal_border.cc vhdev:/tmp/ >/dev/null
docker exec vhdev rm -f /tmp/portal_border
docker exec vhdev bash -c 'cd /tmp && g++ -std=c++20 -O2 portal_border.cc -o portal_border \
  $(pkg-config --cflags --libs libvalhalla) 2>&1 | grep -E "error:" | head -8'
docker exec vhdev bash -c 'test -x /tmp/portal_border && echo BUILD_OK || exit 1' || exit 1

: > /tmp/portals_border.txt
for lvl in 0 1 2; do
  docker exec vhdev /tmp/portal_border /regions/moldova/tiles /regions/romania/tiles \
    45.4 26.6 48.3 28.3 "$lvl" >> /tmp/portals_border.txt
done
echo
echo "   таблица границы: $(wc -l < /tmp/portals_border.txt) записей"
echo "   (полная зона перекрытия давала 12508)"
docker cp /tmp/portals_border.txt vhdev:/tmp/ >/dev/null
echo
echo "   где стоят порталы (широта, долгота):"
awk '{print "      " $5, $6}' /tmp/portals_border.txt | sort -u | head -40
