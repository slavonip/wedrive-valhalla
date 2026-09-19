"""WeDrive patch 42: что возвращает восстановление шортката.

Патч 41 закрыл прямое дерево: 592 метки считают себя безупречно, Σ(EdgeCost+transition)=7163.42
против метки 7147.72, разность −15.69 постоянна (частичное первое ребро) и не дёргается даже на
шве регионов.

Но те же 592 метки, развёрнутые в 615 рёбер пути, при честном recost стоят 8350.56. Разница 1187
рождается ровно при развёртывании: где-то шорткат заменяется набором рёбер, который стоит совсем
не столько, сколько сам шорткат.

Здесь по каждому шорткату прямой цепочки печатается всё, что нужно для приговора:

    сам шорткат      регион, тайл, id, length, EdgeCost
    восстановление   сколько рёбер, Σ length, Σ EdgeCost, набор регионов
    признак отказа   восстановление вернуло сам шорткат

Если Σ length компонентов совпадает с length шортката, а Σ EdgeCost — нет, виновата стоимость.
Если расходятся длины или среди компонентов встречается ЧУЖОЙ регион — восстановление ушло в
другой namespace, и это наш дефект.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

ANCHOR = "        // WEDRIVE label chain audit: проверка каждой forward-метки на её же формулу.\n"

REC = (
    "        // WEDRIVE recovery audit: шорткат против рёбер, которыми он разворачивается.\n"
    "        {\n"
    "          std::vector<uint32_t> wd_ch;\n"
    "          for (uint32_t wd_k = idx1; wd_k != kInvalidLabel;\n"
    "               wd_k = edgelabels_forward_[wd_k].predecessor()) {\n"
    "            wd_ch.push_back(wd_k);\n"
    "            if (wd_ch.size() > 20000) {\n"
    "              break;\n"
    "            }\n"
    "          }\n"
    "          std::reverse(wd_ch.begin(), wd_ch.end());\n"
    "          size_t wd_nsc = 0;\n"
    "          size_t wd_failed = 0;\n"
    "          size_t wd_foreign = 0;\n"
    "          float wd_sc_sum = 0.f;\n"
    "          float wd_comp_sum = 0.f;\n"
    "          for (size_t wd_p = 0; wd_p < wd_ch.size(); ++wd_p) {\n"
    "            const auto wd_id = edgelabels_forward_[wd_ch[wd_p]].edgeid();\n"
    "            graph_tile_ptr wd_tt;\n"
    "            if (!graphreader.GetGraphTile(wd_id, wd_tt) || !wd_tt) {\n"
    "              continue;\n"
    "            }\n"
    "            const auto* wd_de = wd_tt->directededge(wd_id);\n"
    "            if (!wd_de->is_shortcut()) {\n"
    "              continue;\n"
    "            }\n"
    "            ++wd_nsc;\n"
    "            uint8_t wd_fs = 0;\n"
    "            const auto wd_sc_c = costing_->EdgeCost(wd_de, wd_id, wd_tt, time_info, wd_fs);\n"
    "            const auto wd_rec = graphreader.RecoverShortcut(wd_id);\n"
    "            const bool wd_fail = (wd_rec.size() == 1 && wd_rec.front() == wd_id);\n"
    "            wd_failed += wd_fail ? 1 : 0;\n"
    "            uint32_t wd_len = 0;\n"
    "            float wd_cc = 0.f;\n"
    "            uint32_t wd_other = 0;\n"
    "            for (const auto& wd_c_id : wd_rec) {\n"
    "              if (wd_c_id.region() != wd_id.region()) {\n"
    "                ++wd_other;\n"
    "              }\n"
    "              graph_tile_ptr wd_ct;\n"
    "              if (!graphreader.GetGraphTile(wd_c_id, wd_ct) || !wd_ct) {\n"
    "                continue;\n"
    "              }\n"
    "              const auto* wd_cde = wd_ct->directededge(wd_c_id);\n"
    "              wd_len += wd_cde->length();\n"
    "              uint8_t wd_cfs = 0;\n"
    "              wd_cc += costing_->EdgeCost(wd_cde, wd_c_id, wd_ct, time_info, wd_cfs).cost;\n"
    "            }\n"
    "            wd_foreign += wd_other;\n"
    "            wd_sc_sum += wd_sc_c.cost;\n"
    "            wd_comp_sum += wd_cc;\n"
    "            if (wd_nsc <= 24) {\n"
    "              std::cerr << \"WEDRIVE REC #\" << wd_nsc << \" шаг=\" << wd_p\n"
    "                        << \" регион=\" << wd_id.region() << \" тайл=\" << wd_id.tileid()\n"
    "                        << \" id=\" << wd_id.id() << \" length=\" << wd_de->length()\n"
    "                        << \" EdgeCost=\" << wd_sc_c.cost\n"
    "                        << (wd_fail ? \"  ОТКАЗ\" : \"\") << \"  ->рёбер=\" << wd_rec.size()\n"
    "                        << \" Σlength=\" << wd_len << \" ΣEdgeCost=\" << wd_cc\n"
    "                        << \" чужойРегион=\" << wd_other\n"
    "                        << \"  дельта=\" << (wd_cc - wd_sc_c.cost) << std::endl;\n"
    "            }\n"
    "          }\n"
    "          std::cerr << \"WEDRIVE REC итог: шорткатов=\" << wd_nsc << \" отказов=\" << wd_failed\n"
    "                    << \" компонентов из чужого региона=\" << wd_foreign\n"
    "                    << \"  Σ EdgeCost шорткатов=\" << wd_sc_sum\n"
    "                    << \"  Σ EdgeCost компонентов=\" << wd_comp_sum\n"
    "                    << \"  дельта=\" << (wd_comp_sum - wd_sc_sum) << std::endl;\n"
    "        }\n"
) + ANCHOR

NAME = "WEDRIVE recovery audit"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(ANCHOR) == 1, "не нашёл якорь label chain audit"
    io.open(P, "w", encoding="utf-8").write(s.replace(ANCHOR, REC))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s вызов восстановления" % ("ok     " if "graphreader.RecoverShortcut(wd_id)" in s else "MISSING"))
print("      %s проверка чужого региона" % ("ok     " if "wd_c_id.region() != wd_id.region()" in s else "MISSING"))
