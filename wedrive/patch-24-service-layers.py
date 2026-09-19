"""WeDrive patch 24: два слоя ниже Thor, которые ломались на полном valhalla_service.

Odin специально не патчился заранее — запустили и посмотрели, где порвётся. Порвалось в двух
местах, и оба ровно того класса, который и ожидался: код ниже Thor принимает наши верхние биты
за часть обычного идентификатора Valhalla либо, наоборот, теряет их.

1. connectivity_map (ошибка 170 «Locations are in unconnected regions»)

   Он строится по ОДНОМУ каталогу тайлов и о порталах не знает в принципе. Для него точка в
   Румынии и точка в Молдове лежат в несвязанных компонентах — что чистая правда внутри одного
   графа и неправда для композита. Проверка пропускается, когда регионов больше одного: связность
   там обеспечивают порталы, а они уже проверены при загрузке (патч 21).

2. triplegbuilder (ошибка 599, NodeInfo index out of bounds: 3111,0,12034 nodecount= 3330)

   `startnode = directededge->endnode();` сохраняется БЕЗ региона и на следующей итерации по нему
   выбирается тайл: берётся молдавский (регион по умолчанию), а индекс приходит из румынского
   графа. Плюс ещё четыре места, где endnode идёт в выбор тайла.

   Регион всюду берётся у тайла или id, из которого ребро получено: обычное ребро namespace не
   меняет, менять его вправе только портал.
"""
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


print("   src/loki/route_action.cc")
patch(
    "src/loki/route_action.cc",
    [
        (
            "WEDRIVE connectivity skip",
            "  if (!connectivity_map) {\n    return;\n  }",
            "  // WEDRIVE connectivity skip: карта связности строится по одному каталогу тайлов и\n"
            "  // о порталах не знает, поэтому для композита её вердикт «несвязанные регионы»\n"
            "  // заведомо неверен. Связность обеспечивают порталы, проверенные при загрузке.\n"
            "  if (!connectivity_map || reader->RegionCount() > 1) {\n    return;\n  }",
        ),
    ],
)

print("   src/thor/triplegbuilder.cc")
patch(
    "src/thor/triplegbuilder.cc",
    [
        # ГЛАВНОЕ место: startnode переносится в следующую итерацию и по нему выбирается тайл.
        (
            "WEDRIVE startnode keeps region",
            "    // Set the endnode of this directed edge as the startnode of the next edge.\n"
            "    startnode = directededge->endnode();",
            "    // Set the endnode of this directed edge as the startnode of the next edge.\n"
            "    // WEDRIVE startnode keeps region: он живёт до следующей итерации, и по нему там\n"
            "    // ВЫБИРАЕТСЯ тайл. Без региона брался каталог по умолчанию, а индекс приходил из\n"
            "    // другого графа — отсюда NodeInfo index out of bounds на первом же переходе.\n"
            "    startnode = directededge->endnode().with_region(graphtile->id().region());",
        ),
        (
            "WEDRIVE end node tile region",
            "    graph_tile_ptr end_node_tile = graphtile;\n"
            "    graphreader.GetGraphTile(directededge->endnode(), end_node_tile);",
            "    graph_tile_ptr end_node_tile = graphtile;\n"
            "    // WEDRIVE end node tile region.\n"
            "    graphreader.GetGraphTile(directededge->endnode().with_region(\n"
            "                                 graphtile->id().region()),\n"
            "                             end_node_tile);",
        ),
        (
            "WEDRIVE opposing tile region",
            "      graph_tile_ptr t2 =\n"
            "          directededge->leaves_tile() ? graphreader.GetGraphTile(directededge->endnode()) : graphtile;",
            "      // WEDRIVE opposing tile region.\n"
            "      graph_tile_ptr t2 = directededge->leaves_tile()\n"
            "                              ? graphreader.GetGraphTile(\n"
            "                                    directededge->endnode().with_region(\n"
            "                                        graphtile->id().region()))\n"
            "                              : graphtile;",
        ),
        (
            "WEDRIVE elevation tile region",
            "  auto end_tile = graphreader.GetGraphTile(edge->endnode());",
            "  // WEDRIVE elevation tile region: регион у тайла, из которого взято ребро.\n"
            "  auto end_tile = graphreader.GetGraphTile(\n"
            "      edge->endnode().with_region(tile ? tile->id().region() : 0));",
        ),
        (
            "WEDRIVE transition tile region",
            "      GraphId endnode = trans->endnode();",
            "      // WEDRIVE transition tile region: переход между уровнями не меняет namespace.\n"
            "      GraphId endnode = trans->endnode().with_region(start_tile->id().region());",
        ),
        (
            "WEDRIVE first node region",
            "  auto first_tile = graphreader.GetGraphTile(first_edge->endnode());",
            "  // WEDRIVE first node region: регион берётся у id первого ребра пути.\n"
            "  const auto wedrive_begin_region = path_begin->edgeid.region();\n"
            "  auto first_tile =\n"
            "      graphreader.GetGraphTile(first_edge->endnode().with_region(wedrive_begin_region));",
        ),
    ],
)

print("\n   проверка:")
for relpath, markers in (
    ("src/loki/route_action.cc", ["WEDRIVE connectivity skip"]),
    (
        "src/thor/triplegbuilder.cc",
        [
            "WEDRIVE startnode keeps region",
            "WEDRIVE end node tile region",
            "WEDRIVE opposing tile region",
            "WEDRIVE elevation tile region",
            "WEDRIVE transition tile region",
            "WEDRIVE first node region",
        ],
    ),
):
    s = io.open(os.path.join(SRC, relpath), encoding="utf-8").read()
    for m in markers:
        print("      %s %s" % ("ok     " if m in s else "MISSING", m))
