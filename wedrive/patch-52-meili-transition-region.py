"""WeDrive patch 52: переход между уровнями внутри Meili теряет регион.

Гистограмма после multiplex'а: region 0 = 97817, region 1 = 9594, region 2 = 0. Кандидаты и
origin/destination тегируются правильно — GetDirectedEdgeNodes регион сохраняет ещё с патчей 12
и 28, — а узлов без региона всё равно подавляющее большинство.

Источник ровно один и того же вида, что уже ловился в Thor трижды: идентификатор, прочитанный из
тайла напрямую, отдаётся наружу как узел для дальнейшего расширения.

    expand(trans->endnode(), label_idx, true);

NodeTransition хранит endnode так, как его записал Mjolnir, — без namespace. Патч 47 пометил
edgeid и endnode ребра, но переход между уровнями пропустил, и каждый подъём или спуск по
иерархии обнулял регион для всего поддерева расширения.

Переход между уровнями региона НЕ меняет: это тот же граф, другой уровень. Значит тег берётся у
узла, из которого переход исходит.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/routing.cc")
s = io.open(P, encoding="utf-8").read()

OLD = "        expand(trans->endnode(), label_idx, true);\n"
NEW = (
    "        // WEDRIVE meili region: переход между уровнями региона не меняет — это тот же\n"
    "        // граф. Но endnode прочитан из тайла и намespace не несёт, а уходит он наружу\n"
    "        // узлом для дальнейшего расширения.\n"
    "        expand(trans->endnode().with_region(node.region()), label_idx, true);\n"
)

NAME = "WEDRIVE meili region: переход между уровнями"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл рекурсивный вызов по переходу"
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("переход тегируется", "expand(trans->endnode().with_region(node.region()), label_idx, true);", True),
    ("нетегированного перехода не осталось", "expand(trans->endnode(), label_idx, true);", False),
    ("портал по-прежнему на месте", "expand(portal.to, label_idx, true);", True),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
