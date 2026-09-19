"""WeDrive patch 38: пройти цепочку forward-лейблов от точки встречи назад.

Ключевое измерение патча 37: путь пересчитывается СОГЛАСОВАННО — сумма EdgeCost + transition по
всем 993 рёбрам равна recost с точностью до 16 единиц, и на шве регионов скачка нет вовсе.

Значит недосчёт 1234.44 рождается не вдоль пути, а в самой оценке соединения:

    c = F + R + correction = 7147.72 + 10765.8 + 3 = 17916.6
    фактическая стоимость того же пути = 19151

То есть одна из половин занижена примерно на 1234. Forward проходит через портал, reverse — нет
(rev = 0 раскрытий), поэтому подозрение на forward.

Здесь цепочка предшественников forward-лейблов обходится назад от точки встречи, и печатается
стоимость по обе стороны каждой смены региона. Накопленная стоимость обязана расти монотонно от
начала к точке встречи; если на портальном переходе она проседает, это и есть потеря.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

ANCHOR = (
    "  // WEDRIVE breakdown forward: слагаемые склейки. Наружу отдаётся только сумма, поэтому\n"
    "  // понять, какое из них недосчитано, можно лишь здесь.\n"
    "  if (wedrive_debug_bidir() && wedrive_conn_count < 12) {"
)

CHAIN = (
    "  // WEDRIVE chain trace: цепочка предшественников forward от точки встречи назад. Стоимость\n"
    "  // обязана расти монотонно; просадка на смене региона означала бы потерю накопленного.\n"
    "  if (wedrive_debug_bidir() && wedrive_conn_count < 4) {\n"
    "    uint32_t wd_idx = pred.predecessor();\n"
    "    uint32_t wd_reg = pred.edgeid().region();\n"
    "    float wd_cost = pred.cost().cost;\n"
    "    size_t wd_n = 0;\n"
    "    size_t wd_seams = 0;\n"
    "    while (wd_idx != kInvalidLabel && wd_n < 5000) {\n"
    "      const auto& wd_l = edgelabels_forward_[wd_idx];\n"
    "      const uint32_t wd_r = wd_l.edgeid().region();\n"
    "      if (wd_r != wd_reg) {\n"
    "        ++wd_seams;\n"
    "        std::cerr << \"WEDRIVE CHAIN шов на шаге \" << wd_n << \": регион \" << wd_r << \"->\"\n"
    "                  << wd_reg << \"  cost \" << wd_l.cost().cost << \" -> \" << wd_cost\n"
    "                  << \"  (прирост \" << (wd_cost - wd_l.cost().cost) << \")\" << std::endl;\n"
    "      }\n"
    "      wd_reg = wd_r;\n"
    "      wd_cost = wd_l.cost().cost;\n"
    "      wd_idx = wd_l.predecessor();\n"
    "      ++wd_n;\n"
    "    }\n"
    "    std::cerr << \"WEDRIVE CHAIN: шагов \" << wd_n << \"  швов \" << wd_seams\n"
    "              << \"  стоимость в начале цепочки \" << wd_cost\n"
    "              << \"  в точке встречи \" << pred.cost().cost << std::endl;\n"
    "  }\n"
) + ANCHOR

NAME = "WEDRIVE chain trace"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(ANCHOR) == 1, "не нашёл якорь разложения"
    io.open(P, "w", encoding="utf-8").write(s.replace(ANCHOR, CHAIN))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s обход цепочки" % ("ok     " if "wd_l.predecessor()" in s else "MISSING"))
