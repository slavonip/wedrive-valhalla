#!/usr/bin/env bash
# Порталы ТОЛЬКО по линии разреза, а не по всей 11-километровой полосе перекрытия.
#
# С таблицей на всю полосу путь сменил регион 251 раз и дал 298 км против эталонных 279: портал
# бесплатен, один и тот же физический узел существует в обоих графах, и поиску незачем оставаться
# на месте. Это не дефект рантайма, это неверная модель границы — ровно то, о чём предупреждал
# владелец про 12 508 порталов из перекрытия Geofabrik.
#
# Разрез A|B проходит по 47.00. Берём полосу +-0.0005 градуса (около ста метров).
set -u
A=/regions/split/a/tiles
B=/regions/split/b/tiles

: > /tmp/portals_narrow.txt
for lvl in 0 1 2; do
  docker exec vhdev /tmp/portal_find "$A" "$B" 46.9995 26.0 47.0005 30.5 "$lvl" >> /tmp/portals_narrow.txt
done
echo "   узкая таблица: $(wc -l < /tmp/portals_narrow.txt) записей (было 235022)"
docker cp /tmp/portals_narrow.txt vhdev:/tmp/ >/dev/null

T="docker exec vhdev /tmp/thor_route"
N="47.7615 27.9297"
S="45.9081 28.1944"

echo
echo "########## ЭТАЛОН: цельная Moldova"
$T /regions/moldova/tiles /regions/moldova/tiles $N $S r1 2>&1 | grep -E 'МАРШРУТ|NO ROUTE|region lost'
echo "   обратно:"
$T /regions/moldova/tiles /regions/moldova/tiles $S $N r1 2>&1 | grep -E 'МАРШРУТ|NO ROUTE|region lost'
echo
echo "########## A+B, узкая таблица порталов"
$T "$A" "$B" $N $S both+portal /tmp/portals_narrow.txt 2>&1 | grep -E 'МАРШРУТ|NO ROUTE|region lost'
echo "   обратно:"
$T "$A" "$B" $S $N both+portal /tmp/portals_narrow.txt 2>&1 | grep -E 'МАРШРУТ|NO ROUTE|region lost'
echo
echo "########## A+B БЕЗ порталов — обязан быть NO ROUTE"
$T "$A" "$B" $N $S both 2>&1 | grep -E 'МАРШРУТ|NO ROUTE|region lost'
