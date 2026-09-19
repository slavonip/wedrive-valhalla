#!/usr/bin/env bash
# Финальная матрица по критериям владельца.
set -u
T="docker exec vhdev /tmp/thor_route"
MD=/regions/moldova/tiles
RO=/regions/romania/tiles
A=/regions/split/a/tiles
B=/regions/split/b/tiles
CH="47.0105 28.8638"; IS="47.1585 27.6014"
N="47.7615 27.9297";  S="45.9081 28.1944"
keep() { grep -E 'МАРШРУТ|NO ROUTE|region lost|переход|НЕПРЕРЫВНОСТЬ'; }

# Километровая полоса: она покрывает дорогу, по которой идёт оптимальный маршрут.
: > /tmp/portals_cut.txt
for lvl in 0 1 2; do
  docker exec vhdev /tmp/portal_find "$A" "$B" 46.995 26.0 47.005 30.5 "$lvl" 2>/dev/null \
    >> /tmp/portals_cut.txt
done
docker cp /tmp/portals_cut.txt vhdev:/tmp/ >/dev/null
echo "таблица разреза: $(wc -l < /tmp/portals_cut.txt) записей"

echo
echo "===== 1. stock MD через настоящий Thor (один регион)"
$T $MD $MD $CH "47.2075 27.8000" r1 2>&1 | keep
echo
echo "===== 2. MD+RO, порталы ВЫКЛЮЧЕНЫ -> обязан быть NO ROUTE"
$T $MD $RO $CH $IS both 2>&1 | keep
echo
echo "===== 3. MD+RO + портал: Кишинёв -> Яссы"
$T $MD $RO $CH $IS both+portal 2>&1 | keep
echo
echo "===== 4. MD+RO + портал: Яссы -> Кишинёв (обратное)"
$T $MD $RO $IS $CH both+portal 2>&1 | keep
echo
echo "===== 5. ЭТАЛОН цельная Moldova: Бельцы -> Кагул / обратно"
$T $MD $MD $N $S r1 2>&1 | keep
$T $MD $MD $S $N r1 2>&1 | keep
echo
echo "===== 6. split A+B, порталы ВЫКЛЮЧЕНЫ -> обязан быть NO ROUTE"
$T "$A" "$B" $N $S both 2>&1 | keep
echo
echo "===== 7. split A+B + порталы: Бельцы -> Кагул / обратно"
$T "$A" "$B" $N $S both+portal /tmp/portals_cut.txt 2>&1 | keep
$T "$A" "$B" $S $N both+portal /tmp/portals_cut.txt 2>&1 | keep
