"""WeDrive patch 54: сколько кандидатов даёт каждый регион.

Расширение внутри Meili так и не встретило ни одного портального узла: 121339 запросов, ноль
непустых, и ноль даже при принудительной подстановке чужого тега. Значит поиск физически не
доходит до тех 32 узлов, а не промахивается ключом.

При этом узлов региона 2 в гистограмме всего 58 против 79358 у региона 1. Похоже, что multiplex
румынских кандидатов почти не даёт, и тогда искать маршрут в Румынию попросту незачем: нет
состояния — нет и перехода к нему.

Перепись считает ровно это: сколько PathLocation и сколько рёбер в них вернул каждый регион, и
сколько рёбер пришло с каким тегом. Если регион 2 отдаёт нули, дело в поиске кандидатов, а не в
порталах и не в расширении.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/map_matcher.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "      for (auto& pl : found) {\n"
    "        merged.push_back(std::move(pl));\n"
    "      }\n"
)

NEW = (
    "      wedrive_cand_locs[region & 7] += found.size();\n"
    "      for (auto& pl : found) {\n"
    "        for (const auto& e : pl.edges) {\n"
    "          wedrive_cand_edges[e.id.region() & 7] += 1;\n"
    "        }\n"
    "        merged.push_back(std::move(pl));\n"
    "      }\n"
)

# Стоковая ветка считается тоже — иначе сравнить одно-региональный прогон не с чем.
STOCK_OLD = (
    "    if (graphreader_.RegionCount() < 2) {\n"
    "      return candidatequery_.Query(measurement.lnglat(), measurement.stop_type(), sq_radius,\n"
    "                                   costing());\n"
    "    }\n"
)
STOCK_NEW = (
    "    if (graphreader_.RegionCount() < 2) {\n"
    "      auto wd_one = candidatequery_.Query(measurement.lnglat(), measurement.stop_type(),\n"
    "                                          sq_radius, costing());\n"
    "      wedrive_cand_locs[0] += wd_one.size();\n"
    "      return wd_one;\n"
    "    }\n"
)

COUNTERS = (
    "// WEDRIVE meili candidate census: кандидаты по регионам — по запросу и по тегу ребра.\n"
    "std::atomic<size_t> wedrive_cand_locs[8];\n"
    "std::atomic<size_t> wedrive_cand_edges[8];\n"
    "namespace {\n"
    "struct WeDriveCandReport {\n"
    "  ~WeDriveCandReport() {\n"
    '    if (std::getenv("WEDRIVE_DEBUG_BIDIR")) {\n'
    '      std::cerr << "WEDRIVE MEILI кандидаты по региону запроса:";\n'
    "      for (uint32_t r = 0; r < 8; ++r) {\n"
    "        if (wedrive_cand_locs[r]) {\n"
    '          std::cerr << "  " << r << "=" << wedrive_cand_locs[r];\n'
    "        }\n"
    "      }\n"
    '      std::cerr << "\\nWEDRIVE MEILI рёбра кандидатов по тегу:";\n'
    "      for (uint32_t r = 0; r < 8; ++r) {\n"
    "        if (wedrive_cand_edges[r]) {\n"
    '          std::cerr << "  " << r << "=" << wedrive_cand_edges[r];\n'
    "        }\n"
    "      }\n"
    "      std::cerr << std::endl;\n"
    "    }\n"
    "  }\n"
    "};\n"
    "WeDriveCandReport wedrive_cand_report;\n"
    "} // namespace\n"
)

NAME = "WEDRIVE meili candidate census"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл слияние кандидатов"
    assert s.count(STOCK_OLD) == 1, "не нашёл стоковую ветку multiplex'а"
    s = s.replace(OLD, NEW).replace(STOCK_OLD, STOCK_NEW)
    inc = ("#include <atomic>   // WEDRIVE meili candidate census\n"
           "#include <cstdlib>  // WEDRIVE meili candidate census\n"
           "#include <iostream> // WEDRIVE meili candidate census\n")
    first = s.index("#include")
    s = s[:first] + inc + s[first:]
    anchor = "namespace valhalla {"
    assert s.count(anchor) >= 1, "не нашёл namespace valhalla"
    at = s.index(anchor)
    s = s[:at] + COUNTERS + "\n" + s[at:]
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("счётчики", "std::atomic<size_t> wedrive_cand_locs[8];", True),
    ("учёт по запросу", "wedrive_cand_locs[region & 7] += found.size();", True),
    ("учёт по тегу ребра", "wedrive_cand_edges[e.id.region() & 7] += 1;", True),
    ("отчёт", "кандидаты по региону запроса", True),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
