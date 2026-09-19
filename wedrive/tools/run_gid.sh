#!/usr/bin/env bash
set -u
SP="/mnt/c/Users/vpere/AppData/Local/Temp/claude/C--Users-vpere-AndroidStudioProjects-wedrive/9d672018-fcd7-4735-9e25-f33a3c723c7f/scratchpad"
sed 's/\r$//' "$SP/gid_test.cc" > /tmp/gid_test.cc
docker cp /tmp/gid_test.cc vhdev:/tmp/ >/dev/null
docker exec vhdev rm -f /tmp/gid_test
docker exec vhdev bash -c 'cd /tmp && g++ -std=c++20 -O1 gid_test.cc -o gid_test \
  $(pkg-config --cflags libvalhalla) 2>&1 | head -15'
docker exec vhdev bash -c 'test -x /tmp/gid_test && /tmp/gid_test || echo BUILD_FAILED'

echo
echo "########## ревизия: ВСЕ методы GraphId, которые пересобирают value"
docker exec vhdev bash -c "grep -nE 'value = |return GraphId\(' /src/valhalla/valhalla/baldr/graphid.h"
