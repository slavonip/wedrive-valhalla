"""WeDrive patch 56: регион теряется там, где поиск Meili НАЧИНАЕТСЯ.

Детектор снова указал место сам, и снова не туда, где я смотрел. После патча 55 первый же стек
стал таким:

    valhalla::meili::find_shortest_path
    valhalla::meili::TransitionCostModel::UpdateRoute
    valhalla::meili::ViterbiSearch::AddSuccessorsToQueue

Место — ветка раскрытия ИСХОДНОГО ребра, та, что отрабатывает, когда origin стоит посреди ребра,
а не в узле. Там endnode берётся из тайла напрямую и трижды используется как есть:

    baldr::graph_tile_ptr endtile = reader.GetGraphTile(directed_edge->endnode());
    float sortcost = ... heuristic(endtile->get_node_ll(directed_edge->endnode()));
    labelset->put(directed_edge->endnode(), origin_edge.id, ...);

Первое выбирает тайл, третье кладётся в labelset узлом для дальнейшего расширения — обоим
region обязателен. Второе индексирует уже выбранный тайл, и там тег безразличен.

Это ровно та же ошибка, что уже была сделана трижды в Thor: тег поставлен там, где узел
ОБНОВЛЯЕТСЯ, и пропущен там, где он РОЖДАЕТСЯ. Отсюда 41923 узла региона 0 в гистограмме:
почти каждый поиск между парой измерений стартовал без namespace, а дальше патчи 47 и 52
добросовестно протаскивали этот нулевой регион по всему дереву.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/routing.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "          baldr::graph_tile_ptr endtile = reader.GetGraphTile(directed_edge->endnode());\n"
    "          if (endtile == nullptr) {\n"
    "            continue;\n"
    "          }\n"
    "          float sortcost = cost.cost + heuristic(endtile->get_node_ll(directed_edge->endnode()));\n"
    "          labelset->put(directed_edge->endnode(), origin_edge.id, origin_edge.percent_along, 1.f,\n"
    "                        cost, turn_cost, sortcost, label_idx, directed_edge, travelmode,\n"
    "                        restriction_idx);\n"
)

NEW = (
    "          // WEDRIVE meili region: здесь поиск РОЖДАЕТСЯ. Регион берётся у исходного ребра —\n"
    "          // без этого всё дерево расширения уходит в namespace по умолчанию.\n"
    "          const baldr::GraphId wd_origin_end =\n"
    "              directed_edge->endnode().with_region(origin_edge.id.region());\n"
    "          baldr::graph_tile_ptr endtile = reader.GetGraphTile(wd_origin_end);\n"
    "          if (endtile == nullptr) {\n"
    "            continue;\n"
    "          }\n"
    "          float sortcost = cost.cost + heuristic(endtile->get_node_ll(wd_origin_end));\n"
    "          labelset->put(wd_origin_end, origin_edge.id, origin_edge.percent_along, 1.f,\n"
    "                        cost, turn_cost, sortcost, label_idx, directed_edge, travelmode,\n"
    "                        restriction_idx);\n"
)

NAME = "WEDRIVE meili region: здесь поиск РОЖДАЕТСЯ"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл раскрытие исходного ребра"
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("маркер", NAME, True),
    ("тег от исходного ребра", "directed_edge->endnode().with_region(origin_edge.id.region())", True),
    ("тайл берётся по тегированному узлу", "reader.GetGraphTile(wd_origin_end)", True),
    ("в labelset уходит тегированный узел", "labelset->put(wd_origin_end, origin_edge.id", True),
    ("нетегированный endnode в labelset не остался",
     "labelset->put(directed_edge->endnode(), origin_edge.id", False),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
