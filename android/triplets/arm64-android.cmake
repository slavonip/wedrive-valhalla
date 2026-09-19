# Статическая линковка — не предпочтение, а требование: приложение везёт ОДИН .so, и
# зависимости обязаны оказаться внутри него, а не рядом отдельными файлами.
set(VCPKG_TARGET_ARCHITECTURE arm64)
set(VCPKG_CRT_LINKAGE static)
set(VCPKG_LIBRARY_LINKAGE static)
set(VCPKG_CMAKE_SYSTEM_NAME Android)
set(VCPKG_MAKE_BUILD_TRIPLET "--host=aarch64-linux-android")

# УРОВЕНЬ API ЗАДАЁТСЯ ЗДЕСЬ, И ЭТО НЕ ФОРМАЛЬНОСТЬ.
#
# Без него vcpkg собирает зависимости на уровне по умолчанию, а наше дерево — на android-31.
# Clang ниже API 29 использует ЭМУЛИРОВАННЫЙ TLS: `__thread`-переменная становится символом
# `__emutls_v.<имя>`, а выше 29 — настоящим TLS с прямым именем. Разойтись достаточно один раз:
# protobuf собрался с эмуляцией, valhalla без неё, и линковка упала на ЕДИНСТВЕННОМ символе
# `google::protobuf::internal::ThreadSafeArena::thread_cache_` — единственной `__thread`-переменной,
# пересекающей эту границу. Выглядит это как поломка protobuf, а не как расхождение уровней API.
#
# 31 — не выбор, а пол проекта: головное устройство Zeekr это Android 12 (CLAUDE.md §1).
set(VCPKG_CMAKE_CONFIGURE_OPTIONS -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31)
