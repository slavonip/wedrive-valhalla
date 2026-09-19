#!/usr/bin/env bash
# Стеки оставшихся потерь, по одному характерному случаю каждого вида.
set -u
T="docker exec vhdev /tmp/thor_route"
MD=/regions/moldova/tiles
RO=/regions/romania/tiles
A=/regions/split/a/tiles
B=/regions/split/b/tiles

demangle() { sed -E 's/.*\((_Z[A-Za-z0-9_]+)\+0x[0-9a-f]+\).*/\1/' | while read -r s; do
  case "$s" in _Z*) c++filt "$s" | cut -c1-110 ;; *) echo "      $s" ;; esac
done; }

echo "########## MD+RO прямое (level 0)"
$T $MD $RO 47.0105 28.8638 47.1585 27.6014 both 2>&1 | grep -A 6 'REGION LOST #0' | demangle
echo
echo "########## MD+RO обратное (44348 потерь)"
$T $MD $RO 47.1585 27.6014 47.0105 28.8638 both 2>&1 | grep -A 6 'REGION LOST #0' | demangle
echo
echo "########## split A+B прямое (3 потери)"
$T $A $B 47.7615 27.9297 45.9081 28.1944 both 2>&1 | grep -A 6 'REGION LOST #0' | demangle
