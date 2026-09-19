"""WeDrive patch 44: окно вокруг шва, ребро за ребром.

Перепись переходов (патч 43) назвала виновника: на прямой половине composite начисляются ДВА
пересечения границы по 600, тогда как монолит на том же маршруте начисляет ОДНО (601.5). И обе
шестисотки composite невидимы поиску — недосчёт прямой половины 1202.84 против 14.27 у монолита.

Остаётся понять механику, а не следствие. Здесь печатается окно рёбер вокруг шва:

    позиция, регион, тайл, id           кто это
    ctry_crossing, use, класс, узел     почему начисляется пересечение границы
    восстановленное внутреннее ребро    почему поиск этого не видит

Ребро, помеченное восстановленным, попало в путь из шортката — его transition поиск не считал
никогда, потому что метка знает только стоимость самого шортката.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

ANCHOR = "        // WEDRIVE transition census: во что recost оценил переходы между рёбрами.\n"

WIN = (
    "        // WEDRIVE seam window: подробности рёбер вокруг смены региона.\n"
    "        {\n"
    "          size_t wd_seam_at = 0;\n"
    "          for (size_t wd_j = 1; wd_j < path_edges.size(); ++wd_j) {\n"
    "            if (path_edges[wd_j].region() != path_edges[wd_j - 1].region()) {\n"
    "              wd_seam_at = wd_j;\n"
    "              break;\n"
    "            }\n"
    "          }\n"
    "          const size_t wd_lo = (wd_seam_at > 8) ? wd_seam_at - 8 : 0;\n"
    "          const size_t wd_hi = std::min(path_edges.size(), wd_seam_at + 9);\n"
    "          std::cerr << \"WEDRIVE WIN шов на позиции \" << wd_seam_at << std::endl;\n"
    "          for (size_t wd_j = wd_lo; wd_j < wd_hi; ++wd_j) {\n"
    "            const auto& wd_id = path_edges[wd_j];\n"
    "            graph_tile_ptr wd_tt;\n"
    "            if (!graphreader.GetGraphTile(wd_id, wd_tt) || !wd_tt) {\n"
    "              continue;\n"
    "            }\n"
    "            const auto* wd_de = wd_tt->directededge(wd_id);\n"
    "            const bool wd_inner = recovered_inner_edges.count(wd_id) > 0;\n"
    "            std::cerr << \"    поз=\" << wd_j << \" регион=\" << wd_id.region()\n"
    "                      << \" тайл=\" << wd_id.tileid() << \" id=\" << wd_id.id()\n"
    "                      << \" length=\" << wd_de->length()\n"
    "                      << \" класс=\" << static_cast<int>(wd_de->classification())\n"
    "                      << \" ctry_crossing=\" << (wd_de->ctry_crossing() ? 1 : 0)\n"
    "                      << \" shortcut=\" << (wd_de->is_shortcut() ? 1 : 0)\n"
    "                      << \" изШортката=\" << (wd_inner ? 1 : 0)\n"
    "                      << \" transition=\"\n"
    "                      << ((wd_j < path.size()) ? path[wd_j].transition_cost.cost : -1.f)\n"
    "                      << std::endl;\n"
    "          }\n"
    "        }\n"
) + ANCHOR

NAME = "WEDRIVE seam window"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(ANCHOR) == 1, "не нашёл якорь transition census"
    io.open(P, "w", encoding="utf-8").write(s.replace(ANCHOR, WIN))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s признак ctry_crossing" % ("ok     " if "ctry_crossing()" in s else "MISSING"))
print("      %s признак восстановленного" % ("ok     " if "recovered_inner_edges.count(wd_id)" in s else "MISSING"))
