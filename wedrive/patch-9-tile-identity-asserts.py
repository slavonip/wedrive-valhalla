"""WeDrive patch 9: ассерты принадлежности тайлу становятся детектором межрегиональной путаницы.

GraphTile уже проверяет, что спрошенный id принадлежит этому тайлу:

    assert(node.tile_base() == header_->graphid().tile_base());

Слева наш tile_base() сохраняет регион, справа заголовок тайла региона не знает и знать не может —
его писал Mjolnir, для которого регион не существует. Поэтому проверка падала на совершенно
законном обращении.

Чинится сравнением с НАШИМ id(), и от этого ассерт становится строго сильнее: теперь он падает,
если у тайла региона 1 спросить узел региона 2 — то есть ровно на той тихой ошибке, ради которой
всё это затевалось. Бесплатный fail-fast из уже написанной Valhalla проверки.

Важное ограничение: ассерты живут только там, где не задан NDEBUG. Сама libvalhalla собрана в
Release, так что внутри неё они выключены — поэтому счётчик WeDriveRegionLost() в GetGraphTile
остаётся вторым, всегда работающим уровнем защиты.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/baldr/graphtile.h")

s = io.open(P, encoding="utf-8").read()

OLD = ".tile_base() == header_->graphid().tile_base()"
NEW = ".tile_base() == id().tile_base()"

if "WEDRIVE tile identity asserts" in s:
    print("      ok   уже применено: WEDRIVE tile identity asserts")
else:
    n = s.count(OLD)
    assert n == 4, "ожидал 4 ассерта принадлежности тайлу, нашёл %d" % n
    s = s.replace(OLD, NEW)
    # Маркер ставим у объявления id(), где он не может столкнуться с другим маркером.
    anchor = "  /** WEDRIVE: which independently built region this tile was loaded for. */"
    assert s.count(anchor) == 1
    s = s.replace(
        anchor,
        "  // WEDRIVE tile identity asserts: четыре проверки принадлежности id этому тайлу\n"
        "  // сравниваются с id(), а не с заголовком, потому что заголовок региона не содержит.\n"
        "  // Побочный и главный эффект: они теперь ловят обращение к узлу ЧУЖОГО региона.\n"
        + anchor,
    )
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    WEDRIVE tile identity asserts (%d ассерта)" % n)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер на месте" % ("ok     " if "WEDRIVE tile identity asserts" in s else "MISSING"))
print("      %s не осталось сравнений с header_->graphid().tile_base()"
      % ("ok     " if OLD not in s else "MISSING"))
print("      %d ассерта теперь сравниваются с id()" % s.count(NEW))
