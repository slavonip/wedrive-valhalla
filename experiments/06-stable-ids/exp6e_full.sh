#!/usr/bin/env bash
# Experiment 6E, part 2: the whole Romania package, every tile, with reconstruction verified.
#
# bsdiff won the sample at 1-4 % against xdelta3's 4-25 % and plain zstd's 29-36 %. That ordering
# makes sense: renumbering DISPLACES content, and bsdiff's suffix sorting is built to find
# displaced matches, where a streaming compressor sees only novel bytes.
#
# Every patch is applied and its SHA256 compared with the target. The run FAILS if a single tile
# reconstructs wrongly — a patch scheme that is 98 % correct is not a patch scheme.
set -u
ROOT=/data
W=/data/exp6full; rm -rf "$W"; mkdir -p "$W"
OLD="$ROOT/T0/cuts/RO"
NEW="$ROOT/REF/cuts/RO"

total_new=0; total_patch=0; total_whole_zstd=0
n=0; identical=0; verified=0; failed=0; newtile=0
worst=0; worst_name=""

while read -r t; do
  new="$NEW/$t"; old="$OLD/$t"
  sn=$(stat -c%s "$new")
  n=$((n+1))
  total_new=$((total_new + sn))

  if [ ! -f "$old" ]; then
    # a tile the car does not have: it must arrive whole, compressed
    zstd -q -19 -f "$new" -o "$W/w.zst" 2>/dev/null
    s=$(stat -c%s "$W/w.zst"); total_patch=$((total_patch + s))
    total_whole_zstd=$((total_whole_zstd + s))
    newtile=$((newtile + 1))
    continue
  fi

  if cmp -s "$old" "$new"; then
    identical=$((identical + 1))
    continue                                   # nothing to send at all
  fi

  zstd -q -19 -f "$new" -o "$W/w.zst" 2>/dev/null
  total_whole_zstd=$((total_whole_zstd + $(stat -c%s "$W/w.zst")))

  rm -f "$W/p.bs" "$W/r"
  bsdiff "$old" "$new" "$W/p.bs" 2>/dev/null
  if [ ! -s "$W/p.bs" ]; then failed=$((failed+1)); echo "  PATCH FAILED $t"; continue; fi
  sp=$(stat -c%s "$W/p.bs")
  total_patch=$((total_patch + sp))
  pct=$((100 * sp / sn))
  if [ "$pct" -gt "$worst" ]; then worst=$pct; worst_name="$t"; fi

  bspatch "$old" "$W/r" "$W/p.bs" 2>/dev/null
  if [ "$(sha256sum "$W/r" | cut -d' ' -f1)" = "$(sha256sum "$new" | cut -d' ' -f1)" ]; then
    verified=$((verified + 1))
  else
    failed=$((failed + 1)); echo "  SHA MISMATCH $t"
  fi
  if [ $((n % 100)) -eq 0 ]; then echo "  ...$n tiles, patches so far $((total_patch/1048576)) MB"; fi
done < <(cd "$NEW" && find . -name '*.gph' | sed 's|^\./||' | sort)

echo
echo "================ ROMANIA, T0 -> REF (one fortnight) ================"
printf 'tiles in the package            %6d\n' "$n"
printf '   byte-identical, nothing sent %6d\n' "$identical"
printf '   patched and VERIFIED         %6d\n' "$verified"
printf '   new, sent whole              %6d\n' "$newtile"
printf '   FAILED                       %6d\n' "$failed"
echo
printf 'full new package                %12d bytes  %8.1f MB\n' "$total_new" "$(echo "$total_new/1048576" | bc -l)"
printf 'every changed tile, zstd -19    %12d bytes  %8.1f MB  %5.1f %%\n' \
  "$total_whole_zstd" "$(echo "$total_whole_zstd/1048576" | bc -l)" \
  "$(echo "100*$total_whole_zstd/$total_new" | bc -l)"
printf 'BSDIFF PATCHES                  %12d bytes  %8.1f MB  %5.1f %%\n' \
  "$total_patch" "$(echo "$total_patch/1048576" | bc -l)" \
  "$(echo "100*$total_patch/$total_new" | bc -l)"
echo
printf 'worst single tile: %s at %d %%\n' "$worst_name" "$worst"
[ "$failed" -eq 0 ] && echo "EVERY reconstruction verified byte for byte" \
                    || echo "REFUSING: $failed tiles did not reconstruct"
