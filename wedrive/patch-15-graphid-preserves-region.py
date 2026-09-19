"""WeDrive patch 15: set_id и operator+ стирали регион. Это был главный источник потерь.

Backtrace показал, что все потери идут из SetOrigin — а там нет ничего, что мы не пропатчили.
Причина оказалась глубже и общее: два метода самого GraphId пересобирают value из младших битов
и тем самым обнуляют наши верхние.

    set_id      value = (value & 0x1ffffff) | (id << 25)     <- регион стёрт
    operator+   GraphId(tileid(), level(), id() + offset)    <- регион стёрт
    operator++  value += kIdIncrement                        <- регион цел, ничего не нужно

GetOpposingEdgeId заканчивается вызовом set_id, поэтому КАЖДЫЙ противоположный id возвращался
без региона, сколько бы мест выше по стеку мы ни пропатчили. Чинить надо было здесь, а не там,
куда показывал варнинг.

Это ровно тот случай, ради которого стоило поставить backtrace: варнинг честно указывал на
SetOrigin, и там действительно терялось — но причина лежала на два уровня ниже.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/baldr/graphid.h")
s = io.open(P, encoding="utf-8").read()

EDITS = [
    (
        "WEDRIVE set_id keeps region",
        "  void set_id(const uint32_t id) {\n"
        "    value = (value & 0x1ffffff) | (static_cast<uint64_t>(id & 0x1fffff) << 25);\n"
        "  }",
        "  void set_id(const uint32_t id) {\n"
        "    // WEDRIVE set_id keeps region: маска 0x1ffffff оставляет level+tileid и стирает\n"
        "    // всё выше 25-го бита, включая наш регион. GetOpposingEdgeId заканчивается этим\n"
        "    // вызовом, поэтому без правки КАЖДОЕ противоположное ребро теряло namespace.\n"
        "    value = (value & (0x1ffffffULL | kRegionBits)) |\n"
        "            (static_cast<uint64_t>(id & 0x1fffff) << 25);\n"
        "  }",
    ),
    (
        "WEDRIVE operator+ keeps region",
        "  GraphId operator+(uint64_t offset) const {\n"
        "    return GraphId(tileid(), level(), id() + offset);\n"
        "  }",
        "  GraphId operator+(uint64_t offset) const {\n"
        "    // WEDRIVE operator+ keeps region: конструктор из компонентов региона не несёт.\n"
        "    // (operator++ трогать не надо — он прибавляет к value и верхние биты не задевает.)\n"
        "    return GraphId(tileid(), level(), id() + offset).with_region(region());\n"
        "  }",
    ),
]

changed = False
for name, old, new in EDITS:
    if name in s:
        print("      ok   уже применено: %s" % name)
        continue
    n = s.count(old)
    assert n == 1, "ожидал 1 совпадение для %s, нашёл %d" % (name, n)
    s = s.replace(old, new)
    changed = True
    print("      +    %s" % name)
if changed:
    io.open(P, "w", encoding="utf-8").write(s)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
for name, _, _ in EDITS:
    print("      %s %s" % ("ok     " if name in s else "MISSING", name))
print("      %s operator++ оставлен как есть (value += kIdIncrement регион не трогает)"
      % ("ok     " if "value += kIdIncrement;" in s else "MISSING"))
