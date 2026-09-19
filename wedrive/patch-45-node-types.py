"""WeDrive patch 45: какой именно узел берёт 600 и накрыт ли он шорткатом.

Сравнение тайлов уже показало расхождение по месту: пост Леушень 46.79413,28.16196 имеет 4 ребра
в монолите и 2 в каждой одиночной сборке, и обе одиночные сборки накрывают его шорткатом.
CanContract требует РОВНО двух рёбер, и обрез экстракта вдвое уменьшает степень узла, из-за чего
проверка проходит там, где когерентная сборка стяжку запрещает.

Но шорткат на самом пути — id 7257 длиной 2297 из 6 рёбер, а накрывающие Леушень — 19672/19684
длиной 351 из 10. Это разные шорткаты, значит пост на пути может быть и ДРУГИМ. Догадку надо
закрыть измерением.

Здесь в окне вокруг шва печатается узел ПЕРЕД каждым ребром: его тип и координата. Узел, на
котором начисляются 600, обязан оказаться типом kBorderControl, и его координата скажет, тот ли
это пост, который сравнение тайлов уже разобрало.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "            std::cerr << \"    поз=\" << wd_j << \" регион=\" << wd_id.region()\n"
)

NEW = (
    "            // Узел ПЕРЕД ребром: именно на нём начисляется переход.\n"
    "            std::string wd_node = \"-\";\n"
    "            if (wd_j > 0) {\n"
    "              graph_tile_ptr wd_pt;\n"
    "              const auto* wd_pe = graphreader.directededge(path_edges[wd_j - 1], wd_pt);\n"
    "              if (wd_pe) {\n"
    "                graph_tile_ptr wd_nt = wd_pt;\n"
    "                const auto* wd_ni = graphreader.GetEndNode(wd_pe, wd_nt);\n"
    "                if (wd_ni && wd_nt) {\n"
    "                  const auto wd_ll = wd_ni->latlng(wd_nt->header()->base_ll());\n"
    "                  char wd_buf[96];\n"
    "                  std::snprintf(wd_buf, sizeof(wd_buf), \"тип=%d %.5f,%.5f рёбер=%u\",\n"
    "                                static_cast<int>(wd_ni->type()), wd_ll.lat(), wd_ll.lng(),\n"
    "                                wd_ni->edge_count());\n"
    "                  wd_node = wd_buf;\n"
    "                }\n"
    "              }\n"
    "            }\n"
) + OLD

TAIL_OLD = (
    "                      << ((wd_j < path.size()) ? path[wd_j].transition_cost.cost : -1.f)\n"
    "                      << std::endl;\n"
)
TAIL_NEW = (
    "                      << ((wd_j < path.size()) ? path[wd_j].transition_cost.cost : -1.f)\n"
    "                      << \"  узелПеред: \" << wd_node << std::endl;\n"
)

NAME = "Узел ПЕРЕД ребром"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл печать окна"
    assert s.count(TAIL_OLD) == 1, "не нашёл хвост печати"
    s = s.replace(OLD, NEW).replace(TAIL_OLD, TAIL_NEW)
    if "#include <cstdio>" not in s:
        first = s.index("#include")
        s = s[:first] + "#include <cstdio> // WEDRIVE node types\n" + s[first:]
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s тип узла" % ("ok     " if "wd_ni->type()" in s else "MISSING"))
print("      %s печать в окне" % ("ok     " if "узелПеред" in s else "MISSING"))
