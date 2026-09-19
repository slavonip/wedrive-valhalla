#!/usr/bin/env bash
# Перегенерация таблиц порталов для набора стран.
#
# Это единственное, что нужно пересчитать при обновлении страны помимо её собственных тайлов:
# идентификаторы внутри пересобранного графа другие, и старая таблица указывает на узлы,
# которых больше нет. Соседние графы при этом не трогаются — меняется только внешняя таблица.
#
# Номера регионов задаются здесь и обязаны совпадать с конфигом: MD=1, RO=2, HU=3. Инструмент
# portal_border принимает их аргументами именно поэтому — зашитые 1/2 пометили бы венгерские
# узлы румынским namespace.
#
# Границы перечислены явно: пара каталогов, пара номеров и рамка поиска. Рамка — это не
# география границы, а область, где ИЩУТСЯ совпадающие пограничные узлы; критерий
# принадлежности берётся из admin-данных самих тайлов (см. portal_border.cc).
set -u
OUT=${1:-/regions/portals_3.txt}
BIN=${2:-/tmp/portal_border}

if ! docker exec vhdev test -x "$BIN"; then
  echo "нет $BIN — соберите tools/portal_border.cc" >&2
  exit 2
fi

# граница: имяA имяB регионA регионB minlat minlon maxlat maxlon
BORDERS=(
  "moldova_bc romania_bc 1 2 45.4 26.6 48.3 28.3"
  "romania_bc hungary_bc 2 3 45.5 20.0 48.5 23.2"
)

docker exec vhdev bash -c ": > $OUT"
for b in "${BORDERS[@]}"; do
  set -- $b
  a=$1; bb=$2; ra=$3; rb=$4; s=$5; w=$6; n=$7; e=$8
  if ! docker exec vhdev test -d "/regions/$a/tiles" || ! docker exec vhdev test -d "/regions/$bb/tiles"; then
    echo "   пропуск $a-$bb: нет тайлов"
    continue
  fi
  part="/regions/portals_${a%%_*}_${bb%%_*}.txt"
  docker exec vhdev bash -c ": > $part"
  for lvl in 0 1 2; do
    docker exec vhdev bash -c \
      "$BIN /regions/$a/tiles /regions/$bb/tiles $s $w $n $e $lvl $ra $rb >> $part" 2>&1 \
      | sed 's/^/   /'
  done
  docker exec vhdev bash -c "cat $part >> $OUT"
  echo "   $a-$bb (регионы $ra/$rb): $(docker exec vhdev bash -c "grep -vc '^#' $part") записей"
done
echo "   итого в $OUT: $(docker exec vhdev bash -c "grep -vc '^#' $OUT") записей"
