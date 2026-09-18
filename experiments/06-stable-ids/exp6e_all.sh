#!/usr/bin/env bash
# Experiment 6E, part 3: the whole installed set, and what applying the patches costs.
#
# Romania alone came to 1.81 %. The number that matters for the car is the WHOLE monthly update:
# every tile it holds, across all six countries. And a patch scheme is only usable if the car can
# apply it, so bspatch is timed and its peak memory recorded — the head unit is not this machine.
set -u
ROOT=/data
W=/data/exp6all; rm -rf "$W"; mkdir -p "$W"

total_new=0; total_patch=0; total_zstd=0
n=0; identical=0; verified=0; failed=0
apply_ns=0; create_ns=0; peak_kb=0
worst=0; worst_name=""

# The installed set is the union of the six T0 cuts; compare each against REF's master tiles.
while read -r t; do
  old="$ROOT/T0/tiles/$t"
  new="$ROOT/REF/tiles/$t"
  [ -f "$old" ] && [ -f "$new" ] || continue
  sn=$(stat -c%s "$new"); n=$((n+1)); total_new=$((total_new + sn))

  if cmp -s "$old" "$new"; then identical=$((identical+1)); continue; fi

  zstd -q -19 -f "$new" -o "$W/w.zst" 2>/dev/null
  total_zstd=$((total_zstd + $(stat -c%s "$W/w.zst")))

  rm -f "$W/p.bs" "$W/r"
  t0=$(date +%s%N)
  bsdiff "$old" "$new" "$W/p.bs" 2>/dev/null
  create_ns=$((create_ns + $(date +%s%N) - t0))
  [ -s "$W/p.bs" ] || { failed=$((failed+1)); continue; }
  sp=$(stat -c%s "$W/p.bs"); total_patch=$((total_patch + sp))
  p=$((100 * sp / sn)); if [ "$p" -gt "$worst" ]; then worst=$p; worst_name="$t"; fi

  t0=$(date +%s%N)
  /usr/bin/time -f "%M" -o "$W/mem" bspatch "$old" "$W/r" "$W/p.bs" 2>/dev/null
  apply_ns=$((apply_ns + $(date +%s%N) - t0))
  m=$(cat "$W/mem" 2>/dev/null || echo 0); [ "$m" -gt "$peak_kb" ] && peak_kb=$m

  if [ "$(sha256sum "$W/r" | cut -d' ' -f1)" = "$(sha256sum "$new" | cut -d' ' -f1)" ]; then
    verified=$((verified+1))
  else failed=$((failed+1)); echo "  SHA MISMATCH $t"; fi
  [ $((n % 250)) -eq 0 ] && echo "  ...$n tiles, patches $((total_patch/1048576)) MB"
done < <(cd "$ROOT/REF/tiles" && find . -name '*.gph' | sed 's|^\./||' | sort)

awk -v n="$n" -v id="$identical" -v v="$verified" -v f="$failed" \
    -v tn="$total_new" -v tp="$total_patch" -v tz="$total_zstd" \
    -v ap="$apply_ns" -v cr="$create_ns" -v pk="$peak_kb" \
    -v wn="$worst_name" -v w="$worst" 'BEGIN{
  printf "\n=========== ALL SIX COUNTRIES, one fortnight of Romania ===========\n";
  printf "tiles compared                %6d\n", n;
  printf "   byte-identical             %6d   (%.1f %%)\n", id, 100*id/n;
  printf "   patched and VERIFIED       %6d\n", v;
  printf "   FAILED                     %6d\n", f;
  printf "\nfull graph                  %12d B  %8.1f MB\n", tn, tn/1048576;
  printf "changed tiles, zstd -19     %12d B  %8.1f MB   %5.2f %%\n", tz, tz/1048576, 100*tz/tn;
  printf "BSDIFF PATCHES              %12d B  %8.1f MB   %5.2f %%\n", tp, tp/1048576, 100*tp/tn;
  printf "\nworst single tile           %s at %d %%\n", wn, w;
  printf "creating all patches        %8.1f s  (server side)\n", cr/1e9;
  printf "APPLYING all patches        %8.1f s  (what the car does)\n", ap/1e9;
  printf "peak bspatch memory         %8.1f MB on the largest tile\n", pk/1024;
  if (f==0) print "\nEVERY reconstruction verified byte for byte";
  else      print "\nREFUSING: reconstructions failed";
}'
