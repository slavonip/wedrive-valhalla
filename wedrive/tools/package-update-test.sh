#!/usr/bin/env bash
# Асинхронное обновление одной страны: то, ради чего вся многорегиональность и затевалась.
#
# Проверяется утверждение, которое нельзя получить ни из одного маршрутного теста:
#
#     пересобрать ОДНУ страну из свежего OSM, не трогая соседей, и продолжать маршрутизировать
#
# Сценарий:
#   1. запомнить контрольные суммы тайлов всех стран
#   2. подменить тайлы ОДНОЙ страны на свежую сборку
#   3. перегенерировать таблицы порталов ТОЛЬКО её границ
#   4. убедиться, что тайлы соседей побайтово те же
#   5. прогнать те же маршруты и сравнить с эталоном до обновления
#
# Что обязано обновиться вместе с тайлами — таблицы порталов обеих границ страны.
# Идентификаторы внутри пересобранного графа другие: в измерении на Румынии 2026-09-01 ->
# 2026-09-18 сменилось 20 пар из 32. Соседние ГРАФЫ при этом не трогаются вовсе.
#
#   usage: package-update-test.sh <страна> <каталог-свежей-сборки> [конфиг]
#   пример: package-update-test.sh romania_bc /regions/romania_fresh /regions/mrh.json
set -u
COUNTRY=${1:-romania_bc}
FRESH=${2:-/regions/romania_fresh}
CFG=${3:-/regions/mrh.json}
fail=0
note() { printf '%-52s %s\n' "$1" "$2"; [ "$2" = "OK" ] || fail=1; }

sums() { # -> "имя контрольная_сумма" по строке на страну
  docker exec vhdev bash -c 'for d in $(ls -d /regions/*_bc 2>/dev/null); do
    printf "%s %s\n" "$(basename $d)" "$(find $d/tiles -name "*.gph" | sort | xargs md5sum | md5sum | cut -c1-16)"
  done'
}

route_km() { # запрос -> км
  docker exec vhdev valhalla_service "$CFG" route "$1" > /tmp/pu.txt 2>/dev/null
  python3 - /tmp/pu.txt <<'PY'
import json, sys
t = open(sys.argv[1], encoding='utf-8', errors='replace').read()
i = t.find('{"trip"')
print('%.3f' % json.JSONDecoder().raw_decode(t[i:])[0]['trip']['summary']['length'] if i >= 0 else 'ОШИБКА')
PY
}

R() { echo "{\"locations\":[{\"lat\":$1,\"lon\":$2},{\"lat\":$3,\"lon\":$4}],\"costing\":\"auto\"}"; }
declare -a NAMES=("Кишинёв-Будапешт" "Бухарест-Будапешт" "Кишинёв-Яссы" "Яссы-Дебрецен"
                  "Кишинёв-Бухарест" "MD внутри" "HU внутри")
declare -a REQS=("$(R 47.0105 28.8638 47.4979 19.0402)" "$(R 44.4268 26.1025 47.4979 19.0402)"
                 "$(R 47.0105 28.8638 47.1585 27.6014)" "$(R 47.1585 27.6014 47.5316 21.6273)"
                 "$(R 47.0105 28.8638 44.4268 26.1025)" "$(R 47.0105 28.8638 47.7615 27.9297)"
                 "$(R 47.4979 19.0402 46.2530 20.1414)")

if ! docker exec vhdev test -d "$FRESH/tiles"; then
  echo "нет свежей сборки $FRESH/tiles — тест пропущен"
  exit 0
fi

echo "=== 1. маршруты ДО обновления"
declare -a BEFORE=()
for i in "${!NAMES[@]}"; do
  BEFORE[$i]=$(route_km "${REQS[$i]}")
  printf '   %-24s %s\n' "${NAMES[$i]}" "${BEFORE[$i]}"
done
sums > /tmp/sums_before.txt

echo
echo "=== 2. подменяем ТОЛЬКО $COUNTRY"
docker exec vhdev bash -c "rm -rf /regions/${COUNTRY}_prev && mv /regions/$COUNTRY /regions/${COUNTRY}_prev && cp -r $FRESH /regions/$COUNTRY"

echo "=== 3. перегенерируем порталы границ этой страны"
bash "$(dirname "${BASH_SOURCE[0]}")/regen-portals.sh" >/tmp/regen.log 2>&1 \
  && echo "   $(grep -c . /tmp/regen.log) строк в журнале" || { echo "   регенерация упала"; fail=1; }

echo
echo "=== 4. соседи не тронуты"
sums > /tmp/sums_after.txt
moved=$(join /tmp/sums_before.txt /tmp/sums_after.txt | awk '$2 != $3 {print $1}')
for n in $moved; do echo "   изменился: $n"; done
others=$(echo "$moved" | grep -v "^$COUNTRY$" | grep -c . || true)
note "изменилась только $COUNTRY (прочих: $others)" "$([ "$others" = "0" ] && echo OK || echo ПРОВАЛ)"

echo
echo "=== 5. те же маршруты ПОСЛЕ"
for i in "${!NAMES[@]}"; do
  a=${BEFORE[$i]}; b=$(route_km "${REQS[$i]}")
  if [ "$b" = "ОШИБКА" ]; then
    note "   ${NAMES[$i]}: $a -> НЕТ МАРШРУТА" "ПРОВАЛ"
  else
    d=$(python3 -c "print('%.3f' % abs($a - $b))" 2>/dev/null || echo 999)
    ok=$(python3 -c "import sys; sys.exit(0 if abs($a-$b) <= 1.0 else 1)" && echo OK || echo ПРОВАЛ)
    note "   ${NAMES[$i]}: $a -> $b (+-$d)" "$ok"
  fi
done

echo
[ $fail -eq 0 ] && echo "ОБНОВЛЕНИЕ ОДНОЙ СТРАНЫ ПРОШЛО" || echo "ЕСТЬ ПРОВАЛЫ"
exit $fail
