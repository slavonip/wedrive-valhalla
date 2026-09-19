# Патченый движок под Android: маршрутизация без сборщика тайлов.
#
# Подход взят с Rallista/valhalla-mobile (MIT) — проекта, чей AAR приложение использует сегодня
# со стоковой Valhalla. Отличие одно и принципиальное: там src/valhalla — сабмодуль на upstream,
# здесь собирается ЭТО дерево, иначе весь multi-region остаётся на десктопе.

cmake_minimum_required(VERSION 3.20)
project(wedrive_valhalla_android CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ── ЧТО ВЫКЛЮЧЕНО И ПОЧЕМУ ───────────────────────────────────────────────────────────────────
#
# Телефону нужна маршрутизация, а не производство карт. Сборщик тайлов измеренно не поместится:
# Молдова строилась 146 секунд на 22 десктопных ядрах с 15 ГБ памяти (CLAUDE.md §13), и это
# небольшая страна. Карты делает GitHub, устройство их скачивает.
#
# Выключение mjolnir убирает luajit, geos, libspatialite и sqlite3 разом — то есть ровно те
# зависимости, кросс-компиляция которых и составляла бы основную работу.
set(ENABLE_DATA_TOOLS      OFF CACHE BOOL "" FORCE)  # mjolnir: сборка тайлов
set(ENABLE_TOOLS           OFF CACHE BOOL "" FORCE)  # утилиты командной строки
set(ENABLE_SERVICES        OFF CACHE BOOL "" FORCE)  # zeromq/czmq: сервисный слой
set(ENABLE_HTTP            OFF CACHE BOOL "" FORCE)  # curl: скачивание тайлов движком
set(ENABLE_PYTHON_BINDINGS OFF CACHE BOOL "" FORCE)
set(ENABLE_NODE_BINDINGS   OFF CACHE BOOL "" FORCE)
set(ENABLE_TESTS           OFF CACHE BOOL "" FORCE)
set(ENABLE_BENCHMARKS      OFF CACHE BOOL "" FORCE)
set(ENABLE_GEOTIFF         OFF CACHE BOOL "" FORCE)  # растровая сериализация изолиний
set(ENABLE_CCACHE          OFF CACHE BOOL "" FORCE)
set(ENABLE_SINGLE_FILES_WERROR OFF CACHE BOOL "" FORCE)

# Библиотека date собирается со своей базой часовых поясов: на Android нет системной tzdata в
# том виде, который она ожидает найти.
set(BUILD_TZ_LIB  ON  CACHE BOOL "" FORCE)
set(MANUAL_TZ_DB  ON  CACHE BOOL "" FORCE)
set(USE_SYSTEM_TZ_DB OFF CACHE BOOL "" FORCE)

# Модули собираются статически, чтобы всё уехало внутрь одного .so.
set(ENABLE_STATIC_LIBRARY_MODULES ON CACHE BOOL "" FORCE)

# ── САМО ДЕРЕВО ──────────────────────────────────────────────────────────────────────────────
get_filename_component(WEDRIVE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
message(STATUS "WeDrive: собираю движок из ${WEDRIVE_ROOT}")
message(STATUS "WeDrive: ABI ${ANDROID_ABI}, платформа ${ANDROID_PLATFORM}")

add_subdirectory("${WEDRIVE_ROOT}" "${CMAKE_BINARY_DIR}/valhalla" EXCLUDE_FROM_ALL)

# ── ОТПЕЧАТОК ДВИЖКА ─────────────────────────────────────────────────────────────────────────
#
# Одна функция, которая отвечает, ЧТО именно собрано. Без неё .so нельзя отличить от стокового
# по поведению — а разница в одной строке Mjolnir и в восьми битах региона, то есть невидима
# снаружи до первого маршрута через границу.
add_library(wedrive_valhalla SHARED "${CMAKE_CURRENT_SOURCE_DIR}/wedrive_jni.cc")
target_link_libraries(wedrive_valhalla PRIVATE valhalla)
target_include_directories(wedrive_valhalla PRIVATE
  "${WEDRIVE_ROOT}" "${WEDRIVE_ROOT}/valhalla" "${WEDRIVE_ROOT}/third_party/date/include")
set_target_properties(wedrive_valhalla PROPERTIES OUTPUT_NAME "wedrive_valhalla")

# Ссылки на символы, которые обязаны попасть в .so целиком: линкер иначе выбросит модули,
# на которые нет прямой ссылки из обёртки, и библиотека соберётся пустой.
if(ANDROID)
  target_link_options(wedrive_valhalla PRIVATE
    "-Wl,--whole-archive" "$<TARGET_FILE:valhalla>" "-Wl,--no-whole-archive")
endif()

install(TARGETS wedrive_valhalla LIBRARY DESTINATION lib)
