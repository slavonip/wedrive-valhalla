#!/usr/bin/env bash
# Restore the five touched files from the pristine clone, then apply both patches exactly once.
#
# The first attempt applied the GraphId constants twice, because the idempotency check looked for
# a marker that the first edit had not yet written. Restoring is cheaper and surer than trying to
# unpick a double-applied patch.
set -u
SP="/mnt/c/Users/vpere/AppData/Local/Temp/claude/C--Users-vpere-AndroidStudioProjects-wedrive/9d672018-fcd7-4735-9e25-f33a3c723c7f/scratchpad"
SRC="$HOME/vhbuild/src"

echo "=== restoring pristine files into the container ==="
for f in valhalla/baldr/graphid.h valhalla/baldr/graphtile.h valhalla/baldr/graphreader.h \
         src/baldr/graphtile.cc src/baldr/graphreader.cc; do
  docker cp "$SRC/$f" "vhdev:/src/valhalla/$f" >/dev/null
  printf '  %-40s %s\n' "$f" "$(docker exec vhdev grep -c WEDRIVE "/src/valhalla/$f" || true)"
done

for f in patch_multiregion.py patch_mr2.py wedrive_regions_test.cc; do
  sed 's/\r$//' "$SP/$f" > "/tmp/$f"
  docker cp "/tmp/$f" "vhdev:/tmp/$f" >/dev/null
done

echo
echo "=== applying once ==="
docker exec vhdev bash -c '
  cd /tmp
  sed -i "s#os.path.expanduser(\"~/vhbuild/src\")#\"/src/valhalla\"#" patch_multiregion.py patch_mr2.py
  python3 patch_multiregion.py && echo && python3 patch_mr2.py'
rc=$?
echo
echo "=== WEDRIVE markers per file (each should appear once per edit) ==="
docker exec vhdev bash -c 'grep -c WEDRIVE /src/valhalla/valhalla/baldr/graphid.h \
  /src/valhalla/valhalla/baldr/graphtile.h /src/valhalla/src/baldr/graphtile.cc \
  /src/valhalla/valhalla/baldr/graphreader.h /src/valhalla/src/baldr/graphreader.cc'
echo "constants defined once? $(docker exec vhdev grep -c kRegionShift /src/valhalla/valhalla/baldr/graphid.h) occurrences of kRegionShift (2 = declaration + use)"
exit $rc
