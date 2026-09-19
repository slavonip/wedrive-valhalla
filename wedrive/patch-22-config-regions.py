"""WeDrive patch 22: регионы и таблица порталов задаются в КОНФИГЕ.

До сих пор регионы регистрировались из кода тестовых стендов. Чтобы запустить настоящий
valhalla_service, они должны приходить из того же json, что и всё остальное:

    "mjolnir": {
      "tile_dir": "/regions/moldova/tiles",
      "wedrive_regions": [ {"id": 1, "dir": "/regions/moldova/tiles"},
                           {"id": 2, "dir": "/regions/romania/tiles"} ],
      "wedrive_portals": "/regions/portals_border.txt"
    }

Ничего не задано — поведение ровно стоковое: регионов ноль, таблица пуста, и ни одна проверка
в GetGraphTile не включается.
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
            "WEDRIVE config includes",
            "#include <atomic> // WEDRIVE atomic include: счётчик потерь региона",
            "#include <atomic> // WEDRIVE atomic include: счётчик потерь региона\n"
            "#include <fstream>  // WEDRIVE config includes\n"
            "#include <sstream>",
        ),
        (
            "WEDRIVE region ids",
            "  /** WEDRIVE: how many independently built regions are registered. */\n"
            "  size_t RegionCount() const {\n"
            "    return wedrive_region_dirs_.size();\n"
            "  }",
            "  /** WEDRIVE: how many independently built regions are registered. */\n"
            "  size_t RegionCount() const {\n"
            "    return wedrive_region_dirs_.size();\n"
            "  }\n\n"
            "  /** WEDRIVE region ids: зарегистрированные регионы, по возрастанию. Нужны тем, кто\n"
            "   *  обходит регионы по очереди — например multiplexing поиска кандидатов. */\n"
            "  std::vector<uint32_t> RegionIds() const {\n"
            "    std::vector<uint32_t> ids;\n"
            "    ids.reserve(wedrive_region_dirs_.size());\n"
            "    for (const auto& kv : wedrive_region_dirs_) {\n"
            "      ids.push_back(kv.first);\n"
            "    }\n"
            "    std::sort(ids.begin(), ids.end());\n"
            "    return ids;\n"
            "  }\n\n"
            "  /**\n"
            "   * WEDRIVE: прочитать таблицу порталов из файла.\n"
            "   *\n"
            "   * Формат — строка на направление: <from> <to> <метры>, всё после # игнорируется.\n"
            "   * Невалидные записи отвергаются AddPortal и попадают в PortalsRejected().\n"
            "   */\n"
            "  size_t LoadPortalTable(const std::string& path) {\n"
            "    std::ifstream in(path);\n"
            "    if (!in) {\n"
            "      return 0;\n"
            "    }\n"
            "    std::string line;\n"
            "    size_t added = 0;\n"
            "    while (std::getline(in, line)) {\n"
            "      const auto hash = line.find('#');\n"
            "      if (hash != std::string::npos) {\n"
            "        line.erase(hash);\n"
            "      }\n"
            "      std::istringstream ls(line);\n"
            "      uint64_t from = 0, to = 0;\n"
            "      double d = 0.0;\n"
            "      if (ls >> from >> to >> d) {\n"
            "        added += AddPortal(GraphId(from), GraphId(to), static_cast<float>(d)) ? 1 : 0;\n"
            "      }\n"
            "    }\n"
            "    return added;\n"
            "  }",
        ),
    ],
)

print("   src/baldr/graphreader.cc")
patch(
    "src/baldr/graphreader.cc",
    [
        (
            "WEDRIVE config regions",
            "  if (!tile_url_.empty()) {\n"
            "    // Make a tile fetcher if we havent passed one in from somewhere else\n"
            "    if (!tile_getter_) {",
            "  // WEDRIVE config regions: независимо собранные регионы и внешняя таблица порталов\n"
            "  // приходят из того же конфига, что и всё остальное. Не заданы — поведение стоковое.\n"
            "  if (auto regions = pt.get_child_optional(\"wedrive_regions\")) {\n"
            "    for (const auto& kv : *regions) {\n"
            "      const auto id = kv.second.get_optional<uint32_t>(\"id\");\n"
            "      const auto dir = kv.second.get_optional<std::string>(\"dir\");\n"
            "      if (id && dir) {\n"
            "        AddRegion(*id, *dir);\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "  if (auto portals = pt.get_optional<std::string>(\"wedrive_portals\")) {\n"
            "    if (!portals->empty()) {\n"
            "      const size_t added = LoadPortalTable(*portals);\n"
            "      LOG_INFO(\"WEDRIVE: регионов \" + std::to_string(RegionCount()) + \", порталов \" +\n"
            "               std::to_string(added) + \", отвергнуто \" +\n"
            "               std::to_string(PortalsRejected()));\n"
            "    }\n"
            "  }\n\n"
            "  if (!tile_url_.empty()) {\n"
            "    // Make a tile fetcher if we havent passed one in from somewhere else\n"
            "    if (!tile_getter_) {",
        ),
    ],
)

print("\n   проверка:")
for relpath, markers in (
    ("valhalla/baldr/graphreader.h",
     ["WEDRIVE config includes", "WEDRIVE region ids", "LoadPortalTable"]),
    ("src/baldr/graphreader.cc", ["WEDRIVE config regions"]),
):
    s = io.open(os.path.join(SRC, relpath), encoding="utf-8").read()
    for m in markers:
        print("      %s %s" % ("ok     " if m in s else "MISSING", m))
