"""WeDrive patch 8: детектор потери региона + портальное расширение в настоящем Thor."""
import io
import os

SRC = "/src/valhalla"


def patch(relpath, edits):
    p = os.path.join(SRC, relpath)
    s = io.open(p, encoding="utf-8").read()
    changed = False
    for name, old, new in edits:
        if name in s:
            print("      ok   уже применено: %s" % name)
            continue
        n = s.count(old)
        assert n == 1, "%s: ожидал 1 совпадение для %s, нашёл %d" % (relpath, name, n)
        s = s.replace(old, new)
        changed = True
        print("      +    %s" % name)
    if changed:
        io.open(p, "w", encoding="utf-8").write(s)


print("   valhalla/baldr/graphreader.h")
patch(
    "valhalla/baldr/graphreader.h",
    [("WEDRIVE atomic include", "#include <valhalla/baldr/graphid.h>",
      "#include <atomic> // WEDRIVE atomic include: счётчик потерь региона\n"
      "#include <valhalla/baldr/graphid.h>")],
)

print("   src/baldr/graphreader.cc")
patch(
    "src/baldr/graphreader.cc",
    [
        (
            "WEDRIVE region lost detector",
            "graph_tile_ptr GraphReader::GetGraphTile(const GraphId& graphid) {\n"
            "  // Return nullptr if not a valid tile\n"
            "  if (!graphid.is_valid()) {\n"
            "    return nullptr;\n"
            "  }",
            "graph_tile_ptr GraphReader::GetGraphTile(const GraphId& graphid) {\n"
            "  // Return nullptr if not a valid tile\n"
            "  if (!graphid.is_valid()) {\n"
            "    return nullptr;\n"
            "  }\n\n"
            "  // WEDRIVE region lost detector. Если зарегистрировано больше одного региона, то\n"
            "  // id без региона означает, что где-то по дороге тег потерян — и тайл сейчас будет\n"
            "  // взят из ЧУЖОГО каталога. Это ровно та тихая ошибка, ради которой детектор и\n"
            "  // существует: он превращает «машина уехала в соседнюю страну» в счётчик, который\n"
            "  // тест обязан увидеть нулевым, и заодно сам показывает пропущенные call sites.\n"
            "  if (wedrive_region_dirs_.size() > 1 && graphid.region() == 0) {\n"
            "    if (wedrive_region_lost_.fetch_add(1, std::memory_order_relaxed) == 0) {\n"
            "      std::cerr << \"WEDRIVE WARNING: GetGraphTile received an id with no region while \"\n"
            "                << wedrive_region_dirs_.size()\n"
            "                << \" regions are registered. level=\" << graphid.level()\n"
            "                << \" tileid=\" << graphid.tileid() << \" id=\" << graphid.id()\n"
            "                << \" -- the region tag was dropped upstream of here.\" << std::endl;\n"
            "    }\n"
            "  }",
        ),
    ],
)

print("   src/thor/bidirectional_astar.cc")
patch(
    "src/thor/bidirectional_astar.cc",
    [
        # Ребро, уходящее в соседний тайл: endnode из байтов, региона нет.
        (
            "WEDRIVE leaves_tile keeps region",
            "    t2 = meta.edge->leaves_tile() ? graphreader.GetGraphTile(meta.edge->endnode()) : tile;",
            "    // WEDRIVE leaves_tile keeps region: endnode прочитан из байтов тайла, регион\n"
            "    // берём у самого ребра — обычное ребро namespace не меняет.\n"
            "    t2 = meta.edge->leaves_tile()\n"
            "             ? graphreader.GetGraphTile(\n"
            "                   meta.edge->endnode().with_region(meta.edge_id.region()))\n"
            "             : tile;",
        ),
        # Транзишены между уровнями иерархии + порталы сразу за ними.
        (
            "WEDRIVE transition keeps region",
            "      graph_tile_ptr trans_tile = nullptr;\n"
            "      if ((!trans->up() && !ignore_hierarchy_limits_ &&\n"
            "           StopExpanding(hierarchy_limits[trans->endnode().level()], pred.distance())) ||\n"
            "          !(trans_tile = graphreader.GetGraphTile(trans->endnode()))) {\n"
            "        continue;\n"
            "      }\n\n"
            "      // setup for expansion at this level\n"
            "      hierarchy_limits[node.level()].set_up_transition_count(\n"
            "          hierarchy_limits[node.level()].up_transition_count() + trans->up());\n"
            "      const auto* trans_node = trans_tile->node(trans->endnode());\n"
            "      EdgeMetadata trans_meta =\n"
            "          EdgeMetadata::make(trans->endnode(), trans_node, trans_tile, edgestatus);",
            "      graph_tile_ptr trans_tile = nullptr;\n"
            "      // WEDRIVE transition keeps region: переход между уровнями иерархии остаётся\n"
            "      // внутри одного региона, поэтому тег наследуется от узла, из которого идём.\n"
            "      const GraphId trans_end = trans->endnode().with_region(node.region());\n"
            "      if ((!trans->up() && !ignore_hierarchy_limits_ &&\n"
            "           StopExpanding(hierarchy_limits[trans_end.level()], pred.distance())) ||\n"
            "          !(trans_tile = graphreader.GetGraphTile(trans_end))) {\n"
            "        continue;\n"
            "      }\n\n"
            "      // setup for expansion at this level\n"
            "      hierarchy_limits[node.level()].set_up_transition_count(\n"
            "          hierarchy_limits[node.level()].up_transition_count() + trans->up());\n"
            "      const auto* trans_node = trans_tile->node(trans_end);\n"
            "      EdgeMetadata trans_meta =\n"
            "          EdgeMetadata::make(trans_end, trans_node, trans_tile, edgestatus);",
        ),
        (
            "WEDRIVE portal expansion",
            "  // Now, after having looked at all the edges, including edges on other levels,\n"
            "  // we can say if this is a deadend or not, and if so, evaluate the uturn-edge (if it exists)\n"
            "  if (!disable_uturn && uturn_meta) {",
            "  // WEDRIVE portal expansion: ЕДИНСТВЕННОЕ место, которому разрешено сменить\n"
            "  // namespace. Портал — это не ребро внутри .gph, а внешняя запись, и обрабатывается\n"
            "  // он ровно тем же механизмом, что и переход между уровнями иерархии: мы просто\n"
            "  // раскрываем рёбра узла-близнеца в другом регионе. Регион приходит из portal.to,\n"
            "  // поэтому все построенные здесь EdgeLabel получают уже ЧУЖОЙ регион — что и есть\n"
            "  // пересечение границы.\n"
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
            "          EdgeMetadata::make(portal.to, portal_node, portal_tile, edgestatus);\n"
            "      uint32_t portal_shortcuts = 0;\n"
            "      for (uint32_t i = 0; i < portal_node->edge_count(); ++i, ++portal_meta) {\n"
            "        disable_uturn = ExpandInner<expansion_direction>(graphreader, pred, opp_pred_edge,\n"
            "                                                        portal_node, pred_idx, portal_meta,\n"
            "                                                        portal_shortcuts, portal_tile,\n"
            "                                                        offset_time) ||\n"
            "                        disable_uturn;\n"
            "      }\n"
            "    }\n"
            "  }\n\n"
            "  // Now, after having looked at all the edges, including edges on other levels,\n"
            "  // we can say if this is a deadend or not, and if so, evaluate the uturn-edge (if it exists)\n"
            "  if (!disable_uturn && uturn_meta) {",
        ),
    ],
)

print("\n   проверка по маркерам:")
for relpath, markers in (
    ("valhalla/baldr/graphreader.h", ["WEDRIVE atomic include"]),
    ("src/baldr/graphreader.cc", ["WEDRIVE region lost detector"]),
    (
        "src/thor/bidirectional_astar.cc",
        [
            "WEDRIVE leaves_tile keeps region",
            "WEDRIVE transition keeps region",
            "WEDRIVE portal expansion",
        ],
    ),
):
    s = io.open(os.path.join(SRC, relpath), encoding="utf-8").read()
    for m in markers:
        print("      %s %s" % ("ok     " if m in s else "MISSING", m))
