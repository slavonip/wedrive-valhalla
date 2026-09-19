"""WeDrive patch 25: AreEdgesConnected — я сам пометил её безопасной, и ошибся.

При ревизии graphreader.cc эта функция была отнесена к «сравнение endnode с endnode, оба без
региона, значит консистентно». Это неверно по двум причинам, и обе видны только на композите.

1. Она ВЫБИРАЕТ ТАЙЛ. `is_transition` вызывает `GetGraphTile(n1)`, где n1 — сырой endnode без
   региона: берётся каталог по умолчанию, а индекс приходит из другого графа. Именно сюда
   указал backtrace детектора:

       WEDRIVE REGION LOST #0: level=1 tileid=49527 id=2634
         GraphReader::AreEdgesConnected(...)::{lambda}
         thor_worker_t::get_path_algorithm(...)

2. Хуже: сравнение `de1->endnode() == de2->endnode()` сопоставляет сырые 46-битные значения ИЗ
   РАЗНЫХ ГРАФОВ. Они вполне могут совпасть, будучи разными узлами разных стран — ровно та же
   коллизия, ради которой весь multi-region и затевался. Тогда функция отвечает «рёбра связаны»,
   и Thor уходит в тривиальный путь по двум несвязанным рёбрам.

Первое роняло процесс и потому было заметно. Второе молчаливо давало бы неверный маршрут.

Исправление: каждый endnode тегируется регионом СВОЕГО ребра, после чего и выбор тайла, и
сравнение становятся корректными: узлы разных регионов больше не равны.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/baldr/graphreader.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE connected keeps region"

OLD_TRANS = """      const NodeTransition* trans = tile->transition(ni->transition_index());
      for (uint32_t i = 0; i < ni->transition_count(); ++i, ++trans) {
        if (trans->endnode() == n2) {
          return true;
        }
      }"""
NEW_TRANS = """      const NodeTransition* trans = tile->transition(ni->transition_index());
      for (uint32_t i = 0; i < ni->transition_count(); ++i, ++trans) {
        // Переход между уровнями не меняет namespace — регион берём у узла, из которого идём.
        if (trans->endnode().with_region(n1.region()) == n2) {
          return true;
        }
      }"""

OLD_BODY = """  if (de1->endnode() == de2->endnode() || is_transition(de1->endnode(), de2->endnode())) {
    return true;
  }

  // Get opposing edge to de1
  const DirectedEdge* de1_opp = GetOpposingEdge(edge1, t1);
  if (de1_opp &&
      (de1_opp->endnode() == de2->endnode() || is_transition(de1_opp->endnode(), de2->endnode()))) {
    return true;
  }

  // Get opposing edge to de2 and compare to both edge1 endnodes
  const DirectedEdge* de2_opp = GetOpposingEdge(edge2, t2);
  return de1_opp && de2_opp &&
         (de2_opp->endnode() == de1->endnode() || de2_opp->endnode() == de1_opp->endnode() ||
          is_transition(de2_opp->endnode(), de1->endnode()) ||
          is_transition(de2_opp->endnode(), de1_opp->endnode()));"""

NEW_BODY = """  // WEDRIVE connected keeps region: каждый endnode тегируется регионом СВОЕГО ребра. Без этого
  // сырые 46-битные значения из разных графов могут совпасть — и функция ответит «связаны» про
  // два узла в разных странах, отправив Thor в тривиальный путь. А GetGraphTile внутри
  // is_transition взял бы каталог по умолчанию с индексом из чужого графа.
  const GraphId n1 = de1->endnode().with_region(edge1.region());
  const GraphId n2 = de2->endnode().with_region(edge2.region());
  if (n1 == n2 || is_transition(n1, n2)) {
    return true;
  }

  // Get opposing edge to de1
  const DirectedEdge* de1_opp = GetOpposingEdge(edge1, t1);
  // Противоположное ребро лежит в том же namespace, что и прямое.
  const GraphId n1_opp = de1_opp ? de1_opp->endnode().with_region(edge1.region()) : GraphId{};
  if (de1_opp && (n1_opp == n2 || is_transition(n1_opp, n2))) {
    return true;
  }

  // Get opposing edge to de2 and compare to both edge1 endnodes
  const DirectedEdge* de2_opp = GetOpposingEdge(edge2, t2);
  const GraphId n2_opp = de2_opp ? de2_opp->endnode().with_region(edge2.region()) : GraphId{};
  return de1_opp && de2_opp &&
         (n2_opp == n1 || n2_opp == n1_opp || is_transition(n2_opp, n1) ||
          is_transition(n2_opp, n1_opp));"""

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for what, old in (("is_transition", OLD_TRANS), ("тело", OLD_BODY)):
        assert s.count(old) == 1, "ожидал 1 совпадение для %s, нашёл %d" % (what, s.count(old))
    s = s.replace(OLD_TRANS, NEW_TRANS).replace(OLD_BODY, NEW_BODY)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s (2 куска)" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s endnode тегируются" % ("ok     " if "de1->endnode().with_region(edge1.region())" in s else "MISSING"))
print("      %s переход тегируется" % ("ok     " if "trans->endnode().with_region(n1.region())" in s else "MISSING"))
print("      %s не осталось сырых сравнений endnode"
      % ("ok     " if "de1->endnode() == de2->endnode()" not in s else "MISSING"))
