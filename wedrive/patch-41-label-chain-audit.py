"""WeDrive patch 41: где прямое дерево перестаёт считать.

Патч 40 разрезал недосчёт по половинам и ответил однозначно:

    прямая половина:  метка 7147.72  против честного recost 8350.56  -> -1202.84
    обратная:         метка 10765.8  против            10800.4       ->    -34.60

Вся потеря сидит в прямом дереве — том самом, которое проходит портал (шов региона на ребре 600
из 993, стык деревьев на 615).

Здесь цепочка forward-меток обходится от начала к точке встречи и для каждой метки честно
считается то, из чего её стоимость обязана складываться:

    cost(метка) == cost(предыдущая) + transition_cost + EdgeCost(ребро)

Накопленная сумма сравнивается с cost() самой метки. Пока патч считает верно, разность держится
у нуля; шаг, на котором она скачком уходит, и есть место потери. Печатаются только скачки больше
20 и окрестность смены региона.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

ANCHOR = "        // WEDRIVE half split: разрез recost в точке стыка двух деревьев.\n"

AUDIT = (
    "        // WEDRIVE label chain audit: проверка каждой forward-метки на её же формулу.\n"
    "        {\n"
    "          std::vector<uint32_t> wd_chain;\n"
    "          for (uint32_t wd_k = idx1; wd_k != kInvalidLabel;\n"
    "               wd_k = edgelabels_forward_[wd_k].predecessor()) {\n"
    "            wd_chain.push_back(wd_k);\n"
    "            if (wd_chain.size() > 20000) {\n"
    "              break;\n"
    "            }\n"
    "          }\n"
    "          std::reverse(wd_chain.begin(), wd_chain.end());\n"
    "          float wd_acc = 0.f;\n"
    "          float wd_prev_gap = 0.f;\n"
    "          uint32_t wd_reg_prev = 0;\n"
    "          size_t wd_bad = 0;\n"
    "          for (size_t wd_p = 0; wd_p < wd_chain.size(); ++wd_p) {\n"
    "            const auto& wd_l = edgelabels_forward_[wd_chain[wd_p]];\n"
    "            const auto wd_id = wd_l.edgeid();\n"
    "            graph_tile_ptr wd_tt;\n"
    "            if (!graphreader.GetGraphTile(wd_id, wd_tt) || !wd_tt) {\n"
    "              std::cerr << \"WEDRIVE AUDIT шаг=\" << wd_p << \" ТАЙЛ НЕ ЧИТАЕТСЯ регион=\"\n"
    "                        << wd_id.region() << std::endl;\n"
    "              continue;\n"
    "            }\n"
    "            uint8_t wd_fs = 0;\n"
    "            const auto wd_c = costing_->EdgeCost(wd_tt->directededge(wd_id), wd_id, wd_tt,\n"
    "                                                 time_info, wd_fs);\n"
    "            wd_acc += wd_c.cost + wd_l.transition_cost().cost;\n"
    "            const float wd_gap = wd_l.cost().cost - wd_acc;\n"
    "            const uint32_t wd_reg = wd_id.region();\n"
    "            const bool wd_seam = (wd_p > 0 && wd_reg != wd_reg_prev);\n"
    "            if (std::abs(wd_gap - wd_prev_gap) > 20.f || wd_seam ||\n"
    "                wd_p + 3 >= wd_chain.size()) {\n"
    "              ++wd_bad;\n"
    "              if (wd_bad <= 24) {\n"
    "                std::cerr << \"WEDRIVE AUDIT шаг=\" << wd_p << \"/\" << wd_chain.size()\n"
    "                          << \" регион=\" << wd_reg << (wd_seam ? \" ШОВ\" : \"\")\n"
    "                          << \" shortcut=\"\n"
    "                          << (wd_tt->directededge(wd_id)->is_shortcut() ? 1 : 0)\n"
    "                          << \" EdgeCost=\" << wd_c.cost\n"
    "                          << \" transition=\" << wd_l.transition_cost().cost\n"
    "                          << \" метка=\" << wd_l.cost().cost << \" сумма=\" << wd_acc\n"
    "                          << \" расхождение=\" << wd_gap\n"
    "                          << \" (скачок \" << (wd_gap - wd_prev_gap) << \")\" << std::endl;\n"
    "              }\n"
    "            }\n"
    "            wd_prev_gap = wd_gap;\n"
    "            wd_reg_prev = wd_reg;\n"
    "          }\n"
    "          std::cerr << \"WEDRIVE AUDIT итог: меток=\" << wd_chain.size()\n"
    "                    << \"  Σ(EdgeCost+transition)=\" << wd_acc\n"
    "                    << \"  метка в точке встречи=\"\n"
    "                    << edgelabels_forward_[idx1].cost().cost\n"
    "                    << \"  расхождение=\"\n"
    "                    << (edgelabels_forward_[idx1].cost().cost - wd_acc) << std::endl;\n"
    "        }\n"
) + ANCHOR

NAME = "WEDRIVE label chain audit"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(ANCHOR) == 1, "не нашёл якорь half split"
    io.open(P, "w", encoding="utf-8").write(s.replace(ANCHOR, AUDIT))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s обход цепочки" % ("ok     " if "wd_chain.push_back" in s else "MISSING"))
print("      %s сверка с меткой" % ("ok     " if "wd_l.cost().cost - wd_acc" in s else "MISSING"))
