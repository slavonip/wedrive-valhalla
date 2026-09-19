"""WeDrive patch 49: какой регион несут узлы внутри Meili.

Зонд патча 48 дал однозначное: блок порталов исполняется 37407 раз и КАЖДЫЙ раз PortalsAt
возвращает пусто. Таблица при этом заведомо не пуста — на ней работают Thor и все маршруты.

Значит не совпадает ключ. Порталы лежат по полному тегированному GraphId, а узлы внутри Meili
могут быть без региона: у Meili свой поиск кандидатов в candidate_search.cc, и multiplex по
регионам, сделанный для loki::Search, его не касался.

Гистограмма по region у спрошенных узлов отвечает на это прямо. Плюс контрольная проба: если тот
же узел, принудительно помеченный регионом 1 или 2, в таблице НАХОДИТСЯ, значит дело
исключительно в теге, а не в самой таблице.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/routing.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "      ++wedrive_meili_asked;\n"
    "      if (const auto* portals = reader.PortalsAt(node)) {\n"
)

NEW = (
    "      ++wedrive_meili_asked;\n"
    "      if (node.region() < 8) {\n"
    "        ++wedrive_meili_by_region[node.region()];\n"
    "      }\n"
    "      // Контроль: нашёлся бы этот узел, будь он помечен регионом 1 или 2.\n"
    "      for (uint32_t wd_r = 1; wd_r <= 2; ++wd_r) {\n"
    "        if (node.region() != wd_r && reader.PortalsAt(node.with_region(wd_r))) {\n"
    "          ++wedrive_meili_would_hit;\n"
    "        }\n"
    "      }\n"
    "      if (const auto* portals = reader.PortalsAt(node)) {\n"
)

CNT_OLD = "std::atomic<size_t> wedrive_meili_portal_total{0};\n"
CNT_NEW = (
    "std::atomic<size_t> wedrive_meili_would_hit{0};\n"
    "std::atomic<size_t> wedrive_meili_by_region[8];\n"
)

REP_OLD = (
    '                << wedrive_meili_hops << "  порталов в таблице "\n'
    "                << wedrive_meili_portal_total << std::endl;\n"
)
REP_NEW = (
    "                << wedrive_meili_hops\n"
    '                << "  нашлось бы с чужим тегом " << wedrive_meili_would_hit << std::endl;\n'
    '      std::cerr << "WEDRIVE MEILI регионы спрошенных узлов:";\n'
    "      for (uint32_t wd_r = 0; wd_r < 8; ++wd_r) {\n"
    "        if (wedrive_meili_by_region[wd_r]) {\n"
    '          std::cerr << "  " << wd_r << "=" << wedrive_meili_by_region[wd_r];\n'
    "        }\n"
    "      }\n"
    "      std::cerr << std::endl;\n"
)

NAME = "WEDRIVE MEILI регионы спрошенных узлов"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for label, old in (("блок", OLD), ("счётчик", CNT_OLD), ("отчёт", REP_OLD)):
        assert s.count(old) == 1, "не нашёл якорь: %s" % label
    s = s.replace(OLD, NEW).replace(CNT_OLD, CNT_NEW).replace(REP_OLD, REP_NEW)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("гистограмма", "wedrive_meili_by_region[node.region()]", True),
    ("контрольная проба", "node.with_region(wd_r)", True),
    ("отчёт", NAME, True),
    ("мёртвый счётчик убран", "wedrive_meili_portal_total", False),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
