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
for p in $(ls "$HERE"/patch-*.py | sort -t- -k2 -n); do
  name="$(basename "$p")"
  echo
  echo "--- $name"
  # Патчи 1-5 писались с SRC = ~/vhbuild/src, патчи 6+ с /src/valhalla. Нормализуем оба варианта
  # во временной копии, чтобы не редактировать сам патч.
  tmp="/tmp/$name"
  sed -e "s#os.path.expanduser(\"~/vhbuild/src\")#\"$SRC\"#" \
      -e "s#^SRC = \"/src/valhalla\"#SRC = \"$SRC\"#" "$p" > "$tmp"
  python3 "$tmp" || { echo "   !! $name завершился с ошибкой"; fail=1; }
done

echo
echo "=== маркеры WEDRIVE по файлам (ноль где-либо = патч не лёг)"
for f in valhalla/baldr/nodeinfo.h valhalla/baldr/graphid.h valhalla/baldr/graphtile.h valhalla/baldr/graphreader.h \
         valhalla/sif/edgelabel.h valhalla/thor/pathalgorithm.h valhalla/thor/edgestatus.h \
         src/baldr/graphtile.cc src/baldr/graphreader.cc src/sif/recost.cc \
         src/thor/bidirectional_astar.cc src/thor/map_matcher.cc \
         src/loki/trace_route_action.cc valhalla/meili/candidate_search.h \
         src/meili/candidate_search.cc src/meili/map_matcher.cc src/meili/routing.cc; do
  printf '   %-42s %s\n' "$f" "$(grep -c WEDRIVE "$SRC/$f" 2>/dev/null || echo '-')"
done

exit $fail
