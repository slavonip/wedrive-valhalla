#!/usr/bin/env bash
# Работает ли сам стенд на ОДНОМ регионе? Пока эталон красный, сравнивать не с чем.
set -u
MD=/regions/moldova/tiles
echo "=== короткий: внутри Кишинёва"
docker exec vhdev /tmp/thor_route $MD $MD 47.0269 28.8416 47.0105 28.8638 r1
echo
echo "=== средний: Кишинёв -> Унгены (~100 км)"
docker exec vhdev /tmp/thor_route $MD $MD 47.0105 28.8638 47.2075 27.8000 r1
echo
echo "=== длинный: Бельцы -> Кагул (~236 км), это и есть эталон теста 4"
docker exec vhdev /tmp/thor_route $MD $MD 47.7615 27.9297 45.9081 28.1944 r1
