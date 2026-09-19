#!/usr/bin/env bash
# Применяет ВСЕ патчи WeDrive к дереву Valhalla по порядку номеров.
#
# Предыдущая версия этого скрипта ссылалась на каталог конкретной сессии и в другой сессии просто
# не находила файлов. Здесь патчи берутся из каталога рядом со скриптом, а дерево Valhalla
# указывается аргументом — так он работает и в контейнере, и на хосте.
#
# Каждый патч идемпотентен и сам проверяет свои куски по уникальным маркерам, поэтому повторный
# запуск безопасен. Порядок важен: patch-15 (GraphId сохраняет регион) должен лечь до того, как
# что-либо начнёт полагаться на арифметику id.
#
#   usage: apply-patches.sh [путь-к-дереву-valhalla]     (по умолчанию /src/valhalla)
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${1:-/src/valhalla}"

if [ ! -d "$SRC/valhalla/baldr" ]; then
  echo "!! $SRC не похож на дерево Valhalla" >&2
  exit 2
fi

echo "=== применяю патчи к $SRC"
fail=0
# Сортировка ИМЕНИ ФАЙЛА, а не полного пути. `sort -t- -k2 -n` по пути берёт вторым полем
# кусок каталога, если в каталоге есть дефис: для /tmp/wedrive-verify/patch-9-... поле 2 —
# это "verify/patch", а не "9". Числовой ключ вырождается, sort падает на лексикографику,
# и patch-10 применяется РАНЬШЕ patch-9. Первый прогон тогда теряет патчи 10, 14, 19 и 21,
# второй их дотягивает — то есть скрипт был не идемпотентен и зависел от имени каталога,
# в который его скопировали.
for name in $(ls "$HERE" | grep -E '^patch-[0-9]+-.*\.py$' | sort -t- -k2 -n); do
  p="$HERE/$name"
  echo
  echo "--- $name"
  # Патчи 1-5 писались с SRC = ~/vhbuild/src, патчи 6+ с /src/valhalla. Нормализуем оба варианта
  # во временной копии, чтобы не редактировать сам патч.
  tmp="/tmp/$name"
  sed -e "s#os.path.expanduser(\"~/vhbuild/src\")#\"$SRC\"#" \
      -e "s#^SRC = \"/src/valhalla\"#SRC = \"$SRC\"#" "$p" > "$tmp"
  # ПОДСТАНОВКА ПРОВЕРЯЕТСЯ, а не предполагается. patch-32-fix-reverse-side объявлял путь одной
  # строкой вместе с именем файла (`SRC = "/src/valhalla/src/thor/..."`), и шаблон выше, который
  # требует закрывающую кавычку сразу после valhalla, по нему не срабатывал. Патч уходил править
  # НАСТОЯЩИЙ /src/valhalla, находил там свою работу с прошлого раза, печатал «уже исправлено» и
  # выходил с кодом 0 — а целевое дерево оставалось недоправленным, и тринадцать патчей после него
  # падали на «ожидал 1 совпадение, нашёл 2». В контейнере, где дерево и есть /src/valhalla, это
  # было не видно вовсе; ловилось только в CI и в свежем клоне.
  if [ "$SRC" != "/src/valhalla" ] && grep -qE '^ *(SRC|P) *= *"/src/valhalla' "$tmp"; then
    echo "   !! $name не принял подстановку пути, объявление осталось прежним:" >&2
    grep -nE '^ *(SRC|P) *= *"/src/valhalla' "$tmp" | head -3 | sed 's/^/      /' >&2
    fail=1
    continue
  fi
  python3 "$tmp" || { echo "   !! $name завершился с ошибкой"; fail=1; }
done

echo
echo "=== маркеры WEDRIVE по файлам (ноль где-либо = патч не лёг)"
for f in valhalla/baldr/nodeinfo.h valhalla/baldr/graphid.h valhalla/baldr/graphtile.h valhalla/baldr/graphreader.h \
         valhalla/sif/edgelabel.h valhalla/thor/pathalgorithm.h valhalla/thor/edgestatus.h \
         src/baldr/graphtile.cc src/baldr/graphreader.cc src/sif/recost.cc \
         src/thor/bidirectional_astar.cc src/thor/map_matcher.cc \
         src/loki/trace_route_action.cc valhalla/meili/candidate_search.h \
         src/meili/candidate_search.cc src/meili/map_matcher.cc src/meili/routing.cc \
         valhalla/loki/search.h src/loki/route_action.cc src/loki/matrix_action.cc \
         src/loki/isochrone_action.cc src/loki/locate_action.cc src/loki/worker.cc \
         valhalla/thor/dijkstras.h src/thor/dijkstras.cc src/thor/costmatrix.cc; do
  printf '   %-42s %s\n' "$f" "$(grep -c WEDRIVE "$SRC/$f" 2>/dev/null || echo '-')"
done

exit $fail
