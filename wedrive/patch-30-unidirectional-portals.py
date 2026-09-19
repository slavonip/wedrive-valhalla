"""WeDrive patch 30: порталы в ОДНОнаправленный A*.

Портальное расширение было только в BidirectionalAStar. Из-за этого запрос с `date_time`, который
форсирует `timedep_forward`, вообще не находил трансграничный маршрут:

    двунаправленный   монолит 456.458   композит 469.423
    однонаправленный  монолит 456.458   композит "No path could be found"

Для навигации это блокирующая дыра: время отправления в машине задаётся почти всегда.

Правки те же три, что и в патче 8, и по тем же причинам:
  * endnode ребра, уходящего в соседний тайл, тегируется регионом ребра;
  * переход между уровнями иерархии наследует регион узла;
  * портал раскрывается как узел-близнец в другом регионе — единственное место, которому
    разрешено сменить namespace.

Класс `UnidirectionalAStar` шаблонный и инстанцируется и для forward, и для reverse, поэтому одна
правка покрывает оба направления.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/unidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

EDITS = [
    (
        "WEDRIVE uni leaves_tile keeps region",
        "  auto endtile = meta.edge->leaves_tile() ? graphreader.GetGraphTile(meta.edge->endnode()) : tile;",
        "  // WEDRIVE uni leaves_tile keeps region: обычное ребро namespace не меняет.\n"
        "  auto endtile = meta.edge->leaves_tile()\n"
        "                     ? graphreader.GetGraphTile(\n"
        "                           meta.edge->endnode().with_region(meta.edge_id.region()))\n"
        "                     : tile;",
    ),
    (
        "WEDRIVE uni transition keeps region",
        "      graph_tile_ptr trans_tile = nullptr;\n"
        "      if ((!trans->up() &&\n"
        "           StopExpanding(hierarchy_limits_[trans->endnode().level()], pred.distance())) ||\n"
        "          !(trans_tile = graphreader.GetGraphTile(trans->endnode()))) {\n"
        "        continue;\n"
        "      }\n"
        "      // setup for expansion at this level\n"
        "      hierarchy_limits_[node.level()].set_up_transition_count(\n"
        "          hierarchy_limits_[node.level()].up_transition_count() + trans->up());\n"
        "      const auto* trans_node = trans_tile->node(trans->endnode());\n"
        "      EdgeMetadata trans_meta =\n"
        "          EdgeMetadata::make(trans->endnode(), trans_node, trans_tile, edgestatus_);",
        "      graph_tile_ptr trans_tile = nullptr;\n"
        "      // WEDRIVE uni transition keeps region.\n"
        "      const GraphId trans_end = trans->endnode().with_region(node.region());\n"
        "      if ((!trans->up() &&\n"
        "           StopExpanding(hierarchy_limits_[trans_end.level()], pred.distance())) ||\n"
        "          !(trans_tile = graphreader.GetGraphTile(trans_end))) {\n"
        "        continue;\n"
        "      }\n"
        "      // setup for expansion at this level\n"
        "      hierarchy_limits_[node.level()].set_up_transition_count(\n"
        "          hierarchy_limits_[node.level()].up_transition_count() + trans->up());\n"
        "      const auto* trans_node = trans_tile->node(trans_end);\n"
        "      EdgeMetadata trans_meta =\n"
        "          EdgeMetadata::make(trans_end, trans_node, trans_tile, edgestatus_);",
    ),
    (
        "WEDRIVE uni portal expansion",
        "  if (!disable_uturn && uturn_meta) {",
        "  // WEDRIVE uni portal expansion: единственное место, меняющее namespace. Раскрываем рёбра\n"
        "  // узла-близнеца в другом регионе — тем же механизмом, что и переход между уровнями.\n"
        "  if (const auto* portals = graphreader.PortalsAt(node)) {\n"
        "    for (const auto& portal : *portals) {\n"
        "      graph_tile_ptr portal_tile = graphreader.GetGraphTile(portal.to);\n"
        "      if (portal_tile == nullptr) {\n"
        "        continue;\n"
        "      }\n"
        "      const auto* portal_node = portal_tile->node(portal.to);\n"
        "      if (!costing_->Allowed(portal_node)) {\n"
        "        continue;\n"
        "      }\n"
        "      EdgeMetadata portal_meta =\n"
        "          EdgeMetadata::make(portal.to, portal_node, portal_tile, edgestatus_);\n"
        "      for (uint32_t i = 0; i < portal_node->edge_count(); ++i, ++portal_meta) {\n"
        "        disable_uturn = ExpandInner(graphreader, pred, opp_pred_edge, portal_node, pred_idx,\n"
        "                                    portal_meta, portal_tile, offset_time, destination,\n"
        "                                    best_path) ||\n"
        "                        disable_uturn;\n"
        "      }\n"
        "    }\n"
        "  }\n\n"
        "  if (!disable_uturn && uturn_meta) {",
    ),
]

changed = False
for name, old, new in EDITS:
    if name in s:
        print("      ok   уже применено: %s" % name)
        continue
    n = s.count(old)
    assert n == 1, "ожидал 1 совпадение для %s, нашёл %d" % (name, n)
    s = s.replace(old, new)
    changed = True
    print("      +    %s" % name)
if changed:
    io.open(P, "w", encoding="utf-8").write(s)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
for name, _, _ in EDITS:
    print("      %s %s" % ("ok     " if name in s else "MISSING", name))
