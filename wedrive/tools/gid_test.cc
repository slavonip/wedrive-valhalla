// WeDrive: GraphId обязан быть region-preserving value type.
//
// Инвариант, который должен держать САМ GraphId, а не каждый его пользователь:
//
//     любая операция, меняющая штатные поля, сохраняет region;
//     region == 0 ведёт себя ровно как stock Valhalla.
//
// Пока этого не было, Thor терял namespace на ровном месте: EdgeMetadata обходит рёбра узла
// через ++edge_id, GetOpposingEdgeId заканчивается set_id() — и региона не оставалось уже на
// втором ребре. Несколько патчей в Thor лечили симптомы этого.
#include <cstdint>
#include <cstdio>
#include <valhalla/baldr/graphid.h>
#include <valhalla/sif/edgelabel.h>

using namespace valhalla::baldr;

namespace {

int failures = 0;

void check(const char* what, bool ok) {
  std::printf("   %-58s %s\n", what, ok ? "ok" : "FAIL");
  if (!ok) {
    ++failures;
  }
}

} // namespace


// Поля EdgeLabel объявлены protected — наследник здесь даёт к ним доступ, не добавляя в боевой
// заголовок ни одного тестового метода. Регион хранится ТОЛЬКО в метке: edgeid_ и endnode_
// лежат по 46 бит, без namespace, и аксессоры возвращают его на место.
struct WeDriveTestLabel : public valhalla::sif::EdgeLabel {
  void put(const GraphId& e, const GraphId& n, const uint32_t r) {
    edgeid_ = e.without_region().value;
    endnode_ = n.without_region().value;
    region_ = r;
  }
  void put_pred(const uint32_t p) {
    predecessor_ = wedrive_pack_pred(p);
  }
};

int main() {
  constexpr uint32_t kRegion = 5;
  constexpr uint32_t kTile = 789955;
  constexpr uint32_t kLevel = 2;
  constexpr uint32_t kId = 10;

  std::printf("=== region = %u сохраняется всеми операциями\n", kRegion);
  const GraphId tagged = GraphId(kTile, kLevel, kId).with_region(kRegion);
  check("исходный с region", tagged.region() == kRegion && tagged.id() == kId &&
                                 tagged.tileid() == kTile && tagged.level() == kLevel);

  GraphId a = tagged;
  a.set_id(11);
  check("set_id(11) сохраняет region", a.region() == kRegion && a.id() == 11);
  check("set_id(11) не трогает tileid/level", a.tileid() == kTile && a.level() == kLevel);

  const GraphId b = tagged + uint64_t(1);
  check("operator+(1) сохраняет region", b.region() == kRegion && b.id() == kId + 1);

  GraphId c = tagged;
  ++c;
  check("operator++ (префикс) сохраняет region", c.region() == kRegion && c.id() == kId + 1);

  GraphId d = tagged;
  d++;
  check("operator++ (постфикс) сохраняет region", d.region() == kRegion && d.id() == kId + 1);

  GraphId e = tagged;
  e += 3;
  check("operator+=(3) сохраняет region", e.region() == kRegion && e.id() == kId + 3);

  check("tile_base() сохраняет region", tagged.tile_base().region() == kRegion);
  check("without_region() снимает region", tagged.without_region().region() == 0);
  check("with_region(0) снимает region", tagged.with_region(0).region() == 0);
  check("is_valid() не зависит от region", tagged.is_valid() && GraphId(kTile, kLevel, kId).is_valid());

  std::printf("\n=== region = 0 ведёт себя ровно как stock\n");
  const GraphId plain(kTile, kLevel, kId);
  check("region() == 0", plain.region() == 0);

  GraphId p1 = plain;
  p1.set_id(11);
  GraphId s1 = GraphId(kTile, kLevel, 11);
  check("set_id идентичен stock-конструкции", p1.value == s1.value);

  check("operator+ идентичен stock-конструкции",
        (plain + uint64_t(1)).value == GraphId(kTile, kLevel, kId + 1).value);

  GraphId p2 = plain;
  ++p2;
  check("operator++ идентичен stock-конструкции", p2.value == GraphId(kTile, kLevel, kId + 1).value);

  check("tile_base() идентичен stock", plain.tile_base().value == GraphId(kTile, kLevel, 0).value);

  std::printf("\n=== два региона не путаются\n");
  const GraphId md = GraphId(kTile, kLevel, kId).with_region(1);
  const GraphId ro = GraphId(kTile, kLevel, kId).with_region(2);
  check("одинаковые 46 бит, разные значения", md.value != ro.value);
  check("без региона совпадают", md.without_region().value == ro.without_region().value);
  check("после set_id всё ещё различимы",
        [&] {
          GraphId x = md, y = ro;
          x.set_id(77);
          y.set_id(77);
          return x.value != y.value && x.region() == 1 && y.region() == 2;
        }());

  std::printf("\n=== регион шире прежних трёх бит\n");
  // Прежний предел — 7. Восьмёрка доказывает, что мы за него вышли, 255 — что дошли до нового.
  for (const uint32_t r : {8u, 63u, 200u, 255u}) {
    const GraphId g = GraphId(kTile, kLevel, kId).with_region(r);
    char msg[96];
    std::snprintf(msg, sizeof(msg), "GraphId хранит регион %u", r);
    check(msg, g.region() == r && g.without_region().value == plain.value);
  }

  std::printf("\n=== регион проезжает через метку поиска\n");
  for (const uint32_t r : {1u, 7u, 8u, 128u, 255u}) {
    const GraphId e = GraphId(kTile, kLevel, kId).with_region(r);
    const GraphId n = GraphId(kTile, kLevel, kId + 5).with_region(r);
    WeDriveTestLabel lbl;
    lbl.put(e, n, r);
    char msg[96];
    std::snprintf(msg, sizeof(msg), "EdgeLabel отдаёт регион %u на обоих id", r);
    check(msg, lbl.region() == r && lbl.edgeid().region() == r && lbl.endnode().region() == r &&
                   lbl.edgeid().without_region().value == e.without_region().value &&
                   lbl.endnode().without_region().value == n.without_region().value);
  }

  std::printf("\n=== недействительный предшественник пережил сужение до 28 бит\n");
  {
    WeDriveTestLabel lbl;
    lbl.put_pred(valhalla::baldr::kInvalidLabel);
    check("kInvalidLabel возвращается как kInvalidLabel",
          lbl.predecessor() == valhalla::baldr::kInvalidLabel);
    lbl.put_pred(0);
    check("ноль остаётся нулём", lbl.predecessor() == 0);
    lbl.put_pred(268435454u);
    check("предельный индекс 2^28-2 хранится точно", lbl.predecessor() == 268435454u);
  }

  std::printf("\n=== размеры меток не изменились\n");
  check("EdgeLabel 40 байт", sizeof(valhalla::sif::EdgeLabel) == 40);
  check("BDEdgeLabel ровно кэш-линия, 64 байта", sizeof(valhalla::sif::BDEdgeLabel) == 64);

  std::printf("\n%s  (%d провалов)\n", failures == 0 ? "ВСЁ ЗЕЛЁНОЕ" : "ЕСТЬ ПРОВАЛЫ", failures);
  return failures == 0 ? 0 : 1;
}
