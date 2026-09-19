"""WeDrive patch 33: разложить стоимость соединения на слагаемые и сравнить её с recost.

Установлено: композит выбирает соединение, которое СЧИТАЕТ дешевле (17916.6 против монолитных
18498.5), а фактический маршрут через него хуже. Но «насколько занижена оценка» пока не измерено —
отношение двух отношений на одном маршруте это не измерение.

Здесь печатается ровно то, что нужно, чтобы ответить:

  1. F  — стоимость forward-лейбла в точке встречи, с его регионом;
  2. R  — стоимость reverse-лейбла в точке встречи, с его регионом;
  3. correction — transition_cost, добавляемый при склейке;
  4. c = F + R + correction, то есть та самая оценка соединения;

и отдельно, уже после восстановления пути и recost ТОГО ЖЕ набора рёбер:

  5. recost(path) против оценки, и их разность.

Это даёт missing_cost напрямую, а не через пропорции.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

BREAKDOWN_OLD = (
    "  // WEDRIVE trace connection: каждое соединение, а не только первое. Место встречи и его\n"
    "  // стоимость — это и есть ответ на вопрос, почему выбран один путь, а не другой.\n"
    "  if (wedrive_debug_bidir() && ++wedrive_conn_count <= 12) {\n"
    "    auto t = graphreader.GetGraphTile(pred.edgeid());"
)

BREAKDOWN_NEW = (
    "  // WEDRIVE breakdown forward: слагаемые склейки. Наружу отдаётся только сумма, поэтому\n"
    "  // понять, какое из них недосчитано, можно лишь здесь.\n"
    "  if (wedrive_debug_bidir() && wedrive_conn_count < 12) {\n"
    "    const float f_part = (pred.predecessor() != kInvalidLabel)\n"
    "                             ? edgelabels_forward_[pred.predecessor()].cost().cost\n"
    "                             : pred.cost().cost;\n"
    "    std::cerr << \"WEDRIVE РАЗЛОЖЕНИЕ fwd: F=\" << f_part << \" (регион \"\n"
    "              << pred.edgeid().region() << \")  R=\" << opp_pred.cost().cost << \" (регион \"\n"
    "              << opp_pred.edgeid().region() << \")  correction=\"\n"
    "              << pred.transition_cost().cost << \"  = \" << c << std::endl;\n"
    "  }\n"
) + BREAKDOWN_OLD

# Якорь — сама вставка пути в результат: уникальна и не зависит от формулировок комментариев.
RECOST_OLD = "      paths.emplace_back(std::move(path));"

RECOST_NEW = (
    "      // WEDRIVE recost vs estimate: тот же набор рёбер, пересчитанный честно, против\n"
    "      // оценки, по которой это соединение было выбрано. Разность и есть искомая потеря.\n"
    "      if (wedrive_debug_bidir() && !path.empty()) {\n"
    "        std::cerr << \"WEDRIVE RECOST: оценка=\" << best_connection->cost\n"
    "                  << \"  recost=\" << path.back().elapsed_cost.cost << \"  разность=\"\n"
    "                  << (path.back().elapsed_cost.cost - best_connection->cost)\n"
    "                  << \"  рёбер=\" << path.size() << std::endl;\n"
    "      }\n"
) + RECOST_OLD


def edit(name, old, new):
    global s
    if name in s:
        print("      ok   уже применено: %s" % name)
        return
    n = s.count(old)
    assert n == 1, "%s: ожидал 1 совпадение, нашёл %d" % (name, n)
    s = s.replace(old, new)
    print("      +    %s" % name)


edit("WEDRIVE breakdown forward", BREAKDOWN_OLD, BREAKDOWN_NEW)
edit("WEDRIVE recost vs estimate", RECOST_OLD, RECOST_NEW)

io.open(P, "w", encoding="utf-8").write(s)

print("\n   проверка:")
s = io.open(P, encoding="utf-8").read()
for m in ("WEDRIVE breakdown forward", "WEDRIVE recost vs estimate"):
    print("      %s %s" % ("ok     " if m in s else "MISSING", m))
