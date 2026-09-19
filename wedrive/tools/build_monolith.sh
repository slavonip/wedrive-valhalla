#!/usr/bin/env bash
# Когерентная сборка Молдовы и Румынии ОДНИМ проходом — эталон, с которым сравнивается композит.
# До сих пор монолитом служила цифра 150.1 км из документации фабрики; для сравнения на
# нескольких десятках маршрутов нужен настоящий граф.
set -eu
W=/regions/mono
docker exec vhdev bash -c "mkdir -p $W/tiles && ls -la /regions/src/*.osm.pbf"
docker exec vhdev bash -c "cat > $W/valhalla.json <<'JSON'
{\"mjolnir\":{\"tile_dir\":\"$W/tiles\",\"concurrency\":22,\"logging\":{\"type\":\"\"}}}
JSON
cd $W && time valhalla_build_tiles -c valhalla.json \
  /regions/src/moldova.osm.pbf /regions/src/romania.osm.pbf > $W/build.log 2>&1
echo BUILD_DONE
find $W/tiles -name '*.gph' | wc -l
du -sh $W/tiles"
