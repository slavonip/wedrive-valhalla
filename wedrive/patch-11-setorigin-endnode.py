"""WeDrive patch 11: последние два места, где endnode уходит в GetGraphTile без региона.

После патча 10 править надо ТОЛЬКО те места, где id выбирает тайл. Детектор показал ровно два
оставшихся: SetOrigin и EstimateReverseStartTime. В обоих рядом лежит edgeid, полученный из
корреляции Location, и он тегнут — регион берём оттуда.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

EDITS = [
    (
        "WEDRIVE SetOrigin endnode region",
        "    graph_tile_ptr endtile = graphreader.GetGraphTile(directededge->endnode());",
        "    // WEDRIVE SetOrigin endnode region: endnode из байтов тайла, регион у edgeid.\n"
        "    graph_tile_ptr endtile =\n"
        "        graphreader.GetGraphTile(directededge->endnode().with_region(edgeid.region()));",
    ),
    (
        "WEDRIVE reverse start endnode region",
        "  graph_tile_ptr endtile = reader.GetGraphTile(directededge->endnode());",
        "  // WEDRIVE reverse start endnode region: то же самое на обратной стороне поиска.\n"
        "  graph_tile_ptr endtile =\n"
        "      reader.GetGraphTile(directededge->endnode().with_region(edgeid.region()));",
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
print("      %s не осталось GetGraphTile(directededge->endnode()) без региона"
      % ("ok     " if "GetGraphTile(directededge->endnode())" not in s else "MISSING"))
