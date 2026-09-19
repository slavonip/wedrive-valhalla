"""WeDrive patch 40: которая из двух половин занижена.

Бинарный тест патча 39 закрыт: в выигравшем соединении оба дерева держат ОДНО и то же ребро,
и с регионом, и без него (val 140754836021568 / 141974640288056, оба shortcut, оба 27988 м).
Значит region через opp_edgeid протащен верно и представления дороги не разошлись.

Остаётся арифметика склейки:

    c = F + R + correction = 7147.72 + 10765.8 + 3 = 17916.6
    честный recost того же набора рёбер         = 19151

Путь строится из двух цепочек, и место их стыка известно: ровно столько рёбер, сколько набралось
до присоединения обратной части. Разрезаем recost в этой точке и сравниваем каждую половину со
СВОЕЙ меткой:

    forward: edgelabels_forward_[idx1].cost()   против recost до стыка включительно
    reverse: cost предшественника обратной метки против остатка recost

Одна из двух разностей обязана оказаться около 1234, и это назовёт дерево, в котором теряется
стоимость. Обе около нуля означали бы, что занижена не половина, а сама формула склейки.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

MARK_OLD = (
    "    // Reverse the list\n"
    "    std::reverse(path_edges.begin(), path_edges.end());\n"
)
MARK_NEW = MARK_OLD + (
    "    // WEDRIVE half split: длина прямой половины пути до присоединения обратной.\n"
    "    const size_t wd_fwd_n = path_edges.size();\n"
)

ANCHOR = (
    "      if (wedrive_debug_bidir() && !path.empty()) {\n"
)

SPLIT = ANCHOR + (
    "        // WEDRIVE half split: разрез recost в точке стыка двух деревьев.\n"
    "        if (wd_fwd_n > 0 && wd_fwd_n <= path.size()) {\n"
    "          const float wd_f_label = edgelabels_forward_[idx1].cost().cost;\n"
    "          const uint32_t wd_rp = edgelabels_reverse_[idx2].predecessor();\n"
    "          const float wd_r_label =\n"
    "              (wd_rp == kInvalidLabel) ? 0.f : edgelabels_reverse_[wd_rp].cost().cost;\n"
    "          const float wd_f_recost = path[wd_fwd_n - 1].elapsed_cost.cost;\n"
    "          const float wd_total = path.back().elapsed_cost.cost;\n"
    "          const float wd_r_recost = wd_total - wd_f_recost;\n"
    "          std::cerr << \"WEDRIVE HALF стык на ребре \" << wd_fwd_n << \" из \" << path.size()\n"
    "                    << std::endl;\n"
    "          std::cerr << \"    прямая:  метка=\" << wd_f_label << \"  recost=\" << wd_f_recost\n"
    "                    << \"  недосчёт=\" << (wd_f_recost - wd_f_label) << std::endl;\n"
    "          std::cerr << \"    обратная: метка=\" << wd_r_label << \"  recost=\" << wd_r_recost\n"
    "                    << \"  недосчёт=\" << (wd_r_recost - wd_r_label) << std::endl;\n"
    "          std::cerr << \"    метка обратной ВМЕСТЕ с ребром встречи=\"\n"
    "                    << edgelabels_reverse_[idx2].cost().cost << std::endl;\n"
    "        }\n"
)

NAME = "WEDRIVE half split"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(MARK_OLD) == 1, "не нашёл reverse the list"
    assert s.count(ANCHOR) == 1, "не нашёл якорь debug-блока"
    s = s.replace(MARK_OLD, MARK_NEW).replace(ANCHOR, SPLIT)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s длина прямой половины" % ("ok     " if "const size_t wd_fwd_n" in s else "MISSING"))
print("      %s метка обратной половины" % ("ok     " if "wd_r_label" in s else "MISSING"))
