#!/usr/bin/env bash
# Point 6, second half: MANY portals, derived from the graphs, and the search left to choose.
set -u

# Scan all three hierarchy levels. A portal on level 2 is reachable from a motorway only by
# descending a NodeTransition first, so a table that covers every level lets the search cross
# wherever it already is rather than forcing it down to local roads at the frontier.
: > /tmp/portals_all.txt
for lvl in 0 1 2; do
  docker exec vhdev /tmp/portal_find /regions/moldova/tiles /regions/romania/tiles \
    45.4 26.6 48.3 28.3 "$lvl" >> /tmp/portals_all.txt
done
echo "   portal table: $(wc -l < /tmp/portals_all.txt) directed entries"
docker cp /tmp/portals_all.txt vhdev:/tmp/ >/dev/null

R="docker exec vhdev /tmp/compose_route /regions/moldova/tiles /regions/romania/tiles"

echo
echo "########## Chisinau -> Iasi, ONE hand-picked portal (Leuseni/Albita)"
$R 47.0105 28.8638 47.1585 27.6014 both+portal

echo
echo "########## Chisinau -> Iasi, the FULL derived table"
$R 47.0105 28.8638 47.1585 27.6014 both+portal /tmp/portals_all.txt

echo
echo "########## Chisinau -> Bucharest, the FULL derived table"
echo "   (Bucharest is absent from Moldova's graph entirely, so this can only be composed)"
$R 47.0105 28.8638 44.4268 26.1025 both+portal /tmp/portals_all.txt

echo
echo "########## CONTROL: Chisinau -> Bucharest with NO portals"
$R 47.0105 28.8638 44.4268 26.1025 both
