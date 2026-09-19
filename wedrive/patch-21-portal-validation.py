"""WeDrive patch 21: портал проверяется при добавлении, а не роняет процесс на маршруте.

Таблица, собранная для ДРУГОЙ пары графов, кладёт рантайм:

    GraphTile NodeInfo index out of bounds: 49527,1,7042 nodecount= 146

потому что id из чужой сборки попадает в тайл, где столько узлов просто нет. Это не гипотеза —
воспроизведено подстановкой таблицы MD/RO графам A/B.

Инвариант: каждый портал, попадающий в таблицу, обязан быть отдельно валиден, и проверяться это
должно ОДИН РАЗ при загрузке, а не на каждом маршруте:

  * оба тайла существуют в своих регионах;
  * оба индекса узлов лежат в пределах nodecount своего тайла;
  * оба узла проходимы для автомобиля — иначе переход бесполезен;
  * концы в РАЗНЫХ регионах — портал внутри одного namespace бессмысленен;
  * при distance == 0 концы обязаны быть одной физической точкой (допуск 2 м), потому что
    нулевая стоимость заявляет именно это.

Отвергнутые считаются, и вызывающий код может об этом сказать. Молча пропускать нельзя: таблица
на 235 022 записи, из которой половина отброшена, — это сломанный генератор, а не мелочь.
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
            "WEDRIVE portal validation",
            "  void AddPortal(const GraphId& from, const GraphId& to, const float distance) {\n"
            "    wedrive_portals_[from.value].push_back({to, distance});\n"
            "  }",
            "  /**\n"
            "   * WEDRIVE portal validation: добавляет переход, ЕСЛИ он валиден.\n"
            "   *\n"
            "   * Возвращает false и ничего не добавляет, когда портал непригоден. Проверка здесь,\n"
            "   * а не на маршруте, потому что таблица загружается один раз, а маршрутов много — и\n"
            "   * потому что невалидный портал иначе роняет процесс индексом за пределами чужого\n"
            "   * тайла, что и наблюдалось на таблице, собранной для другой пары графов.\n"
            "   */\n"
            "  bool AddPortal(const GraphId& from, const GraphId& to, const float distance) {\n"
            "    // Переход внутри одного namespace ничего не соединяет.\n"
            "    if (from.region() == to.region()) {\n"
            "      ++wedrive_portals_rejected_;\n"
            "      return false;\n"
            "    }\n"
            "    const auto* a = WeDrivePortalNode(from);\n"
            "    const auto* b = WeDrivePortalNode(to);\n"
            "    if (a == nullptr || b == nullptr) {\n"
            "      ++wedrive_portals_rejected_;\n"
            "      return false;\n"
            "    }\n"
            "    // Нулевая стоимость заявляет, что это ОДНА точка. Если концы разъехались —\n"
            "    // либо таблица не от этих графов, либо генератор не проставил расстояние.\n"
            "    if (distance == 0.0f) {\n"
            "      auto ta = GetGraphTile(from);\n"
            "      auto tb = GetGraphTile(to);\n"
            "      const auto pa = a->latlng(ta->header()->base_ll());\n"
            "      const auto pb = b->latlng(tb->header()->base_ll());\n"
            "      if (pa.Distance(pb) > 2.0) {\n"
            "        ++wedrive_portals_rejected_;\n"
            "        return false;\n"
            "      }\n"
            "    }\n"
            "    wedrive_portals_[from.value].push_back({to, distance});\n"
            "    return true;\n"
            "  }\n"
            "\n"
            "  /** WEDRIVE: сколько порталов отвергнуто как невалидные. */\n"
            "  size_t PortalsRejected() const {\n"
            "    return wedrive_portals_rejected_;\n"
            "  }",
        ),
        (
            "WEDRIVE portal node lookup",
            "  /** WEDRIVE: порталы, выходящие из этого узла, или nullptr. Горячий путь в Thor,",
            "  /**\n"
            "   * WEDRIVE portal node lookup: узел конца портала, или nullptr если его нет.\n"
            "   *\n"
            "   * Проверяет индекс ДО обращения: GraphTile::node() на индексе за пределами\n"
            "   * nodecount бросает, а нам нужен ответ «такого узла нет», а не исключение.\n"
            "   * Требует и проходимости для автомобиля — переход в узел, из которого нельзя\n"
            "   * выехать, не добавляет связности.\n"
            "   */\n"
            "  const NodeInfo* WeDrivePortalNode(const GraphId& id) {\n"
            "    auto tile = GetGraphTile(id);\n"
            "    if (!tile || id.id() >= tile->header()->nodecount()) {\n"
            "      return nullptr;\n"
            "    }\n"
            "    const auto* n = tile->node(id.id());\n"
            "    for (uint32_t e = 0; e < n->edge_count(); ++e) {\n"
            "      const auto* de = tile->directededge(n->edge_index() + e);\n"
            "      if (!de->is_shortcut() && (de->forwardaccess() & kAutoAccess)) {\n"
            "        return n;\n"
            "      }\n"
            "    }\n"
            "    return nullptr;\n"
            "  }\n"
            "\n"
            "  /** WEDRIVE: порталы, выходящие из этого узла, или nullptr. Горячий путь в Thor,",
        ),
        (
            "WEDRIVE rejected counter",
            "  std::unordered_map<uint64_t, std::vector<WeDrivePortal>> wedrive_portals_;",
            "  std::unordered_map<uint64_t, std::vector<WeDrivePortal>> wedrive_portals_;\n"
            "  size_t wedrive_portals_rejected_{0}; // WEDRIVE rejected counter",
        ),
    ],
)

print("\n   проверка:")
s = io.open(os.path.join(SRC, "valhalla/baldr/graphreader.h"), encoding="utf-8").read()
for m in ("WEDRIVE portal validation", "WEDRIVE portal node lookup", "WEDRIVE rejected counter",
          "bool AddPortal", "PortalsRejected"):
    print("      %s %s" % ("ok     " if m in s else "MISSING", m))
