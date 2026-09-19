#!/usr/bin/env bash
# Полная таблица — ровно тот случай, который падал на recost.
set -u
L="docker exec vhdev /tmp/loki_route"
T="docker exec vhdev /tmp/thor_route"
MD=/regions/moldova/tiles
RO=/regions/romania/tiles
A=/regions/split/a/tiles
B=/regions/split/b/tiles
keep() { grep -E 'порталов|МАРШРУТ|NO ROUTE|region lost|recost|out of bounds'; }

echo "########## Loki+Thor, MD->RO, ПОЛНАЯ таблица 12508"
$L $MD $RO 47.0105 28.8638 47.1585 27.6014 /tmp/portals_all.txt 2>&1 | keep
echo
echo "########## обратное, полная таблица"
$L $MD $RO 47.1585 27.6014 47.0105 28.8638 /tmp/portals_all.txt 2>&1 | keep
echo
echo "########## Кишинёв -> Бухарест, полная таблица"
$L $MD $RO 47.0105 28.8638 44.4268 26.1025 /tmp/portals_all.txt 2>&1 | keep
echo
echo "########## split A+B, ПРАВИЛЬНАЯ таблица зоны перекрытия 235022 (худший случай)"
$T $A $B 47.7615 27.9297 45.9081 28.1944 both+portal /tmp/portals_split.txt 2>&1 | keep
echo
echo "########## split A+B, ЧУЖАЯ таблица (id из MD/RO) — проверка поведения на мусоре"
$T $A $B 47.7615 27.9297 45.9081 28.1944 both+portal /tmp/portals_all.txt 2>&1 | keep
echo
echo "########## split A+B, production-таблица разреза"
$T $A $B 47.7615 27.9297 45.9081 28.1944 both+portal /tmp/portals_cut.txt 2>&1 | keep
echo "   обратно:"
$T $A $B 45.9081 28.1944 47.7615 27.9297 both+portal /tmp/portals_cut.txt 2>&1 | keep
echo
echo "########## ЭТАЛОН цельная Moldova"
$T $MD $MD 47.7615 27.9297 45.9081 28.1944 r1 2>&1 | keep
$T $MD $MD 45.9081 28.1944 47.7615 27.9297 r1 2>&1 | keep
