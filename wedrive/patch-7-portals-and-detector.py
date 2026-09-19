"""WeDrive patch 7: porталы в GraphReader + fail-fast детектор потери региона.

Главная идея патча — НЕ угадывать, какие call sites теряют регион, а поставить один детектор в
GetGraphTile: если зарегистрировано больше одного региона, а пришёл id с region == 0, значит
где-то регион потерян. Счётчик и однократный лог превращают тихую ошибку («уехали в чужую
страну») в громкую и, главное, САМИ показывают список пропущенных мест.

Это ровно то, о чём просил владелец: assertion на потерю региона, а не 100 ручных правок.
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
        # 1. Тип портала, объявленный до класса.
        (
            "WEDRIVE portal type",
            "class GraphReader {\npublic:",
            "/**\n"
            " * WEDRIVE portal type: внешний переход между двумя независимо собранными графами.\n"
            " *\n"
            " * Это НЕ синтетическое ребро внутри .gph — формат тайлов не меняется. Портал живёт\n"
            " * только в рантайме и является единственным механизмом, которому разрешено менять\n"
            " * namespace: обычное ребро всегда наследует регион от текущего тайла.\n"
            " */\n"
            "struct WeDrivePortal {\n"
            "  GraphId to;\n"
            "  float distance; // метры реальной дороги между концами; 0 — если это один узел\n"
            "};\n\n"
            "class GraphReader {\npublic:",
        ),
        # 2. AddRegion теперь отказывается принимать регион, который не влезет в 3 бита EdgeLabel.
        (
            "WEDRIVE region cap",
            "  void AddRegion(const uint32_t region, const std::string& tile_dir) {\n"
            "    wedrive_region_dirs_[region] = tile_dir;\n"
            "  }",
            "  void AddRegion(const uint32_t region, const std::string& tile_dir) {\n"
            "    // WEDRIVE region cap: EdgeLabel хранит регион в 3 битах, отнятых у `spare`.\n"
            "    // Регион 8 там молча превратится в 0 и машина уедет в чужую страну, поэтому\n"
            "    // здесь громкий отказ, а не обрезание. Это ограничение ПРОТОТИПА: расширение\n"
            "    // namespace до сотен регионов — отдельная задача, см. MULTI-REGION.md.\n"
            "    if (region >= kWeDriveMaxRegions) {\n"
            "      throw std::runtime_error(\"WEDRIVE: region id \" + std::to_string(region) +\n"
            "                               \" exceeds the \" + std::to_string(kWeDriveMaxRegions) +\n"
            "                               \" that EdgeLabel's 3 spare bits can carry\");\n"
            "    }\n"
            "    wedrive_region_dirs_[region] = tile_dir;\n"
            "  }\n\n"
            "  /** WEDRIVE: сколько регионов помещается в 3 бита EdgeLabel::region_. */\n"
            "  static constexpr uint32_t kWeDriveMaxRegions = 8;",
        ),
        # 3. Портальная таблица и детектор.
        (
            "WEDRIVE portal table",
            "  /** WEDRIVE: how many independently built regions are registered. */\n"
            "  size_t RegionCount() const {\n"
            "    return wedrive_region_dirs_.size();\n"
            "  }",
            "  /** WEDRIVE: how many independently built regions are registered. */\n"
            "  size_t RegionCount() const {\n"
            "    return wedrive_region_dirs_.size();\n"
            "  }\n\n"
            "  /** WEDRIVE portal table: одна запись на направление; две записи делают переход\n"
            "   *  двусторонним. Обе стороны — настоящие узлы своих графов. */\n"
            "  void AddPortal(const GraphId& from, const GraphId& to, const float distance) {\n"
            "    wedrive_portals_[from.value].push_back({to, distance});\n"
            "  }\n\n"
            "  /** WEDRIVE: порталы, выходящие из этого узла, или nullptr. Горячий путь в Thor,\n"
            "   *  поэтому сначала дешёвая проверка на пустую таблицу. */\n"
            "  const std::vector<WeDrivePortal>* PortalsAt(const GraphId& node) const {\n"
            "    if (wedrive_portals_.empty()) {\n"
            "      return nullptr;\n"
            "    }\n"
            "    auto found = wedrive_portals_.find(node.value);\n"
            "    return found == wedrive_portals_.end() ? nullptr : &found->second;\n"
            "  }\n\n"
            "  size_t PortalCount() const {\n"
            "    size_t n = 0;\n"
            "    for (const auto& e : wedrive_portals_) {\n"
            "      n += e.second.size();\n"
            "    }\n"
            "    return n;\n"
            "  }\n\n"
            "  /** WEDRIVE: сколько раз GetGraphTile получил id без региона при нескольких\n"
            "   *  зарегистрированных регионах. Ноль — обязательное условие зелёного теста. */\n"
            "  static uint64_t WeDriveRegionLost() {\n"
            "    return wedrive_region_lost_.load(std::memory_order_relaxed);\n"
            "  }\n"
            "  static void WeDriveResetRegionLost() {\n"
            "    wedrive_region_lost_.store(0, std::memory_order_relaxed);\n"
            "  }",
        ),
        # 4. Члены.
        (
            "WEDRIVE portal members",
            "  // WEDRIVE: one tile directory per independently built region.",
            "  // WEDRIVE portal members: внешняя таблица переходов, ключ — полный tagged GraphId\n"
            "  // узла-источника. Пустая в stock-сценарии, и тогда PortalsAt выходит сразу.\n"
            "  std::unordered_map<uint64_t, std::vector<WeDrivePortal>> wedrive_portals_;\n"
            "  static inline std::atomic<uint64_t> wedrive_region_lost_{0};\n\n"
            "  // WEDRIVE: one tile directory per independently built region.",
        ),
    ],
)

print("   src/baldr/graphreader.cc")
patch(
    "src/baldr/graphreader.cc",
    [
        # 5. Тегируем endnode в GetOpposingEdgeId — им Thor пользуется постоянно.
        (
            "WEDRIVE opposing keeps region",
            "  // If edge leaves the tile get the end node's tile\n"
            "  GraphId id = directededge->endnode();",
            "  // WEDRIVE opposing keeps region: endnode прочитан из байтов тайла и региона не\n"
            "  // содержит — его надо восстановить из id ребра, иначе уедем в чужой регион.\n"
            "  GraphId id = directededge->endnode().with_region(edgeid.region());",
        ),
    ],
)

print("\n   проверка каждого куска по собственному маркеру:")
for relpath, markers in (
    (
        "valhalla/baldr/graphreader.h",
        [
            "WEDRIVE portal type",
            "WEDRIVE region cap",
            "WEDRIVE portal table",
            "WEDRIVE portal members",
        ],
    ),
    ("src/baldr/graphreader.cc", ["WEDRIVE opposing keeps region"]),
):
    s = io.open(os.path.join(SRC, relpath), encoding="utf-8").read()
    for m in markers:
        print("      %s %s" % ("ok     " if m in s else "MISSING", m))
