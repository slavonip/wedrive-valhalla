"""WeDrive patch 39: одно и то же ли ребро видят два дерева в точке встречи.

Расследование сошлось к одной паре идентификаторов. Формула склейки

    c = F + R + correction

верна лишь если forward и reverse встретились на ОДНОМ ребре: forward доходит до его начала,
reverse проходит его в обратную сторону. Измерено, что стоимость ребра встречи (шорткат 28 км,
1112.25) не учтена ни в одной половине.

Печатаются все атрибуты обеих сторон и две проверки:

    pred.opp_edgeid() == opp_pred.edgeid()                      с регионом
    pred.opp_edgeid().without_region() == ... .without_region() без региона

Результат разделяет задачу надвое:

  равны без региона, но не равны с ним -> наш патч неправильно протащил регион через
      противоположный шорткат, исправление локальное;
  не равны и без региона -> деревья встретились на РАЗНЫХ представлениях одной дороги
      (шорткат против составляющих рёбер), и обычную формулу к такой паре применять нельзя.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

ANCHOR = (
    "  // WEDRIVE chain trace: цепочка предшественников forward от точки встречи назад. Стоимость\n"
    "  // обязана расти монотонно; просадка на смене региона означала бы потерю накопленного.\n"
)

IDENT = (
    "  // WEDRIVE meeting edge identity: одно ли ребро видят два дерева в точке встречи.\n"
    "  if (wedrive_debug_bidir() && wedrive_conn_count < 4) {\n"
    "    auto wd_info = [&graphreader](const char* wd_tag, const baldr::GraphId& wd_id) {\n"
    "      graph_tile_ptr wd_t;\n"
    "      bool wd_sc = false;\n"
    "      uint32_t wd_len = 0;\n"
    "      if (graphreader.GetGraphTile(wd_id, wd_t) && wd_t &&\n"
    "          wd_id.id() < wd_t->header()->directededgecount()) {\n"
    "        const auto* wd_de = wd_t->directededge(wd_id);\n"
    "        wd_sc = wd_de->is_shortcut();\n"
    "        wd_len = wd_de->length();\n"
    "      }\n"
    "      std::cerr << \"    \" << wd_tag << \" val=\" << wd_id.value << \" регион=\" << wd_id.region()\n"
    "                << \" level=\" << wd_id.level() << \" tile=\" << wd_id.tileid() << \" id=\"\n"
    "                << wd_id.id() << \" shortcut=\" << (wd_sc ? 1 : 0) << \" length=\" << wd_len\n"
    "                << std::endl;\n"
    "    };\n"
    "    std::cerr << \"WEDRIVE MEETING #\" << (wedrive_conn_count + 1) << std::endl;\n"
    "    wd_info(\"fwd.edgeid    \", pred.edgeid());\n"
    "    wd_info(\"fwd.opp_edgeid\", pred.opp_edgeid());\n"
    "    std::cerr << \"    fwd.cost=\" << pred.cost().cost << std::endl;\n"
    "    wd_info(\"rev.edgeid    \", opp_pred.edgeid());\n"
    "    wd_info(\"rev.opp_edgeid\", opp_pred.opp_edgeid());\n"
    "    std::cerr << \"    rev.cost=\" << opp_pred.cost().cost << std::endl;\n"
    "    const bool wd_eq = pred.opp_edgeid() == opp_pred.edgeid();\n"
    "    const bool wd_eq_nr =\n"
    "        pred.opp_edgeid().without_region() == opp_pred.edgeid().without_region();\n"
    "    std::cerr << \"    ПРОВЕРКА: с регионом \" << (wd_eq ? \"РАВНЫ\" : \"НЕ РАВНЫ\")\n"
    "              << \", без региона \" << (wd_eq_nr ? \"РАВНЫ\" : \"НЕ РАВНЫ\") << std::endl;\n"
    "  }\n"
) + ANCHOR

NAME = "WEDRIVE meeting edge identity"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(ANCHOR) == 1, "не нашёл якорь chain trace"
    io.open(P, "w", encoding="utf-8").write(s.replace(ANCHOR, IDENT))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s обе проверки равенства"
      % ("ok     " if "without_region() == opp_pred.edgeid().without_region()" in s else "MISSING"))
