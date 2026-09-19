"""WeDrive patch 64: остальные места, где Loki искал кандидатов в одном регионе.

Изолиния всё ещё обрезалась по Пруту, и детектор снова назвал место сам — loki_worker_t::isochrones
с собственным search_.search. Это был четвёртый такой вызов после route, trace и matrix, и стало
ясно, что искать их по одному бессмысленно: у каждого действия loki_worker_t свой.

Перечислены все шесть разом:

    route_action.cc          переведён (патч 23 -> 60)
    trace_route_action.cc    переведён (патч 55 -> 60)
    matrix_action.cc         переведён (патч 60)
    isochrone_action.cc      здесь
    locate_action.cc         здесь
    worker.cc                здесь — exclude_locations, точки объезда

locate по правилу проекта остаётся диагностикой и в guidance не участвует, но отвечать он обязан
про тот же граф, что и всё остальное. exclude_locations — это точки, которые пользователь просит
объехать: найденные в одном регионе, они молча не сработают в другом.

После этого патча в loki не остаётся ни одного одно-регионального поиска кандидатов.
"""
import io
import os

SRC = "/src/valhalla"
NAME = "WEDRIVE loki correlate"

SITES = (
    ("src/loki/isochrone_action.cc",
     "    const auto projections = search_.search(locations, costing);\n",
     "    // WEDRIVE loki correlate: изолиния от точки у границы обязана видеть оба графа.\n"
     "    const auto projections = loki::WeDriveCorrelate(*reader, search_, locations, costing);\n"),
    ("src/loki/locate_action.cc",
     "  auto projections = search_.search(locations, costing);\n",
     "  // WEDRIVE loki correlate: locate остаётся диагностикой, но отвечать должен про тот же\n"
     "  // граф, что и остальные действия.\n"
     "  auto projections = loki::WeDriveCorrelate(*reader, search_, locations, costing);\n"),
    ("src/loki/worker.cc",
     "      auto results = search_.search(exclude_locations, costing);\n",
     "      // WEDRIVE loki correlate: точки объезда, найденные в одном регионе, молча не\n"
     "      // сработали бы в другом.\n"
     "      auto results = loki::WeDriveCorrelate(*reader, search_, exclude_locations, costing);\n"),
)

for rel, old, new in SITES:
    P = os.path.join(SRC, rel)
    s = io.open(P, encoding="utf-8").read()
    if "WeDriveCorrelate" in s:
        print("      ok   уже применено: %s" % rel)
        continue
    assert s.count(old) == 1, "не нашёл вызов в %s" % rel
    io.open(P, "w", encoding="utf-8").write(s.replace(old, new))
    print("      +    %s" % rel)

print("\n   проверка:")
LOKI = os.path.join(SRC, "src/loki")
left = []
for fn in sorted(os.listdir(LOKI)):
    if not fn.endswith(".cc") or fn == "search.cc":
        continue
    txt = io.open(os.path.join(LOKI, fn), encoding="utf-8").read()
    if "search_.search(" in txt:
        left.append(fn)
print("      %s одно-региональных поисков не осталось%s"
      % ("ok     " if not left else "MISSING", ("" if not left else ": " + ", ".join(left))))
converted = 0
for fn in sorted(os.listdir(LOKI)):
    if fn.endswith(".cc") and "WeDriveCorrelate" in io.open(os.path.join(LOKI, fn), encoding="utf-8").read():
        converted += 1
print("      %s мест вызова через общий helper: %d (ожидается 6)"
      % ("ok     " if converted == 6 else "MISSING", converted))
