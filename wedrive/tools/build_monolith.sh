#!/usr/bin/env bash
# Эталонный монолит MD+RO — теми же входами, что и отдельные страны.
#
# Первая версия собиралась БЕЗ admin-базы, тогда как Молдова и Румыния собраны с ней
# (`admin = .../admins.sqlite`, timezone не задан ни там, ни там). Из-за этого Odin группировал
# манёвры по-разному, и сравнивать их было бессмысленно: 324 манёвра против 35 на одном маршруте.
# Для честного сравнения admin-база строится по ОБОИМ pbf сразу.
set -eu
W=/regions/mono
docker exec vhdev bash -c "rm -rf $W && mkdir -p $W/tiles"

docker exec vhdev bash -c "cat > $W/valhalla.json <<'JSON'
{\"mjolnir\":{
  \"tile_dir\":\"$W/tiles\",
  \"admin\":\"$W/admins.sqlite\",
  \"concurrency\":22,
  \"logging\":{\"type\":\"\"}
}}
JSON
echo '=== admin-база по обоим pbf'
cd $W && time valhalla_build_admins -c valhalla.json \
  /regions/src/moldova.osm.pbf /regions/src/romania.osm.pbf > $W/admin.log 2>&1
ls -la $W/admins.sqlite"

docker exec vhdev bash -c "
echo '=== тайлы'
cd $W && time valhalla_build_tiles -c valhalla.json \
  /regions/src/moldova.osm.pbf /regions/src/romania.osm.pbf > $W/build.log 2>&1
echo BUILD_DONE
find $W/tiles -name '*.gph' | wc -l
du -sh $W/tiles"

# Проверка, что admin действительно попал в тайлы: у пограничного тайла должны быть ОБЕ страны.
docker exec vhdev /tmp/check_admin $W/tiles 2>&1 | head -10
