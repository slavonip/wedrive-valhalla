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
# Список патчуемых файлов — один на весь скрипт. Файл, забытый здесь, остался бы
# пропатченным во время «проверки из чистого клона», и тест был бы зелёным ровно по той
# причине, которую он обязан исключить.
WEDRIVE_FILES="valhalla/baldr/graphid.h valhalla/baldr/graphtile.h valhalla/baldr/graphreader.h \
  valhalla/baldr/nodeinfo.h valhalla/sif/edgelabel.h valhalla/thor/pathalgorithm.h \
  valhalla/thor/edgestatus.h valhalla/thor/dijkstras.h valhalla/loki/search.h \
  valhalla/meili/candidate_search.h \
  src/baldr/graphtile.cc src/baldr/graphreader.cc src/baldr/shortcut_recovery.h \
  src/sif/recost.cc \
  src/thor/bidirectional_astar.cc src/thor/unidirectional_astar.cc src/thor/triplegbuilder.cc \
  src/thor/map_matcher.cc src/thor/costmatrix.cc src/thor/dijkstras.cc \
  src/meili/candidate_search.cc src/meili/map_matcher.cc src/meili/routing.cc \
  src/loki/route_action.cc src/loki/trace_route_action.cc src/loki/matrix_action.cc \
  src/loki/isochrone_action.cc src/loki/locate_action.cc src/loki/worker.cc"
docker exec vhdev bash -c "cd $SRC && git checkout -- $WEDRIVE_FILES"
left=$(docker exec vhdev bash -c "cd $SRC && grep -l WEDRIVE $WEDRIVE_FILES 2>/dev/null | wc -l")
note "файлов с маркерами после отката: $left" "$([ "$left" = "0" ] && echo OK || echo ПРОВАЛ)"

echo
echo "=== 2. патчи из репозитория"
docker exec vhdev rm -rf /tmp/wedrive-verify
docker cp "$HERE" vhdev:/tmp/wedrive-verify >/dev/null
# Проверяется И код возврата, И маркеры. Раньше искалось только "MISSING", поэтому четыре
# патча, падавшие с AssertionError на первом прогоне, проходили этот шаг зелёными: их
# дотягивал второй прогон в шаге 3.
docker exec vhdev bash -c "bash /tmp/wedrive-verify/apply-patches.sh $SRC" >/tmp/apply.log 2>&1
rc=$?
broke=$(grep -c '!!' /tmp/apply.log || true)
ok2=ПРОВАЛ
if [ "$rc" = "0" ] && [ "$broke" = "0" ] && ! grep -q 'MISSING' /tmp/apply.log; then ok2=OK; fi
note "apply-patches.sh (код $rc, упавших патчей $broke)" "$ok2"

echo
echo "=== 3. идемпотентность: второй прогон ничего не меняет"
sum1=$(docker exec vhdev bash -c "cd $SRC && cat $WEDRIVE_FILES | md5sum")
docker exec vhdev bash -c "bash /tmp/wedrive-verify/apply-patches.sh $SRC" >/dev/null 2>&1
sum2=$(docker exec vhdev bash -c "cd $SRC && cat $WEDRIVE_FILES | md5sum")
note "дерево не изменилось" "$([ "$sum1" = "$sum2" ] && echo OK || echo ПРОВАЛ)"

echo

echo
echo "=== 3b. патчи ложатся на дерево по ДРУГОМУ пути (так работает CI и Android-сборка)"
# Шаги 1-3 применяют патчи к /src/valhalla. Это слепое пятно по построению: патч, в котором путь
# зашит константой, проходит их даром — он правит ровно то дерево, которое проверяется. Именно так
# patch-32-fix-reverse-side полгода выглядел рабочим, объявляя путь одной строкой вместе с именем
# файла: apply-patches.sh подменяет точное `SRC = "/src/valhalla"` с закрывающей кавычкой, по нему
# не срабатывал, патч правил настоящий /src/valhalla, находил там прошлую работу, печатал «уже
# исправлено» и выходил с кодом 0. В контейнере ноль провалов; в CI и в свежем клоне — тринадцать
# диагностических патчей подряд на «ожидал 1 совпадение, нашёл 2».
# Дерево берётся git-worktree, а не копией: это стоковый снимок HEAD по другому пути, без build/
# и без второй копии истории.
docker exec vhdev bash -c "cd $SRC && git worktree remove --force /tmp/otherpath 2>/dev/null; rm -rf /tmp/otherpath; git worktree add --detach -f /tmp/otherpath HEAD >/dev/null 2>&1 && bash /tmp/wedrive-verify/apply-patches.sh /tmp/otherpath" > /tmp/otherpath.log 2>&1
rc=$?
bad=$(grep -c '!!' /tmp/otherpath.log 2>/dev/null || echo 0)
note "apply-patches.sh на чужом пути (код $rc, упавших $bad)" \
     "$([ "$rc" = 0 ] && [ "$bad" = 0 ] && echo OK || echo ПРОВАЛ)"
[ "$bad" != 0 ] && grep '!!' /tmp/otherpath.log | head -5 | sed 's/^/      /'
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
echo "=== 9. полный сервис через границу: композит против монолита"
# Главная приёмка: четыре службы, каждая со своим обходом графа, на одних и тех же парах.
if docker exec vhdev test -f /regions/mono_full.json && docker exec vhdev test -f /regions/mr_bc.json; then
  bash "$HERE/tools/service-regress.sh" > /tmp/service.log 2>&1
  bad=$(grep -c 'РАСХОЖДЕНИЕ' /tmp/service.log || true)
  lost=$(grep -oE 'ПОТЕРЬ РЕГИОНА[^0-9]*[0-9]+' /tmp/service.log | grep -oE '[0-9]+$' || echo 1)
  sed 's/^/   /' /tmp/service.log
  note "расхождений сверх допуска: $bad" "$([ "$bad" = "0" ] && echo OK || echo ПРОВАЛ)"
  note "потерь региона: $lost" "$([ "$lost" = "0" ] && echo OK || echo ПРОВАЛ)"
else
  echo "   пропущено: нет /regions/mono_full.json или /regions/mr_bc.json"
fi

echo
[ $fail -eq 0 ] && echo "ВСЁ ЗЕЛЁНОЕ — репозиторий самодостаточен" \
                || echo "ЕСТЬ ПРОВАЛЫ — см. /tmp/apply.log /tmp/regress.log /tmp/matrix.log"
exit $fail
