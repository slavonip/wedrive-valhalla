"""WeDrive patch 34: диагностика патча 32 сама роняла маршрут.

Измерено прямо: без WEDRIVE_DEBUG_BIDIR композит выдаёт 469.423 км, с ним — ошибку сериализации.
То есть наблюдение меняло наблюдаемое.

Причина в самой печати: бралcя тайл РЕБРА, а координата спрашивалась у endnode —

    auto t = graphreader.GetGraphTile(pred.edgeid());
    ll = t->get_node_ll(pred.endnode());          // endnode может быть в СОСЕДНЕМ тайле

Для ребра, уходящего за границу тайла, это обращение по чужому индексу. В обычной сборке ассерты
выключены, поэтому вместо падения тут читался мусор, а роняло уже дальше по коду.

Правильно спрашивать тайл того узла, чью координату печатаем.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE trace tile fixed"

FWD_OLD = (
    "    auto t = graphreader.GetGraphTile(pred.edgeid());\n"
    "    midgard::PointLL ll;\n"
    "    if (t) {\n"
    "      ll = t->get_node_ll(pred.endnode());\n"
    "    }"
)
FWD_NEW = (
    "    // WEDRIVE trace tile fixed: тайл берётся у САМОГО узла, а не у ребра — endnode ребра,\n"
    "    // уходящего за границу тайла, живёт в соседнем.\n"
    "    auto t = graphreader.GetGraphTile(pred.endnode());\n"
    "    midgard::PointLL ll;\n"
    "    if (t) {\n"
    "      ll = t->get_node_ll(pred.endnode());\n"
    "    }"
)

REV_OLD = (
    "    auto t = graphreader.GetGraphTile(rev_pred.edgeid());\n"
    "    midgard::PointLL ll;\n"
    "    if (t) {\n"
    "      ll = t->get_node_ll(rev_pred.endnode());\n"
    "    }"
)
REV_NEW = (
    "    auto t = graphreader.GetGraphTile(rev_pred.endnode());\n"
    "    midgard::PointLL ll;\n"
    "    if (t) {\n"
    "      ll = t->get_node_ll(rev_pred.endnode());\n"
    "    }"
)

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for what, old in (("forward", FWD_OLD), ("reverse", REV_OLD)):
        assert s.count(old) == 1, "%s: ожидал 1 совпадение, нашёл %d" % (what, s.count(old))
    s = s.replace(FWD_OLD, FWD_NEW).replace(REV_OLD, REV_NEW)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s (2 куска)" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s тайл берётся у узла в обеих версиях"
      % ("ok     " if s.count("GetGraphTile(pred.endnode());") >= 1
                      and s.count("GetGraphTile(rev_pred.endnode());") >= 1 else "MISSING"))
print("      %s не осталось тайла-от-ребра в трассировке"
      % ("ok     " if "GetGraphTile(pred.edgeid());\n    midgard::PointLL" not in s else "MISSING"))
