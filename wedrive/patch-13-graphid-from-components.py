"""WeDrive patch 13: GraphId, СОБРАННЫЙ из компонентов, теряет регион так же, как прочитанный.

Патчи 11-12 закрыли чтения endnode. Но детектор продолжал ругаться на level 0, и причина —
другая форма той же ошибки: GetShortcut не только ходит по endnode, он ещё СТРОИТ новый id
конструктором {tileid, level, index}, который про регион ничего не знает.

Это отдельный класс мест, и его стоит держать в голове: тег теряется и при чтении из байтов,
и при сборке id из частей. Ровно поэтому EdgeMetadata::make понадобился патч 6.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/baldr/graphreader.cc")
s = io.open(P, encoding="utf-8").read()

EDITS = [
    (
        "WEDRIVE shortcut edgeid keeps region",
        "    edgeid = {endnode.tileid(), endnode.level(), idx};",
        "    // WEDRIVE shortcut edgeid keeps region: конструктор из компонентов региона не несёт.\n"
        "    edgeid = GraphId(endnode.tileid(), endnode.level(), idx).with_region(endnode.region());",
    ),
    (
        "WEDRIVE shortcut result keeps region",
        "      return GraphId(endnode.tileid(), endnode.level(), idx);",
        "      // WEDRIVE shortcut result keeps region.\n"
        "      return GraphId(endnode.tileid(), endnode.level(), idx).with_region(endnode.region());",
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
