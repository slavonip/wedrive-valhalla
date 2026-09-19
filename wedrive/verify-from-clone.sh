#!/usr/bin/env bash
# Доказывает утверждение, которое сильнее, чем «наше дерево работает»:
#
#     git clone -> скрипты ИЗ репозитория -> сборка -> тесты = рабочий multi-region Valhalla
#
# Пока это не проверено, всегда остаётся шанс, что сборка держится на чём-то, что лежит только
# на машине разработчика и никуда не закоммичено.
#
#   usage: verify-from-clone.sh [путь-к-дереву-valhalla]     (по умолчанию /src/valhalla)
#
# Запускать ИЗ свежего клона. Требует контейнер vhdev с зависимостями Valhalla и смонтированными
# тайлами в /regions.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${1:-/src/valhalla}"
fail=0
note() { printf '%-46s %s\n' "$1" "$2"; [ "$2" = "OK" ] || fail=1; }

echo "=== 1. дерево Valhalla возвращается к стоковому"
docker exec vhdev bash -c "cd $SRC && git checkout -- \
  valhalla/baldr/graphid.h valhalla/baldr/graphtile.h valhalla/baldr/graphreader.h \
  valhalla/sif/edgelabel.h valhalla/thor/pathalgorithm.h valhalla/thor/edgestatus.h \
  src/baldr/graphtile.cc src/baldr/graphreader.cc src/sif/recost.cc \
  src/thor/bidirectional_astar.cc"
left=$(docker exec vhdev bash -c "grep -c WEDRIVE $SRC/valhalla/baldr/graphid.h || true")
note "маркеров WEDRIVE после отката: $left" "$([ "$left" = "0" ] && echo OK || echo ПРОВАЛ)"

echo
echo "=== 2. патчи из репозитория"
docker exec vhdev rm -rf /tmp/wedrive-verify
docker cp "$HERE" vhdev:/tmp/wedrive-verify >/dev/null
docker exec vhdev bash -c "bash /tmp/wedrive-verify/apply-patches.sh $SRC" >/tmp/apply.log 2>&1
note "apply-patches.sh" "$(grep -q 'MISSING' /tmp/apply.log && echo ПРОВАЛ || echo OK)"

echo
echo "=== 3. идемпотентность: второй прогон ничего не меняет"
sum1=$(docker exec vhdev bash -c "cat $SRC/valhalla/baldr/graphid.h $SRC/valhalla/thor/edgestatus.h | md5sum")
docker exec vhdev bash -c "bash /tmp/wedrive-verify/apply-patches.sh $SRC" >/dev/null 2>&1
sum2=$(docker exec vhdev bash -c "cat $SRC/valhalla/baldr/graphid.h $SRC/valhalla/thor/edgestatus.h | md5sum")
note "дерево не изменилось" "$([ "$sum1" = "$sum2" ] && echo OK || echo ПРОВАЛ)"

echo
echo "=== 4. сборка"
errs=$(docker exec vhdev bash -c "make -C $SRC/build -j\$(nproc) 2>&1 | grep -cE 'error:'")
note "ошибок компиляции: $errs" "$([ "$errs" = "0" ] && echo OK || echo ПРОВАЛ)"
docker exec vhdev bash -c "make -C $SRC/build install >/dev/null 2>&1"

echo
echo "=== 5. инструменты собираются"
# Без `| head`: обрыв пайпа шлёт g++ SIGPIPE, и сборка выглядит упавшей, хотя дело в тесте.
docker exec vhdev bash -c 'cd /tmp/wedrive-verify/tools && for t in gid_test portal_find portal_cut compose_route; do
    g++ -std=c++20 -O2 $t.cc -o /tmp/$t $(pkg-config --cflags --libs libvalhalla) >/dev/null 2>&1
  done
  g++ -std=c++20 -O2 -g -rdynamic thor_route.cc -o /tmp/thor_route \
      $(pkg-config --cflags --libs libvalhalla) -lprotobuf >/dev/null 2>&1'
for t in gid_test portal_find portal_cut compose_route thor_route; do
  note "  $t" "$(docker exec vhdev test -x /tmp/$t && echo OK || echo ПРОВАЛ)"
done

echo
echo "=== 6. инвариант GraphId"
note "gid_test" "$(docker exec vhdev /tmp/gid_test >/dev/null 2>&1 && echo OK || echo ПРОВАЛ)"

echo
echo "=== 7. регрессия против stock upstream 3.6.3"
bash "$HERE/tools/regress.sh" > /tmp/regress.log 2>&1
p=$(grep -A4 'patched' /tmp/regress.log | grep -oE '[0-9]+\.[0-9]+ km' | head -3 | tr '\n' ' ')
s=$(grep -A4 'stock upstream' /tmp/regress.log | grep -oE '[0-9]+\.[0-9]+ km' | head -3 | tr '\n' ' ')
echo "   патч:  $p"
echo "   сток:  $s"
note "ответы совпадают" "$([ "$p" = "$s" ] && [ -n "$p" ] && echo OK || echo ПРОВАЛ)"

echo
echo "=== 8. multi-region matrix"
bash "$HERE/tools/final.sh" > /tmp/matrix.log 2>&1
routes=$(grep -cE '^МАРШРУТ НАЙДЕН' /tmp/matrix.log)
# ^NO ROUTE, иначе считаются и заголовки вида «обязан быть NO ROUTE».
noroute=$(grep -cE '^NO ROUTE' /tmp/matrix.log)
lost=$(grep -c 'region lost: [1-9]' /tmp/matrix.log)
gaps=$(grep -c 'РАЗРЫВ' /tmp/matrix.log)
note "маршрутов найдено: $routes (ожидается 7)" "$([ "$routes" = "7" ] && echo OK || echo ПРОВАЛ)"
note "NO ROUTE без порталов: $noroute (ожидается 2)" "$([ "$noroute" = "2" ] && echo OK || echo ПРОВАЛ)"
note "прогонов с потерей региона: $lost" "$([ "$lost" = "0" ] && echo OK || echo ПРОВАЛ)"
note "разрывов геометрии: $gaps" "$([ "$gaps" = "0" ] && echo OK || echo ПРОВАЛ)"

echo
[ $fail -eq 0 ] && echo "ВСЁ ЗЕЛЁНОЕ — репозиторий самодостаточен" \
                || echo "ЕСТЬ ПРОВАЛЫ — см. /tmp/apply.log /tmp/regress.log /tmp/matrix.log"
exit $fail
