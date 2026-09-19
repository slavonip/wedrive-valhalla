"""WeDrive patch 36: подробности по каждому шорткату выигравшего пути.

Установлено: без шорткатов композит даёт ровно монолитный маршрут и нулевой недосчёт, с ними —
1234.44 на 16 штук. Значит вопрос сузился до одного:

    почему стоимость шортката при поиске меньше, чем при пересчёте того же ребра?

Для каждого шортката печатается:

  позиция в пути, GraphId, регион, длина, скорость,
  EdgeCost, посчитанный здесь же теми же costing и time_info,
  фактический прирост стоимости при recost (разность соседних elapsed_cost).

Если эти два числа расходятся при одинаковых входах — дефект в самом расчёте. Если сходятся,
значит недосчёт рождается не на ребре, а в накоплении вокруг него.

Отдельно печатается позиция смены региона в пути: если шорткаты сидят ПОСЛЕ портала, это прямо
указывает на потерю состояния при создании портального лейбла.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "        size_t wd_sc = 0;\n"
    "        for (const auto& wd_e : path_edges) {\n"
    "          graph_tile_ptr wd_t;\n"
    "          if (graphreader.GetGraphTile(wd_e, wd_t) && wd_t->directededge(wd_e)->is_shortcut()) {\n"
    "            ++wd_sc;\n"
    "          }\n"
    "        }"
)

NEW = (
    "        size_t wd_sc = 0;\n"
    "        // WEDRIVE shortcut detail: по каждому шорткату — входы расчёта и два числа,\n"
    "        // которые обязаны совпадать: EdgeCost и фактический прирост при recost.\n"
    "        uint32_t wd_prev_region = 0;\n"
    "        for (size_t wd_i = 0; wd_i < path_edges.size(); ++wd_i) {\n"
    "          const auto& wd_e = path_edges[wd_i];\n"
    "          const uint32_t wd_r = wd_e.region();\n"
    "          if (wd_i > 0 && wd_r != wd_prev_region) {\n"
    "            std::cerr << \"WEDRIVE SEAM: смена региона \" << wd_prev_region << \"->\" << wd_r\n"
    "                      << \" на ребре \" << wd_i << \" из \" << path_edges.size() << std::endl;\n"
    "          }\n"
    "          wd_prev_region = wd_r;\n"
    "          graph_tile_ptr wd_t;\n"
    "          if (!graphreader.GetGraphTile(wd_e, wd_t)) {\n"
    "            continue;\n"
    "          }\n"
    "          const auto* wd_de = wd_t->directededge(wd_e);\n"
    "          if (!wd_de->is_shortcut()) {\n"
    "            continue;\n"
    "          }\n"
    "          ++wd_sc;\n"
    "          uint8_t wd_flow = 0;\n"
    "          const auto wd_ec = costing_->EdgeCost(wd_de, wd_e, wd_t, time_info, wd_flow);\n"
    "          const float wd_recost = (wd_i < path.size())\n"
    "                                      ? (path[wd_i].elapsed_cost.cost -\n"
    "                                         (wd_i ? path[wd_i - 1].elapsed_cost.cost : 0.f))\n"
    "                                      : -1.f;\n"
    "          if (wd_sc <= 16) {\n"
    "            std::cerr << \"WEDRIVE SC #\" << wd_sc << \" поз=\" << wd_i << \" регион=\" << wd_r\n"
    "                      << \" длина=\" << wd_de->length() << \" скорость=\" << wd_de->speed()\n"
    "                      << \" EdgeCost=\" << wd_ec.cost << \" (сек \" << wd_ec.secs\n"
    "                      << \")  приростRecost=\" << wd_recost << std::endl;\n"
    "          }\n"
    "        }"
)

NAME = "WEDRIVE shortcut detail"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    n = s.count(OLD)
    assert n == 1, "ожидал 1 совпадение, нашёл %d" % n
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s печать шва регионов" % ("ok     " if "WEDRIVE SEAM" in s else "MISSING"))
print("      %s EdgeCost считается" % ("ok     " if "costing_->EdgeCost(wd_de" in s else "MISSING"))
