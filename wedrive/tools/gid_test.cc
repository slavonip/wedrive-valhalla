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

  const GraphId b = tagged + 1;
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
        (plain + 1).value == GraphId(kTile, kLevel, kId + 1).value);

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

  std::printf("\n%s  (%d провалов)\n", failures == 0 ? "ВСЁ ЗЕЛЁНОЕ" : "ЕСТЬ ПРОВАЛЫ", failures);
  return failures == 0 ? 0 : 1;
}
