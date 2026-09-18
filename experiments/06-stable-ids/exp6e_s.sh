#!/usr/bin/env bash
# Experiment 6E, part 1: three delta algorithms on a representative sample.
#
# The architecture this decides is NOT mixed generations. It is:
#     the car holds coherent generation N; the server builds N+1 and diffs every tile;
#     the car downloads PATCHES and reconstructs N+1 byte for byte.
# There is then no mixed graph, no closure, and no change to Valhalla: the tiles the car ends up
# with are exactly the ones the server built. The only question is
#     sum of patches / size of the new graph
#
# SIZE IS NOT THE CRITERION ON ITS OWN. Every patch is applied and the result's SHA256 compared
# with the target. A small patch that reconstructs the wrong bytes is worth nothing.
set -u
ROOT=/data
W=/data/exp6e; rm -rf "$W"; mkdir -p "$W"

pick() {
  local want="$1" lvl="$2"
  (cd "$ROOT/REF/cuts/RO" && find "$lvl" -name '*.gph' -printf '%s %p\n' 2>/dev/null \
     | sort -n | awk -v w="$want" 'function a(x){return x<0?-x:x}
        {d=a($1-w); if(best==""||d<bd){bd=d;best=$2}} END{if(best!="")print best}')
}

TILES=()
for spec in "300000 2" "12000000 2" "99999999 1" "99999999 0"; do
  set -- $spec
  p=$(pick "$1" "$2")
  [ -n "${p:-}" ] && TILES+=("$p")
done

echo "sample: ${#TILES[@]} tiles"
printf '%-22s %10s %9s %9s %9s %9s   %s\n' tile bytes zstd19 zstdpatch xdelta3 bsdiff verify
echo "--------------------------------------------------------------------------------------------"

for t in "${TILES[@]}"; do
  old="$ROOT/T0/cuts/RO/$t"
  new="$ROOT/REF/cuts/RO/$t"
  [ -f "$old" ] && [ -f "$new" ] || { echo "  $t missing"; continue; }
  sn=$(stat -c%s "$new")
  want=$(sha256sum "$new" | cut -d' ' -f1)

  zstd -q -19 -f "$new" -o "$W/w.zst" 2>/dev/null; zw=$(stat -c%s "$W/w.zst")

  zstd -q -19 -f --patch-from="$old" --long=27 "$new" -o "$W/p.zst" 2>/dev/null
  zp=$(stat -c%s "$W/p.zst" 2>/dev/null || echo 0)
  rm -f "$W/r1"; zstd -q -d -f --patch-from="$old" --long=27 "$W/p.zst" -o "$W/r1" 2>/dev/null
  v1=$([ -f "$W/r1" ] && [ "$(sha256sum "$W/r1" | cut -d' ' -f1)" = "$want" ] && echo z:ok || echo z:BAD)

  rm -f "$W/p.xd"; xdelta3 -q -9 -S lzma -f -e -s "$old" "$new" "$W/p.xd" 2>/dev/null
  xp=$(stat -c%s "$W/p.xd" 2>/dev/null || echo 0)
  rm -f "$W/r2"; xdelta3 -q -f -d -s "$old" "$W/p.xd" "$W/r2" 2>/dev/null
  v2=$([ -f "$W/r2" ] && [ "$(sha256sum "$W/r2" | cut -d' ' -f1)" = "$want" ] && echo x:ok || echo x:BAD)

  rm -f "$W/p.bs"; bsdiff "$old" "$new" "$W/p.bs" 2>/dev/null
  bp=$(stat -c%s "$W/p.bs" 2>/dev/null || echo 0)
  rm -f "$W/r3"; bspatch "$old" "$W/r3" "$W/p.bs" 2>/dev/null
  v3=$([ -f "$W/r3" ] && [ "$(sha256sum "$W/r3" | cut -d' ' -f1)" = "$want" ] && echo b:ok || echo b:BAD)

  pct() { [ "$2" -gt 0 ] && echo "$((100*$1/$2))%" || echo "-"; }
  printf '%-22s %10d %9s %9s %9s %9s   %s %s %s\n' \
    "$t" "$sn" "$(pct $zw $sn)" "$(pct $zp $sn)" "$(pct $xp $sn)" "$(pct $bp $sn)" "$v1" "$v2" "$v3"
done
