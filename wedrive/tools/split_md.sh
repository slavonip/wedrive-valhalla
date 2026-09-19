#!/usr/bin/env bash
# Point 7: cut Moldova in half MYSELF and rebuild each half as its own graph.
#
# Everything so far has run on Geofabrik extracts, which overlap at the frontier -- so a sceptic
# can say the portal only worked because both graphs already held the junction. Here the cut is
# ours: MD-A north of 47.0, MD-B south of it, built independently, with a deliberate SMALL overlap
# band so that coincident junctions exist to be portals at all. The reference is whole Moldova,
# already built, so the composed answer has something exact to be wrong against.
set -eu

PBF=/regions/src/moldova.osm.pbf
WORK=/regions/split

docker exec vhdev bash -c "ls -la $PBF" || {
  echo "!! the Moldova pbf is not where this expects it; looking for it"
  docker exec vhdev bash -c 'find /regions -name "*.osm.pbf" | head'
  exit 1
}

docker exec vhdev bash -c "mkdir -p $WORK/a $WORK/b"

# A 0.1 degree overlap band (about 11 km) around the cut. Without it the two halves share no
# junction and no portal can exist -- which is itself the finding that the overlap is load-bearing.
echo "=== cutting"
docker exec vhdev bash -c "osmium extract -b 26.0,46.90,30.5,48.6 -o $WORK/a/md-a.osm.pbf --overwrite $PBF 2>&1 | tail -2"
docker exec vhdev bash -c "osmium extract -b 26.0,45.0,30.5,47.10 -o $WORK/b/md-b.osm.pbf --overwrite $PBF 2>&1 | tail -2"
docker exec vhdev bash -c "ls -la $WORK/a/md-a.osm.pbf $WORK/b/md-b.osm.pbf"

echo
echo "=== building each half as its own independent graph"
for half in a b; do
  docker exec vhdev bash -c "
    mkdir -p $WORK/$half/tiles
    cat > $WORK/$half/valhalla.json <<'JSON'
{\"mjolnir\":{\"tile_dir\":\"$WORK/$half/tiles\",\"concurrency\":8,\"logging\":{\"type\":\"\"}}}
JSON
    cd $WORK/$half && valhalla_build_tiles -c valhalla.json md-$half.osm.pbf >/dev/null 2>&1
    echo \"   $half: \$(find $WORK/$half/tiles -name '*.gph' | wc -l) tiles, \$(du -sh $WORK/$half/tiles | cut -f1)\"
  "
done
