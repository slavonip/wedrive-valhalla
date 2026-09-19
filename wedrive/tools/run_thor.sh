#!/usr/bin/env bash
# Пять обязательных тестов через НАСТОЯЩИЙ Thor + Sif, плюс обратное направление.
set -u
T="docker exec vhdev /tmp/thor_route"
MD=/regions/moldova/tiles
RO=/regions/romania/tiles
A=/regions/split/a/tiles
B=/regions/split/b/tiles

CH="47.0105 28.8638"   # Кишинёв  — только в MD
IS="47.1585 27.6014"   # Яссы     — только в RO
BALTI="47.7615 27.9297"  # Бельцы — только в A
CAHUL="45.9081 28.1944"  # Кагул  — только в B

echo "################ ТЕСТ 2: MD+RO без порталов"
$T $MD $RO $CH $IS both
echo
echo "################ ТЕСТ 3: MD+RO + один портал Leuseni/Albita — Кишинёв → Яссы"
$T $MD $RO $CH $IS both+portal
echo
echo "################ ТЕСТ 6: ОБРАТНОЕ направление — Яссы → Кишинёв"
echo "   (симметрию нельзя считать самоочевидной)"
$T $MD $RO $IS $CH both+portal
echo
echo "################ и обратное БЕЗ портала — должно быть NO ROUTE"
$T $MD $RO $IS $CH both
echo
echo "################ ТЕСТ 3b: MD+RO + полная выведенная таблица"
$T $MD $RO $CH $IS both+portal /tmp/portals_all.txt
echo "   обратно:"
$T $MD $RO $IS $CH both+portal /tmp/portals_all.txt
echo
echo "################ ТЕСТ 4: split Moldova против цельной Moldova"
echo "--- ЭТАЛОН: цельная Moldova, один регион, Бельцы → Кагул"
$T $MD $MD $BALTI $CAHUL r1
echo "--- ЭТАЛОН обратно: Кагул → Бельцы"
$T $MD $MD $CAHUL $BALTI r1
echo "--- A+B без порталов"
$T $A $B $BALTI $CAHUL both
echo "--- A+B с порталами"
$T $A $B $BALTI $CAHUL both+portal /tmp/portals_split.txt
echo "--- A+B с порталами, обратно"
$T $A $B $CAHUL $BALTI both+portal /tmp/portals_split.txt
