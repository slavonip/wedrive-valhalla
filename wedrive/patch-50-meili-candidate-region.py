"""WeDrive patch 50: пространственный индекс Meili становится region-aware.

Гистограмма патча 49: все 37407 узлов внутри Meili несут region 0, и 26 из них нашлись бы в
таблице порталов, будь они помечены регионом 1 или 2. То есть Meili целиком живёт в namespace по
умолчанию и видит ровно один граф — отсюда 638 сопоставленных точек из 770.

Причина в том, что свой поиск кандидатов у Meili region про не знает ничего, и внутри него
обнаружился ЧЕТВЁРТЫЙ namespace-unaware контейнер — после FlatTileCache, EdgeStatus и
shortcut_recovery_t:

    mutable std::unordered_map<int32_t, grid_t> grid_cache_;   // candidate_search.h

Ключ — bin_id, чистая география: один и тот же квадрат имеет один и тот же номер в каждом
регионе. Под multiplex'ом это означало бы, что сетка Молдовы возвращается Румынии, — ровно тот
дефект, который уже был закрыт в FlatTileCache, в новом месте.

Три правки, все в одном механизме:

1. Ключ сетки получает регион. bin_id остаётся географией, а namespace добавляется сверху.
2. Тайл, из которого сетка строится, выбирается по ТЕКУЩЕМУ региону области видимости, а не
   безымянным нулём.
3. Идентификаторы рёбер, попадающие в сетку, тегируются регионом своего тайла: именно они
   возвращаются наружу как кандидаты и дальше выбирают тайлы.

Сам multiplex — следующий патч. Без этого он был бы вреден.
"""
import io
import os

SRC = "/src/valhalla"
H = os.path.join(SRC, "valhalla/meili/candidate_search.h")
C = os.path.join(SRC, "src/meili/candidate_search.cc")

NAME = "WEDRIVE meili grid key"

h = io.open(H, encoding="utf-8").read()
c = io.open(C, encoding="utf-8").read()

# --- заголовок: тип ключа ------------------------------------------------------------------
H_OLD = "  mutable std::unordered_map<int32_t, grid_t> grid_cache_;\n"
H_NEW = (
    "  // WEDRIVE meili grid key: bin_id — чистая география, и один и тот же квадрат имеет\n"
    "  // один и тот же номер в каждом регионе. Ключ расширен, чтобы сетка одного графа не\n"
    "  // возвращалась другому.\n"
    "  mutable std::unordered_map<int64_t, grid_t> grid_cache_;\n"
)

# --- .cc: ключ, тайл, теги на рёбрах --------------------------------------------------------
KEY_HELPER = (
    "// WEDRIVE meili grid key: namespace поверх географии.\n"
    "inline int64_t WeDriveBinKey(const int32_t bin_id) {\n"
    "  return (static_cast<int64_t>(baldr::GraphReader::ScopeRegion()) << 32) |\n"
    "         static_cast<int64_t>(static_cast<uint32_t>(bin_id));\n"
    "}\n"
    "\n"
    "void IndexBin(const baldr::graph_tile_ptr& tile,\n"
)
KEY_HELPER_OLD = "void IndexBin(const baldr::graph_tile_ptr& tile,\n"

FIND_OLD = "  const auto it = grid_cache_.find(bin_id);\n"
FIND_NEW = "  const auto it = grid_cache_.find(WeDriveBinKey(bin_id));\n"

EMPLACE_OLD = (
    "  const auto inserted =\n"
    "      grid_cache_.emplace(bin_id, grid_t(tile->BoundingBox(), cell_width_, cell_height_));\n"
)
EMPLACE_NEW = (
    "  const auto inserted = grid_cache_.emplace(WeDriveBinKey(bin_id),\n"
    "                                            grid_t(tile->BoundingBox(), cell_width_,\n"
    "                                                   cell_height_));\n"
)

TILEID_OLD = "  baldr::GraphId tileid(tile_id, bin_level_, 0);\n"
TILEID_NEW = (
    "  // WEDRIVE meili region: сетка строится из тайла ТЕКУЩЕЙ области видимости.\n"
    "  baldr::GraphId tileid =\n"
    "      baldr::GraphId(tile_id, bin_level_, 0).with_region(baldr::GraphReader::ScopeRegion());\n"
)

SEG_OLD = (
    "    auto shape = bin_tile->edgeinfo(bin_tile->directededge(edge_id)).lazy_shape();\n"
)
SEG_NEW = (
    "    // WEDRIVE meili region: в сетку кладётся тегированный id — он уходит наружу\n"
    "    // кандидатом и дальше сам выбирает тайлы.\n"
    "    const baldr::GraphId wd_edge_id = edge_id.with_region(bin_tile->id().region());\n"
    "    auto shape = bin_tile->edgeinfo(bin_tile->directededge(edge_id)).lazy_shape();\n"
)

ADD_OLD = "        grid.AddLineSegment(edge_id, {u, v});\n"
ADD_NEW = "        grid.AddLineSegment(wd_edge_id, {u, v});\n"

if NAME in h and NAME in c:
    print("      ok   уже применено: %s" % NAME)
else:
    assert h.count(H_OLD) == 1, "не нашёл объявление grid_cache_"
    for label, old in (("IndexBin", KEY_HELPER_OLD), ("find", FIND_OLD), ("emplace", EMPLACE_OLD),
                       ("tileid", TILEID_OLD), ("shape", SEG_OLD), ("AddLineSegment", ADD_OLD)):
        assert c.count(old) == 1, "не нашёл якорь: %s" % label
    io.open(H, "w", encoding="utf-8").write(h.replace(H_OLD, H_NEW))
    c = (c.replace(KEY_HELPER_OLD, KEY_HELPER)
          .replace(FIND_OLD, FIND_NEW)
          .replace(EMPLACE_OLD, EMPLACE_NEW)
          .replace(TILEID_OLD, TILEID_NEW)
          .replace(SEG_OLD, SEG_NEW)
          .replace(ADD_OLD, ADD_NEW))
    io.open(C, "w", encoding="utf-8").write(c)
    print("      +    %s" % NAME)

h = io.open(H, encoding="utf-8").read()
c = io.open(C, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    (h, "ключ сетки расширен", "std::unordered_map<int64_t, grid_t> grid_cache_;", True),
    (c, "ключ считается с регионом", "WeDriveBinKey(const int32_t bin_id)", True),
    (c, "find по новому ключу", "grid_cache_.find(WeDriveBinKey(bin_id))", True),
    (c, "emplace по новому ключу", "grid_cache_.emplace(WeDriveBinKey(bin_id)", True),
    (c, "тайл берётся по области видимости", "with_region(baldr::GraphReader::ScopeRegion())", True),
    (c, "в сетку кладётся тегированный id", "grid.AddLineSegment(wd_edge_id", True),
    (c, "нетегированный id в сетку не попадает", "grid.AddLineSegment(edge_id", False),
)
for text, label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in text) == want else "MISSING", label))
