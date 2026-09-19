"""WeDrive patch 57: сборка маршрута из сопоставления теряет регион.

После патча 56 внутри Meili регион 0 исчез совсем (регион 1 = 46520, регион 2 = 6264), и порталы
наконец заработали: 30 непустых ответов, 30 прыжков. Детектор передвинулся дальше по конвейеру:

    valhalla::thor::MapMatcher::FormPath
    valhalla::thor::thor_worker_t::map_match
    valhalla::thor::thor_worker_t::trace_route

Это уже не поиск, а сборка готового маршрута из сегментов сопоставления. Два места, оба одного
вида: endnode читается из тайла и сразу выбирает следующий тайл.

    // определение часового пояса по первому сегменту
    if (matcher->graphreader().GetGraphTile(directededge->endnode(), tile)) {
      nodeinfo = tile->node(directededge->endnode());

    // переход к следующему сегменту
    prior_node = directededge->endnode();
    graph_tile_ptr end_tile = matcher->graphreader().GetGraphTile(prior_node);

Регион берётся у ребра, которому endnode принадлежит: сегмент целиком лежит в одном графе, а
смену графа делает портал, а не ребро.

Второе место особенно неприятно тем, что end_tile разыменовывается без проверки: чужой регион
здесь означал бы не кривой маршрут, а падение на nullptr.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/map_matcher.cc")
s = io.open(P, encoding="utf-8").read()

TZ_OLD = (
    "    directededge = tile->directededge(s.edgeid);\n"
    "    if (matcher->graphreader().GetGraphTile(directededge->endnode(), tile)) {\n"
    "      // get the timezone\n"
    "      nodeinfo = tile->node(directededge->endnode());\n"
)
TZ_NEW = (
    "    directededge = tile->directededge(s.edgeid);\n"
    "    // WEDRIVE mapmatcher region: endnode выбирает СЛЕДУЮЩИЙ тайл, значит обязан нести\n"
    "    // регион своего ребра. Сегмент целиком лежит в одном графе — граф меняет портал.\n"
    # map_matcher.cc лежит внутри namespace thor, где baldr уже внесён using-директивой:
    # квалификатор baldr:: здесь не разрешается.
    "    const GraphId wd_tz_node = directededge->endnode().with_region(s.edgeid.region());\n"
    "    if (matcher->graphreader().GetGraphTile(wd_tz_node, tile)) {\n"
    "      // get the timezone\n"
    "      nodeinfo = tile->node(wd_tz_node);\n"
)

NODE_OLD = (
    "    prior_node = directededge->endnode();\n"
    "    graph_tile_ptr end_tile = matcher->graphreader().GetGraphTile(prior_node);\n"
    "    nodeinfo = end_tile->node(prior_node);\n"
)
NODE_NEW = (
    "    // WEDRIVE mapmatcher region: то же самое на переходе к следующему сегменту. Здесь\n"
    "    // end_tile разыменовывается без проверки, поэтому чужой регион означал бы не кривой\n"
    "    // маршрут, а падение на nullptr.\n"
    "    prior_node = directededge->endnode().with_region(edge_id.region());\n"
    "    graph_tile_ptr end_tile = matcher->graphreader().GetGraphTile(prior_node);\n"
    "    nodeinfo = end_tile->node(prior_node);\n"
)

NAME = "WEDRIVE mapmatcher region"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for label, old in (("часовой пояс", TZ_OLD), ("переход к сегменту", NODE_OLD)):
        assert s.count(old) == 1, "не нашёл якорь: %s" % label
    io.open(P, "w", encoding="utf-8").write(s.replace(TZ_OLD, TZ_NEW).replace(NODE_OLD, NODE_NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("маркер", NAME, True),
    ("часовой пояс тегирован", "with_region(s.edgeid.region())", True),
    ("переход тегирован", "prior_node = directededge->endnode().with_region(edge_id.region());", True),
    ("нетегированный выбор тайла убран",
     "GetGraphTile(directededge->endnode(), tile)", False),
    ("нетегированный prior_node убран", "prior_node = directededge->endnode();", False),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
