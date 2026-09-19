"""WeDrive patch 66: поднять предел числа регионов вслед за шириной поля.

Патч 65 расширил EdgeLabel::region_ до восьми бит, и первая же попытка собрать таблицу
порталов с номерами 8 и 9 упала:

    WEDRIVE: region id 8 exceeds the 8 that EdgeLabel's 3 spare bits can carry

Это наш собственный страж из AddRegion, и он отработал ровно как задумано: регион 8 в трёх
битах молча стал бы нулём, то есть машина уехала бы в чужую страну. Отказ был громким именно
для этого. Теперь вместе с полем переезжает и его граница.

Предел остаётся ЯВНЫМ и проверяемым, а не исчезает: 255 регионов — это ширина поля метки, и
она по-прежнему меньше восемнадцати бит, которые способен нести GraphId. Ноль сохраняет
прежний смысл «регион не проставлен», поэтому пригодных номеров 255, а не 256.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/baldr/graphreader.h")
s = io.open(P, encoding="utf-8").read()

CAP_OLD = (
    "  /** WEDRIVE: сколько регионов помещается в 3 бита EdgeLabel::region_. */\n"
    "  static constexpr uint32_t kWeDriveMaxRegions = 8;\n"
)
CAP_NEW = (
    "  /** WEDRIVE: сколько регионов помещается в 8 бит EdgeLabel::region_.\n"
    "   *  Ноль означает «регион не проставлен», поэтому пригодных номеров 255. */\n"
    "  static constexpr uint32_t kWeDriveMaxRegions = 256;\n"
)

GUARD_OLD = (
    "    // WEDRIVE region cap: EdgeLabel хранит регион в 3 битах, отнятых у `spare`.\n"
    "    // Регион 8 там молча превратится в 0 и машина уедет в чужую страну, поэтому\n"
    "    // здесь громкий отказ, а не обрезание. Это ограничение ПРОТОТИПА: расширение\n"
    "    // namespace до сотен регионов — отдельная задача, см. MULTI-REGION.md.\n"
    "    if (region >= kWeDriveMaxRegions) {\n"
    "      throw std::runtime_error(\"WEDRIVE: region id \" + std::to_string(region) +\n"
    "                               \" exceeds the \" + std::to_string(kWeDriveMaxRegions) +\n"
    "                               \" that EdgeLabel's 3 spare bits can carry\");\n"
    "    }\n"
)
GUARD_NEW = (
    "    // WEDRIVE region cap: EdgeLabel хранит регион в 8 битах. Номер сверх предела там\n"
    "    // молча обрезался бы, и машина уехала бы в чужую страну, поэтому здесь громкий\n"
    "    // отказ. Ширину поля держат static_assert'ы в edgelabel.h; этот страж — та же\n"
    "    // граница, но во время выполнения, где номера приходят из конфига.\n"
    "    if (region >= kWeDriveMaxRegions) {\n"
    "      throw std::runtime_error(\"WEDRIVE: region id \" + std::to_string(region) +\n"
    "                               \" exceeds the \" + std::to_string(kWeDriveMaxRegions - 1) +\n"
    "                               \" that EdgeLabel's region field can carry\");\n"
    "    }\n"
)

NAME = "8 бит EdgeLabel::region_"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for label, old in (("предел", CAP_OLD), ("страж", GUARD_OLD)):
        assert s.count(old) == 1, "не нашёл якорь: %s" % label
    io.open(P, "w", encoding="utf-8").write(s.replace(CAP_OLD, CAP_NEW).replace(GUARD_OLD, GUARD_NEW))
    print("      +    предел регионов поднят до 255")

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("новый предел", "kWeDriveMaxRegions = 256;", True),
    ("прежнего предела не осталось", "kWeDriveMaxRegions = 8;", False),
    ("страж на месте", "if (region >= kWeDriveMaxRegions) {", True),
    ("упоминания трёх бит убраны", "3 spare bits", False),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
