"""WeDrive patch 37: кумулятивное расхождение вдоль всего пути.

Гипотеза о шорткатах опровергнута собственным измерением: Σ EdgeCost = 6276.8 против
Σ прироста при recost = 6310.3, расхождение 33.5 при недосчёте 1234.44. Шорткаты считаются
правильно; их отключение просто уводило поиск на другой маршрут.

Значит надо идти по пути ребро за ребром. Для каждого считается EdgeCost плюс transition_cost из
recost, сумма сравнивается с накопленной elapsed_cost. В норме разность около нуля на всём
протяжении; место, где она скачком вырастает, и есть источник.

Печатаются только скачки больше 20 и контрольные точки вокруг шва регионов — иначе на 993 рёбрах
вывод нечитаем.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

ANCHOR = "          if (wd_sc <= 16) {"

NEW_BEFORE = (
    "          // ничего: подробности по шорткатам ниже\n"
    "          if (wd_sc <= 16) {"
)

# Кумулятивная проверка ставится ПЕРЕД циклом по шорткатам: отдельный проход по всем рёбрам.
CUM_OLD = (
    "        size_t wd_sc = 0;\n"
    "        // WEDRIVE shortcut detail: по каждому шорткату — входы расчёта и два числа,\n"
    "        // которые обязаны совпадать: EdgeCost и фактический прирост при recost.\n"
)

CUM_NEW = (
    "        // WEDRIVE cumulative diff: идём по пути ребро за ребром и сравниваем сумму\n"
    "        // EdgeCost + transition_cost с накопленной стоимостью recost. В норме разность\n"
    "        // держится около нуля; место её скачка и есть источник недосчёта.\n"
    "        {\n"
    "          float wd_sum = 0.f;\n"
    "          float wd_prev_diff = 0.f;\n"
    "          uint32_t wd_r_prev = 0;\n"
    "          for (size_t wd_j = 0; wd_j < path_edges.size() && wd_j < path.size(); ++wd_j) {\n"
    "            const auto& wd_id = path_edges[wd_j];\n"
    "            graph_tile_ptr wd_tt;\n"
    "            if (!graphreader.GetGraphTile(wd_id, wd_tt)) {\n"
    "              continue;\n"
    "            }\n"
    "            uint8_t wd_fs = 0;\n"
    "            const auto wd_c = costing_->EdgeCost(wd_tt->directededge(wd_id), wd_id, wd_tt,\n"
    "                                                 time_info, wd_fs);\n"
    "            wd_sum += wd_c.cost + path[wd_j].transition_cost.cost;\n"
    "            const float wd_diff = path[wd_j].elapsed_cost.cost - wd_sum;\n"
    "            const bool wd_seam = (wd_j > 0 && wd_id.region() != wd_r_prev);\n"
    "            if (std::abs(wd_diff - wd_prev_diff) > 20.f || wd_seam) {\n"
    "              std::cerr << \"WEDRIVE CUM поз=\" << wd_j << \" регион=\" << wd_id.region()\n"
    "                        << (wd_seam ? \" ШОВ\" : \"\") << \" расхождение=\" << wd_diff\n"
    "                        << \" (скачок \" << (wd_diff - wd_prev_diff) << \")\" << std::endl;\n"
    "            }\n"
    "            wd_prev_diff = wd_diff;\n"
    "            wd_r_prev = wd_id.region();\n"
    "          }\n"
    "          std::cerr << \"WEDRIVE CUM итог: Σ(EdgeCost+transition)=\" << wd_sum\n"
    "                    << \"  recost=\" << path.back().elapsed_cost.cost\n"
    "                    << \"  расхождение=\" << (path.back().elapsed_cost.cost - wd_sum)\n"
    "                    << std::endl;\n"
    "        }\n"
) + CUM_OLD

NAME = "WEDRIVE cumulative diff"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(CUM_OLD) == 1, "не нашёл начало блока шорткатов"
    s = s.replace(CUM_OLD, CUM_NEW)
    if "#include <cmath>" not in s:
        first = s.index("#include")
        s = s[:first] + "#include <cmath> // WEDRIVE cumulative diff\n" + s[first:]
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s cmath подключён" % ("ok     " if "#include <cmath>" in s else "MISSING"))
