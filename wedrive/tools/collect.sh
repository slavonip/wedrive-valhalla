#!/usr/bin/env bash
# ИСТОРИЧЕСКИЙ. Собирал всё, что делает multi-region воспроизводимым, из контейнера и домашнего
# каталога WSL в один промежуточный каталог, откуда это забирала Windows-сторона.
#
# ЭТОТ ШАГ БОЛЬШЕ НЕ НУЖЕН, и стоит сказать почему, а не просто удалить. Скрипт существовал
# ровно потому, что патчи и стенды жили в /tmp внутри контейнера, то есть нигде: пересоздай
# контейнер — и работы нет. Он вытаскивал их наружу руками, по списку имён, который надо было
# помнить и обновлять.
#
# Теперь канон — сам репозиторий: патчи лежат в wedrive/, стенды в wedrive/tools/, а
# verify-from-clone.sh доказывает, что из чистого клона всё воспроизводится одним прогоном. То
# есть вопрос «а всё ли мы вынесли из контейнера» получил механический ответ вместо списка,
# который легко забыть дополнить — и именно так однажды и вышло: список внизу перечисляет пять
# исходников, тогда как стендов давно больше.
#
# Оставлен как запись о том, чем это было до репозитория. Работать он всё ещё будет, но его
# результат — подмножество того, что и так лежит в git.
set -u
OUT=/tmp/wv-stage
rm -rf "$OUT"; mkdir -p "$OUT/patches" "$OUT/tools"

echo "=== патчи внутри контейнера"
for f in $(docker exec vhdev bash -c 'ls /tmp/*.py 2>/dev/null'); do
  b=$(basename "$f")
  docker cp "vhdev:$f" "$OUT/patches/$b" 2>/dev/null && echo "   взято $b"
done

echo
echo "=== исходники стендов внутри контейнера"
for f in compose_route.cc portal_find.cc portal_probe.cc wedrive_regions_test.cc t_flat.cc; do
  docker cp "vhdev:/tmp/$f" "$OUT/tools/$f" 2>/dev/null && echo "   взято $f"
done

echo
echo "=== фактический diff, который дали патчи, прямо из собранного дерева"
docker exec vhdev bash -c 'cd /src/valhalla && git diff -- valhalla/baldr/graphid.h \
  valhalla/baldr/graphreader.h valhalla/baldr/graphtile.h src/baldr/graphreader.cc \
  src/baldr/graphtile.cc' > "$OUT/wedrive-runtime.patch"
echo "   wedrive-runtime.patch: $(wc -l < "$OUT/wedrive-runtime.patch") строк"

echo
echo "=== собрано"
find "$OUT" -type f | sed "s|$OUT/|   |"
