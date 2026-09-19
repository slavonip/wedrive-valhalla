"""WeDrive patch 20: recost на стыке регионов. Исправляет дефект патча 17.

Патч 17 написал так:

    node = edge ? reader.nodeinfo(edge->endnode().with_region(edge_id.region()), tile) : nullptr;

и это неверно. В цикле recost_forward на входе итерации `edge` — ребро ПРЕДЫДУЩЕЕ, а `edge_id` —
id ТЕКУЩЕГО: сам `edge` обновляется строкой ниже. Внутри одного региона разница незаметна,
потому что регион у всех рёбер один.

На стыке через портал предыдущее ребро лежит в регионе 1, текущее — в регионе 2. Узел региона 1
получал тег региона 2: тайл брался румынский, а индекс узла оставался молдавским —

    GraphTile NodeInfo index out of bounds: 3111,0,20495 nodecount= 3330

причём при region lost = 0, потому что регион не терялся, он был проставлен НЕВЕРНЫЙ. Это и есть
причина, по которой большая таблица порталов ломала recost: чем больше переходов, тем вероятнее
попасть индексом за границу чужого тайла. С одним переходом иногда «везло».

Исправление двойное:

1. Регион для endnode берётся у ПРЕДЫДУЩЕГО ребра, как и положено.
2. На самом стыке `node` не используется вовсе. Портал соединяет две копии ОДНОЙ точки в разных
   namespace, поэтому поворота там нет: transition cost равен нулю, а обращаться к NodeInfo
   чужого тайла нельзя в принципе. Это тот же приём, что и для первого ребра пути, где node тоже
   отсутствует.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/sif/recost.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE recost portal seam"

OLD_DECL = """  PathEdgeLabel label;
  uint32_t predecessor = baldr::kInvalidLabel;"""
NEW_DECL = """  PathEdgeLabel label;
  // WEDRIVE recost portal seam: регион РЕБРА, а не следующего за ним id. `edge` в цикле ниже
  // отстаёт от `edge_id` на шаг, и на границе регионов это разные namespace.
  uint32_t wedrive_edge_region = 0;
  uint32_t predecessor = baldr::kInvalidLabel;"""

OLD_NODE = """    node = edge ? reader.nodeinfo(edge->endnode().with_region(edge_id.region()), tile)
                : nullptr;
    if (edge && !node) {
      throw std::runtime_error("Node cannot be found");
    }"""
NEW_NODE = """    // Стык двух регионов: узел предыдущего ребра существует только в СВОЁМ графе, а дальше
    // путь продолжается в чужом. Портал — это одна и та же точка в двух namespace, поворота в
    // ней нет, поэтому node здесь не нужен и брать его из чужого тайла нельзя.
    const bool wedrive_seam = edge && wedrive_edge_region != edge_id.region();
    node = (edge && !wedrive_seam)
               ? reader.nodeinfo(edge->endnode().with_region(wedrive_edge_region), tile)
               : nullptr;
    if (edge && !wedrive_seam && !node) {
      throw std::runtime_error("Node cannot be found");
    }"""

OLD_ADVANCE = """    // next edge
    edge_id = next_id;"""
NEW_ADVANCE = """    // next edge
    wedrive_edge_region = edge_id.region();
    edge_id = next_id;"""

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for what, old in (("declaration", OLD_DECL), ("node", OLD_NODE), ("advance", OLD_ADVANCE)):
        assert s.count(old) == 1, "ожидал 1 совпадение для %s, нашёл %d" % (what, s.count(old))
    s = s.replace(OLD_DECL, NEW_DECL).replace(OLD_NODE, NEW_NODE).replace(OLD_ADVANCE, NEW_ADVANCE)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s (3 куска)" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s регион берётся у предыдущего ребра"
      % ("ok     " if "with_region(wedrive_edge_region)" in s else "MISSING"))
print("      %s стык обнаруживается" % ("ok     " if "wedrive_seam" in s else "MISSING"))
print("      %s регион продвигается вместе с edge_id"
      % ("ok     " if "wedrive_edge_region = edge_id.region();" in s else "MISSING"))
print("      %s не осталось ошибочного тега из патча 17"
      % ("ok     " if "with_region(edge_id.region()), tile)" not in s else "MISSING"))
