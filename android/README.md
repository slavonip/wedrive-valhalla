# Сборка движка под Android

Здесь кросс-компилируется тот же самый патченый движок, что и на десктопе, — под arm64-v8a для
машины и x86_64 для эмулятора. Ничего из `src/`, `valhalla/` и `wedrive/` эта папка не меняет:
runtime заморожен на `multi-region-runtime-v2`, а сборка под другую платформу — это конфигурация,
а не правка.

## Почему это вообще нетривиально

**Upstream Valhalla про Android не знает ничего** — ноль упоминаний в её CMake. Поэтому каждую
зависимость приходится давать самим, под чужую ABI, статически.

Спасает то, что мобильному приложению нужен НЕ ВЕСЬ движок. Маршрутизация — это baldr, sif,
thor, odin, meili, loki, tyr. Сборщик тайлов (mjolnir) на телефон не едет и не должен: это уже
измерено и записано в CLAUDE.md §13 — Молдова строилась 146 секунд на 22 десктопных ядрах, и
переносить это на головное устройство бессмысленно. Карты делает GitHub.

Выключение mjolnir убирает самые тяжёлые зависимости разом:

    ENABLE_DATA_TOOLS=OFF   -> нет luajit, geos, libspatialite, sqlite3
    ENABLE_SERVICES=OFF     -> нет zeromq, czmq
    ENABLE_HTTP=OFF         -> нет curl
    ENABLE_TOOLS=OFF        -> нет cxxopts и утилит командной строки

Остаётся protobuf, заголовки boost и то, что лежит в third_party. Это уже подъёмно.

## Откуда взят подход

С `Rallista/valhalla-mobile` (MIT) — того самого проекта, чей AAR приложение использует сегодня
со СТОКОВОЙ Valhalla. Он уже решил задачу vcpkg + NDK-toolchain с собственными triplet'ами, и
переизобретать её было бы тратой времени: §18 CLAUDE.md прямо разрешает заимствовать из
пермиссивных источников с указанием.

Отличие одно и оно принципиальное: у них `src/valhalla` — сабмодуль на upstream, а здесь
собирается ЭТО дерево. Нам нужен патченый движок, иначе весь multi-region остаётся на десктопе.

## Что здесь лежит

    vcpkg.json           зависимости, которые vcpkg соберёт под Android
    triplets/            как именно: статически, под нужную ABI
    CMakeLists.txt       конфигурация движка без mjolnir и сервисов

## Сборка

Требуются `ANDROID_NDK_HOME` и `VCPKG_ROOT`. В CI это делает `.github/workflows/android-ndk.yml`.

    cmake -S android -B build/android-arm64 \
      -DCMAKE_TOOLCHAIN_FILE=$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake \
      -DVCPKG_CHAINLOAD_TOOLCHAIN_FILE=$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake \
      -DVCPKG_OVERLAY_TRIPLETS=android/triplets \
      -DVCPKG_TARGET_TRIPLET=arm64-android \
      -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 \
      -DCMAKE_BUILD_TYPE=Release
    cmake --build build/android-arm64 -j

`ANDROID_PLATFORM=android-31` — не произвольное число: CLAUDE.md называет API 31 полом всего
проекта, потому что головное устройство Zeekr работает на Android 12.
