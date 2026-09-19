"""WeDrive patch 17: последняя потеря региона — recost_forward.

Поиск пути уже сохранял namespace (44348 -> 1). Оставшаяся потеря возникала ПОСЛЕ нахождения
пути, на финальном пересчёте стоимости, в единственном месте recost.cc:

    node = edge ? reader.nodeinfo(edge->endnode(), tile) : nullptr;

`edge->endnode()` прочитан из байтов тайла и региона не несёт, а `nodeinfo()` по этому id
ВЫБИРАЕТ тайл — то есть это ровно тот случай, где регион обязателен. Регион берётся у ребра,
по которому мы в этот узел пришли: обычное ребро namespace не меняет.

Остальные обращения в recost.cc идут по `edge_id`, который приходит из уже построенного пути
и тегнут, поэтому больше здесь править нечего. Тегировать recosting целиком не нужно и вредно:
внутри уже выбранного тайла region 0 допустим.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/sif/recost.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE recost keeps region"
OLD = "    node = edge ? reader.nodeinfo(edge->endnode(), tile) : nullptr;"
NEW = (
    "    // WEDRIVE recost keeps region: endnode из байтов тайла, а nodeinfo() по нему ВЫБИРАЕТ\n"
    "    // тайл. Регион наследуем от ребра, по которому пришли.\n"
    "    node = edge ? reader.nodeinfo(edge->endnode().with_region(edge_id.region()), tile)\n"
    "                : nullptr;"
)

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    n = s.count(OLD)
    assert n == 1, "ожидал 1 совпадение, нашёл %d" % n
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s %s" % ("ok     " if NAME in s else "MISSING", NAME))
print("      %s не осталось nodeinfo(edge->endnode()) без региона"
      % ("ok     " if "reader.nodeinfo(edge->endnode(), tile)" not in s else "MISSING"))
print("\n   ревизия остальных обращений в recost.cc (должны идти по тегнутому edge_id):")
for i, line in enumerate(s.split("\n"), 1):
    if "reader." in line and ("directededge" in line or "nodeinfo" in line):
        print("      %4d  %s" % (i, line.strip()[:88]))
