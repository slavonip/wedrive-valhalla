"""WeDrive patch 48: доходит ли расширитель Meili до портала вообще.

Патч 47 лёг и собрался, а результат не сдвинулся ни на метр: те же 638 из 770 и те же 126.626 км.
Значит блок либо не исполняется, либо PortalsAt в этом читателе пуст. Гадать не о чем — у Meili
свой MapMatcherFactory, и он вполне может держать СВОЙ GraphReader, в который таблица порталов
не попадала.

Зонд печатает три числа: сколько раз расширитель спросил порталы, сколько раз получил непустой
список и сколько прыжков совершил. Ноль в первом означает, что блок не исполняется; ноль во
втором при ненулевом первом — что читатель другой.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/routing.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "    if (!from_transition) {\n"
    "      if (const auto* portals = reader.PortalsAt(node)) {\n"
    "        for (const auto& portal : *portals) {\n"
    "          expand(portal.to, label_idx, true);\n"
    "        }\n"
    "      }\n"
    "    }\n"
)

NEW = (
    "    if (!from_transition) {\n"
    "      ++wedrive_meili_asked;\n"
    "      if (const auto* portals = reader.PortalsAt(node)) {\n"
    "        ++wedrive_meili_found;\n"
    "        for (const auto& portal : *portals) {\n"
    "          ++wedrive_meili_hops;\n"
    "          expand(portal.to, label_idx, true);\n"
    "        }\n"
    "      }\n"
    "    }\n"
)

COUNTERS = (
    "// WEDRIVE meili probe: счётчики раскрытия порталов в собственном поиске Meili.\n"
    "std::atomic<size_t> wedrive_meili_asked{0};\n"
    "std::atomic<size_t> wedrive_meili_found{0};\n"
    "std::atomic<size_t> wedrive_meili_hops{0};\n"
    "std::atomic<size_t> wedrive_meili_portal_total{0};\n"
    "namespace {\n"
    "struct WeDriveMeiliReport {\n"
    "  ~WeDriveMeiliReport() {\n"
    "    if (std::getenv(\"WEDRIVE_DEBUG_BIDIR\")) {\n"
    "      std::cerr << \"WEDRIVE MEILI: спрошено \" << wedrive_meili_asked\n"
    "                << \"  непустых \" << wedrive_meili_found << \"  прыжков \"\n"
    "                << wedrive_meili_hops << \"  порталов в таблице \"\n"
    "                << wedrive_meili_portal_total << std::endl;\n"
    "    }\n"
    "  }\n"
    "};\n"
    "WeDriveMeiliReport wedrive_meili_report;\n"
    "} // namespace\n"
)

NAME = "WEDRIVE meili probe"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл блок порталов Meili"
    s = s.replace(OLD, NEW)
    # Счётчики кладём сразу после включений, до первого namespace.
    anchor = "namespace valhalla {"
    assert s.count(anchor) >= 1, "не нашёл namespace valhalla"
    inc = "#include <atomic>   // WEDRIVE meili probe\n#include <cstdlib>  // WEDRIVE meili probe\n#include <iostream> // WEDRIVE meili probe\n"
    first = s.index("#include")
    s = s[:first] + inc + s[first:]
    at = s.index(anchor)
    s = s[:at] + COUNTERS + "\n" + s[at:]
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
for label, needle in (("счётчики", "wedrive_meili_asked{0}"),
                      ("инкремент в блоке", "++wedrive_meili_asked;"),
                      ("отчёт", "WEDRIVE MEILI: спрошено")):
    print("      %s %s" % ("ok     " if needle in s else "MISSING", label))
