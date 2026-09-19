#!/usr/bin/env bash
# Point 7: does a route composed from two halves of Moldova match the route the WHOLE Moldova
# graph gives? The whole graph is the reference, so this has an exact number to be wrong against --
# unlike the MD/RO work, where no single-pass build of that pair exists here to compare with.
set -u

A=/regions/split/a/tiles
B=/regions/split/b/tiles
WHOLE=/regions/moldova/tiles

# Balti is north of the cut (in A only); Cahul is south of it (in B only).
N="47.7615 27.9297"
S="45.9081 28.1944"

echo "########## REFERENCE: whole Moldova, one graph, no portals"
docker exec vhdev /tmp/compose_route "$WHOLE" "$WHOLE" $N $S md

echo
echo "########## A alone (north half)"
docker exec vhdev /tmp/compose_route "$A" "$B" $N $S md
echo
echo "########## B alone (south half)"
docker exec vhdev /tmp/compose_route "$A" "$B" $N $S ro

echo
echo "########## A + B loaded together, NO portals  <-- the negative control"
docker exec vhdev /tmp/compose_route "$A" "$B" $N $S both

echo
echo "=== derive the portal table across the cut (the 46.90..47.10 overlap band)"
: > /tmp/portals_split.txt
for lvl in 0 1 2; do
  docker exec vhdev /tmp/portal_find "$A" "$B" 46.90 26.0 47.10 30.5 "$lvl" >> /tmp/portals_split.txt
done
echo "   $(wc -l < /tmp/portals_split.txt) directed entries"
docker cp /tmp/portals_split.txt vhdev:/tmp/ >/dev/null

echo
echo "########## A + B with portals  <-- must match the reference"
docker exec vhdev /tmp/compose_route "$A" "$B" $N $S both+portal /tmp/portals_split.txt
