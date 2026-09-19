"""WeDrive patch 16: третий и последний GraphId-аксессор лейбла — BDEdgeLabel::opp_edgeid().

Патч 6 сделал region-aware edgeid() и endnode() в EdgeLabel. Но у BDEdgeLabel, который и
используется двунаправленным поиском, есть СВОЙ третий id — противоположное ребро, — и он
возвращался без региона. Обратное дерево обращается к нему на каждом шаге, отсюда и 44 348
потерь именно на направлении Яссы -> Кишинёв, против единиц на прямом.

Ревизия (как и с самим GraphId, чтобы не чинить по одному): GraphId-аксессоров во всех
классах лейблов ровно три — edgeid(), endnode(), opp_edgeid(). После этого патча покрыты все.

Противоположное ребро всегда лежит в ТОМ ЖЕ регионе, что и прямое: это одна и та же физическая
дорога. Регион меняет только портал, и он строит свои лейблы отдельно.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/sif/edgelabel.h")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE tagged opp_edgeid"
OLD = "  baldr::GraphId opp_edgeid() const {\n    return baldr::GraphId(opp_edgeid_);\n  }"
NEW = (
    "  baldr::GraphId opp_edgeid() const {\n"
    "    // WEDRIVE tagged opp_edgeid: третий id лейбла. Обратное дерево двунаправленного\n"
    "    // поиска читает его на каждом шаге, поэтому без тега оно теряло namespace лавинообразно.\n"
    "    // Противоположное ребро — та же физическая дорога, значит тот же регион.\n"
    "    return baldr::GraphId(opp_edgeid_).with_region(region());\n  }"
)

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    n = s.count(OLD)
    assert n == 1, "ожидал 1 совпадение, нашёл %d" % n
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   ревизия всех GraphId-аксессоров лейблов:")
import re

for m in re.finditer(r"baldr::GraphId ([a-z_]+)\(\) const \{\n(?:.*\n)*?\s*return ([^\n]+)\n", s):
    name, body = m.group(1), m.group(2).strip()
    ok = "with_region" in body
    print("      %s %-12s -> %s" % ("ok     " if ok else "БЕЗ РЕГИОНА", name, body[:60]))
