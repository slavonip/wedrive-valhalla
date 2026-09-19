"""WeDrive patch 43: перепись transition_cost, которую recost начисляет себе сам.

Патч 42 снял подозрение с восстановления шорткатов: 12 шорткатов, ни одного компонента из чужого
региона, суммарная дельта 1.34 при недосчёте 1187. Кэш восстановления не виноват.

Остаётся единственное место, куда 1187 могут поместиться, и которое прежняя кумулятивная
проверка увидеть НЕ МОГЛА: собственные transition_cost внутри recost. Она сравнивала
elapsed_cost с суммой EdgeCost + path[j].transition_cost — то есть подставляла подозреваемое
число в обе части равенства и потому показывала ноль на шве.

Здесь transition_cost печатается напрямую: все, что больше 50, плюс окрестность смены региона.
Путь сшит из двух графов, и между последним ребром MD и первым ребром RO НЕТ ребра — портал это
переход между совпадающими узлами. recost идёт по списку рёбер подряд и обязан чем-то посчитать
этот стык.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

ANCHOR = "        // WEDRIVE recovery audit: шорткат против рёбер, которыми он разворачивается.\n"

CENSUS = (
    "        // WEDRIVE transition census: во что recost оценил переходы между рёбрами.\n"
    "        {\n"
    "          float wd_tr_sum = 0.f;\n"
    "          float wd_tr_fwd = 0.f;\n"
    "          uint32_t wd_pr = 0;\n"
    "          size_t wd_shown = 0;\n"
    "          for (size_t wd_j = 0; wd_j < path.size(); ++wd_j) {\n"
    "            const float wd_t = path[wd_j].transition_cost.cost;\n"
    "            wd_tr_sum += wd_t;\n"
    "            if (wd_j < wd_fwd_n) {\n"
    "              wd_tr_fwd += wd_t;\n"
    "            }\n"
    "            const uint32_t wd_r =\n"
    "                (wd_j < path_edges.size()) ? path_edges[wd_j].region() : 0u;\n"
    "            const bool wd_seam = (wd_j > 0 && wd_r != wd_pr);\n"
    "            if ((wd_t > 50.f || wd_seam) && wd_shown < 24) {\n"
    "              ++wd_shown;\n"
    "              std::cerr << \"WEDRIVE TR поз=\" << wd_j << \"/\" << path.size()\n"
    "                        << \" регион=\" << wd_r << (wd_seam ? \" ШОВ\" : \"\")\n"
    "                        << (wd_j < wd_fwd_n ? \" прямая\" : \" обратная\")\n"
    "                        << \" transition=\" << wd_t\n"
    "                        << \" (сек \" << path[wd_j].transition_cost.secs << \")\"\n"
    "                        << \" elapsed=\" << path[wd_j].elapsed_cost.cost << std::endl;\n"
    "            }\n"
    "            wd_pr = wd_r;\n"
    "          }\n"
    "          std::cerr << \"WEDRIVE TR итог: Σ переходов=\" << wd_tr_sum\n"
    "                    << \"  из них на прямой половине=\" << wd_tr_fwd << std::endl;\n"
    "        }\n"
) + ANCHOR

NAME = "WEDRIVE transition census"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(ANCHOR) == 1, "не нашёл якорь recovery audit"
    io.open(P, "w", encoding="utf-8").write(s.replace(ANCHOR, CENSUS))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s сумма по прямой половине" % ("ok     " if "wd_tr_fwd" in s else "MISSING"))
