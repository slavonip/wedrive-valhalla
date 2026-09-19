"""WeDrive patch 61: порталы и регион в собственном расширении CostMatrix.

Матрица — третья самостоятельная реализация обхода графа после Thor и Meili, и, как и они, про
порталы не знала. Патч 60 починил половину беды (кандидаты искались в одном регионе), осталась
вторая: даже с правильными кандидатами расширение не умеет сменить граф.

Два места, оба того же вида, что уже разобраны в Thor и Meili:

1. РЕГИОН на переходе между уровнями. trans->endnode() читается из тайла и сразу выбирает
   следующий тайл, узел и набор рёбер — namespace обязан сохраниться. Переход между уровнями
   региона не меняет: это тот же граф, другой уровень.

2. ПОРТАЛ рядом с блоком переходов, как в unidirectional_astar.cc: из узла раскрываются ещё и
   его порталы, и рёбра узла-близнеца обходятся тем же ExpandInner с тем же pred. Портал имеет
   нулевую длину между совпадающими узлами, поэтому отдельной стоимости не вносит.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/costmatrix.cc")
s = io.open(P, encoding="utf-8").read()

# --- 1. регион на переходе -------------------------------------------------------------------
TRANS_OLD = (
    "      graph_tile_ptr trans_tile = nullptr;\n"
    "      if ((!trans->up() && !ignore_hierarchy_limits_ &&\n"
    "           StopExpanding(hierarchy_limits[trans->endnode().level()], pred.path_distance())) ||\n"
    "          !(trans_tile = graphreader.GetGraphTile(trans->endnode()))) {\n"
    "        continue;\n"
    "      }\n"
)
TRANS_NEW = (
    "      // WEDRIVE costmatrix region: переход между уровнями region не меняет — это тот же\n"
    "      // граф. Но endnode прочитан из тайла и namespace не несёт, а дальше выбирает тайл,\n"
    "      // узел и весь набор рёбер.\n"
    "      const GraphId wd_trans_end = trans->endnode().with_region(node.region());\n"
    "      graph_tile_ptr trans_tile = nullptr;\n"
    "      if ((!trans->up() && !ignore_hierarchy_limits_ &&\n"
    "           StopExpanding(hierarchy_limits[wd_trans_end.level()], pred.path_distance())) ||\n"
    "          !(trans_tile = graphreader.GetGraphTile(wd_trans_end))) {\n"
    "        continue;\n"
    "      }\n"
)

NODE_OLD = (
    "      const auto* trans_node = trans_tile->node(trans->endnode());\n"
    "      EdgeMetadata trans_meta =\n"
    "          EdgeMetadata::make(trans->endnode(), trans_node, trans_tile, edgestatus);\n"
)
NODE_NEW = (
    "      const auto* trans_node = trans_tile->node(wd_trans_end);\n"
    "      EdgeMetadata trans_meta =\n"
    "          EdgeMetadata::make(wd_trans_end, trans_node, trans_tile, edgestatus);\n"
)

# --- 2. раскрытие порталов -------------------------------------------------------------------
ANCHOR = (
    "  // Now, after having looked at all the edges, including edges on other levels,\n"
    "  // we can say if this is a deadend or not, and if so, evaluate the uturn-edge (if it exists)\n"
)

PORTAL = (
    "  // WEDRIVE costmatrix portals: единственный способ сменить регион, тот же, что в Thor.\n"
    "  // Рёбра узла-близнеца обходятся тем же ExpandInner с тем же pred; портал имеет нулевую\n"
    "  // длину между совпадающими узлами и своей стоимости не вносит.\n"
    "  if (const auto* wd_portals = graphreader.PortalsAt(node)) {\n"
    "    for (const auto& wd_portal : *wd_portals) {\n"
    "      graph_tile_ptr wd_tile = graphreader.GetGraphTile(wd_portal.to);\n"
    "      if (wd_tile == nullptr) {\n"
    "        continue;\n"
    "      }\n"
    "      const auto* wd_node = wd_tile->node(wd_portal.to);\n"
    "      if (!costing_->Allowed(wd_node)) {\n"
    "        continue;\n"
    "      }\n"
    "      EdgeMetadata wd_meta = EdgeMetadata::make(wd_portal.to, wd_node, wd_tile, edgestatus);\n"
    "      uint32_t wd_shortcuts = 0;\n"
    "      for (uint32_t i = 0; i < wd_node->edge_count(); ++i, ++wd_meta) {\n"
    "        disable_uturn = ExpandInner<expansion_direction>(graphreader, index, pred, opp_pred_edge,\n"
    "                                                        wd_node, pred_idx, wd_meta,\n"
    "                                                        wd_shortcuts, wd_tile, offset_time) ||\n"
    "                        disable_uturn;\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "\n"
) + ANCHOR

NAME = "WEDRIVE costmatrix portals"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for label, old in (("переход", TRANS_OLD), ("узел перехода", NODE_OLD), ("якорь", ANCHOR)):
        assert s.count(old) == 1, "не нашёл якорь: %s" % label
    s = s.replace(TRANS_OLD, TRANS_NEW).replace(NODE_OLD, NODE_NEW).replace(ANCHOR, PORTAL)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("маркер", NAME, True),
    ("регион на переходе", "trans->endnode().with_region(node.region())", True),
    ("узел перехода тегирован", "trans_tile->node(wd_trans_end)", True),
    ("нетегированного перехода не осталось", "graphreader.GetGraphTile(trans->endnode())", False),
    ("раскрытие порталов", "graphreader.PortalsAt(node)", True),
    ("рёбра близнеца через ExpandInner", "wd_node, pred_idx, wd_meta", True),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
