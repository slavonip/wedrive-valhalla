"""WeDrive patch 12: последние три места в GraphReader, где endnode выбирает тайл.

Детектор показал level=0 — а на нулевом уровне живут шорткаты, и действительно GetShortcut
переходит по cont_de->endnode() в соседний тайл, не зная про регион. Ещё два таких же места —
GetEdgeDensity и GetDirectedEdgeNodes.

Во всех трёх регион берётся из того, что у функции уже есть на руках: входной edgeid или тайл,
из которого пришло ребро. Обычное ребро namespace не меняет — менять его вправе только портал.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/baldr/graphreader.cc")
s = io.open(P, encoding="utf-8").read()

EDITS = [
    # GetShortcut: идёт по продолжающему ребру в соседний тайл на верхнем уровне иерархии.
    (
        "WEDRIVE shortcut keeps region",
        "    GraphId endnode = cont_de->endnode();",
        "    // WEDRIVE shortcut keeps region: шорткаты живут на уровнях 0/1, и переход по\n"
        "    // продолжающему ребру уводил в тайл соседнего региона с тем же именем файла.\n"
        "    GraphId endnode = cont_de->endnode().with_region(id.region());",
    ),
    # GetEdgeDensity: смотрит плотность у узла на конце противоположного ребра.
    (
        "WEDRIVE density keeps region",
        "    GraphId id = opp_edge->endnode();",
        "    // WEDRIVE density keeps region.\n"
        "    GraphId id = opp_edge->endnode().with_region(edgeid.region());",
    ),
    # GetDirectedEdgeNodes: регион надо снять с тайла ДО того, как его move-нут.
    (
        "WEDRIVE edge nodes keep region",
        "  GraphId end_node = edge->endnode();",
        "  // WEDRIVE edge nodes keep region: tile ниже уходит в std::move, поэтому регион\n"
        "  // снимаем с него сейчас.\n"
        "  const uint32_t wedrive_region = tile ? tile->id().region() : 0;\n"
        "  GraphId end_node = edge->endnode().with_region(wedrive_region);",
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
# start_node внутри GetDirectedEdgeNodes читает endnode уже из тайла t2 — там регион не нужен,
# id используется только для индексации, а ассерт из патча 10 такое пропускает.
print("      (start_node внутри t2 не тегируем: индексация внутри уже правильного тайла)")
