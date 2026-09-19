"""WeDrive patch 19: region scope — чтобы Loki не пришлось патчить вообще.

Loki строит идентификаторы тайлов сам:

    auto tile_id = GraphId(tile_index, TileHierarchy::levels().back().level, 0);
    reader.GetGraphTile(tile_id, cur_tile);

то есть БЕЗ региона, и все производные id тоже без региона. Протаскивать регион через
loki::Search означало бы править его внутренности — ровно то, чего мы избегали в Thor.

Вместо этого GraphReader получает понятие «регион по умолчанию для нетегнутых id», включаемый
RAII-объектом. Тогда Loki запускается ПО РАЗУ НА РЕГИОН, каждый раз видя ровно один граф, а
вызывающий код тегирует полученных кандидатов и складывает их в общий набор. Ни одной строки в
loki/ менять не нужно.

Важно: scope НЕ выбирает регион за пользователя. Он лишь говорит, в каком графе идёт текущий
проход поиска. Если точка попадает в перекрытие двух регионов, проходов будет два и кандидаты
вернутся из обоих — решать, каким пользоваться, будет Thor по стоимости.
"""
import io
import os

SRC = "/src/valhalla"


def patch(relpath, edits):
    p = os.path.join(SRC, relpath)
    s = io.open(p, encoding="utf-8").read()
    changed = False
    for name, old, new in edits:
        if name in s:
            print("      ok   уже применено: %s" % name)
            continue
        n = s.count(old)
        assert n == 1, "%s: ожидал 1 совпадение для %s, нашёл %d" % (relpath, name, n)
        s = s.replace(old, new)
        changed = True
        print("      +    %s" % name)
    if changed:
        io.open(p, "w", encoding="utf-8").write(s)


print("   valhalla/baldr/graphreader.h")
patch(
    "valhalla/baldr/graphreader.h",
    [
        (
            "WEDRIVE region scope",
            "  /** WEDRIVE portal table: одна запись на направление; две записи делают переход",
            "  /**\n"
            "   * WEDRIVE region scope: в каком регионе считать НЕТЕГНУТЫЕ id.\n"
            "   *\n"
            "   * Существует ради Loki, который конструирует id тайлов сам и о регионах не знает.\n"
            "   * Поиск кандидатов запускается по разу на регион внутри такого scope, и каждый\n"
            "   * проход видит ровно один граф. Тегирование результатов — забота вызывающего.\n"
            "   *\n"
            "   * thread_local, потому что GraphReader разделяется между потоками, а scope\n"
            "   * принадлежит одному конкретному проходу поиска.\n"
            "   */\n"
            "  class RegionScope {\n"
            "  public:\n"
            "    explicit RegionScope(const uint32_t region) : previous_(wedrive_scope_region_) {\n"
            "      wedrive_scope_region_ = region;\n"
            "    }\n"
            "    ~RegionScope() {\n"
            "      wedrive_scope_region_ = previous_;\n"
            "    }\n"
            "    RegionScope(const RegionScope&) = delete;\n"
            "    RegionScope& operator=(const RegionScope&) = delete;\n"
            "\n"
            "  private:\n"
            "    uint32_t previous_;\n"
            "  };\n"
            "\n"
            "  static uint32_t ScopeRegion() {\n"
            "    return wedrive_scope_region_;\n"
            "  }\n"
            "\n"
            "  /** WEDRIVE portal table: одна запись на направление; две записи делают переход",
        ),
        (
            "WEDRIVE scope member",
            "  static inline std::atomic<uint64_t> wedrive_region_lost_{0};",
            "  static inline std::atomic<uint64_t> wedrive_region_lost_{0};\n"
            "  // WEDRIVE scope member: активный регион текущего прохода поиска, 0 = нет.\n"
            "  static inline thread_local uint32_t wedrive_scope_region_{0};",
        ),
    ],
)

print("   src/baldr/graphreader.cc")
patch(
    "src/baldr/graphreader.cc",
    [
        # Детектор не должен ругаться, когда scope сознательно задаёт регион.
        (
            "WEDRIVE detector respects scope",
            "  if (wedrive_region_dirs_.size() > 1 && graphid.region() == 0) {",
            "  if (wedrive_region_dirs_.size() > 1 && graphid.region() == 0 &&\n"
            "      wedrive_scope_region_ == 0) { // WEDRIVE detector respects scope",
        ),
        # Единственная точка, где нетегнутый id получает регион из scope: выбор тайла.
        (
            "WEDRIVE scope applies to tile choice",
            "  // Check if the level/tileid combination is in the cache\n"
            "  auto base = graphid.tile_base();",
            "  // Check if the level/tileid combination is in the cache\n"
            "  // WEDRIVE scope applies to tile choice: нетегнутый id внутри scope относится к\n"
            "  // региону этого прохода. Один раз здесь — и кеш, и выбор каталога ниже уже\n"
            "  // работают с правильным регионом, потому что оба идут от base.\n"
            "  auto base = graphid.tile_base();\n"
            "  if (base.region() == 0 && wedrive_scope_region_ != 0) {\n"
            "    base = base.with_region(wedrive_scope_region_);\n"
            "  }",
        ),
    ],
)

print("\n   проверка:")
for relpath, markers in (
    ("valhalla/baldr/graphreader.h", ["WEDRIVE region scope", "WEDRIVE scope member"]),
    (
        "src/baldr/graphreader.cc",
        ["WEDRIVE detector respects scope", "WEDRIVE scope applies to tile choice"],
    ),
):
    s = io.open(os.path.join(SRC, relpath), encoding="utf-8").read()
    for m in markers:
        print("      %s %s" % ("ok     " if m in s else "MISSING", m))
