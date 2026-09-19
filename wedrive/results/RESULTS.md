# Measurements

Every run below came from one binary, `tools/compose_route.cc`, built once. Modes differ only in
which tile directories are loaded and whether the portal table is empty.

**The costing is distance, not time.** A crude auto-access filter, `edge->length()` as weight, a
straight-line heuristic. So absolute kilometres are *not* comparable to `valhalla_service route`.
Every comparison here is between two runs of this same search, which is what makes it mean
anything.

---

## 1. What the two extracts actually contain

Asked of the graphs, not of a map. Nearest **drivable** node to each place:

| place | Moldova graph | Romania graph |
|---|---|---|
| Chișinău | 19 m | **absent — no graph within 25 km** |
| Leușeni / Albița, on the E581 | 5 m | 5 m |
| Huși | 8811 m (a stub at the extract's edge) | 33 m |
| Iași | 13314 m | 23 m |

Two things follow, and the first killed the test that was planned.

**Geofabrik extracts overlap.** At the crossing both graphs hold the same junction at the identical
coordinate — region 1 node `70384118415618` and region 2 node `140758264856834`, both at
46.8233, 28.1407, both with 4 edges, for six consecutive nodes running in both directions from the
frontier. So **Leușeni → Albița cannot be a negative control**: Moldova's own graph contains Albița
and stock Valhalla would route it, proving nothing.

**What the overlap gives instead is the portal.** One physical junction, present twice, in two
namespaces. And the honest exclusive pair is Chișinău (Moldova-only) → Iași or Huși (Romania-only).

---

## 2. The proof: Chișinău → Huși

| mode | result |
|---|---|
| Moldova alone | NO ROUTE — destination never snaps, nearest node 8811 m |
| Romania alone | NO ROUTE — origin never snaps, nearest node 56853 m |
| **both graphs loaded, portal table empty** | **NO ROUTE — 512 815 nodes settled, search exhausted** |
| both graphs, one portal | **ROUTE, 102.844 km, 1 crossing at 46.8233, 28.1407 → 46.8233, 28.1407** |

Row three is the one that matters. Both graphs are in one reader, both endpoints snap, and the
search still cannot cross. **Identical coordinates are not a connection.** The namespaces are
genuinely disjoint and only the portal joins them.

---

## 3. Chișinău → Iași, and the search choosing a crossing

| portals | length | crossed at |
|---|---|---|
| none | NO ROUTE (512 815 settled) | — |
| 1, hand-picked (Leușeni) | 151.416 km | 46.8233, 28.1407 |
| 12508, derived from the graphs | **137.940 km** | **47.3103, 27.7098** — Sculeni |

Given the whole frontier the search picks a different and shorter crossing. It uses exactly **one**
portal, not a chain of them.

Chișinău → Bucharest, which Moldova's graph cannot answer at all:

| portals | result |
|---|---|
| none | **NO ROUTE** |
| 12508 derived | 424.922 km, 1 crossing at 46.7951, 28.1688 |

A third destination, a third crossing chosen.

### Portals found along the frontier (45.4–48.3 N, 26.6–28.3 E)

| level | drivable nodes, MD | drivable nodes, RO | coincident pairs |
|---|---|---|---|
| 0 | 4264 | 10763 | 506 |
| 1 | 15135 | 10331 | 482 |
| 2 | 54897 | 46486 | 5266 |
| | | **total** | **6254 pairs → 12508 directed entries** |

---

## 4. The controls that say the portal changes nothing else

Routes wholly inside one country, run with and without the portal table:

| route | without portals | with portals |
|---|---|---|
| Chișinău → Ungheni (Moldova only) | 100.507 km, 683 nodes, 120 330 settled | **identical in every figure**, 0 crossings |
| Iași → Huși (Romania only) | 74.303 km, 297 nodes, 24 251 settled | **identical in every figure**, 0 crossings |

The portal is inert where it should be.

> **Control A failed first, and it was the harness.** Chișinău → Ungheni reported NO ROUTE with
> *and* without portals — a journey wholly inside one country. The snap took the nearest node with
> any edge at all, and in Ungheni that was a footpath, unreachable by car. A harness failure wearing
> the exact costume of the defect the harness exists to detect. The snap now requires a node with at
> least one non-shortcut auto-accessible edge.

---

## 5. Point 7 — a cut we control

The Moldova/Romania work can always be answered with "the extracts overlapped anyway". So Moldova
was cut in half by us — A north of 46.90, B south of 47.10, an 11 km overlap band — and each half
built independently by stock `valhalla_build_tiles`. A = 77 tiles / 83 MB, B = 59 tiles / 58 MB.

Bălți (north of the cut, in A only) → Cahul (south of it, in B only):

| mode | route | nodes | portal crossings |
|---|---|---|---|
| **whole Moldova, one graph — the reference** | **236.864 km** | 1059 | — |
| A alone | NO ROUTE — destination 103 650 m off | | |
| B alone | NO ROUTE — origin 69 823 m off | | |
| A + B loaded, no portals | **NO ROUTE**, 375 948 settled | | |
| A + B with portals | **236.864 km** | 1064 | 5 |

**The composed route equals the monolithic route exactly**, and the 1064 − 1059 = 5 extra nodes are
precisely the 5 portal hops. Both sides ran the same search and the same costing, which is what
makes the equality meaningful rather than a coincidence of two different routers.

The five crossings are the churn noted in `MULTI-REGION.md`: inside the overlap band every drivable
node coincides (104 331 pairs at level 2, the entire band), and a zero-cost portal gives the search
no reason to prefer staying put. The road is the same road; the path just changes namespace five
times while driving down it.

---

## 6. The regression gate: does the patch disturb ordinary routing?

"It still routes" is not the same claim as "it routes the same". Answered by running our patched
build and **stock upstream `ghcr.io/valhalla/valhalla:3.6.3`** against the same Moldova tiles with
the same requests, through `valhalla_service route` — so this one goes through real Thor, real Sif
costing and real Odin narrative, unlike every measurement above.

| request | patched | stock 3.6.3 |
|---|---|---|
| Chișinău → Ungheni | 109.300 km, 5613.3 s, 26 maneuvers | 109.300 km, 5613.3 s, 26 maneuvers |
| a one-way pair, with the one-way | 3.684 km, 356.5 s, 9 maneuvers | 3.684 km, 356.5 s, 9 maneuvers |
| the same pair, reversed | 4.112 km, 381.7 s, 12 maneuvers | 4.112 km, 381.7 s, 12 maneuvers |

Identical to the decimal on every figure. The region tag is inert when only one region is loaded,
which is what makes the patch safe to carry.

The third row is also §7's one-way relationship surviving: 4.112 / 3.684 = 1.12 against the one-way,
and both builds agree on it.

---

## 7. Scoping what is left: Thor

Counted rather than guessed. Every `endnode()` read in Thor is a place the region tag must be
re-applied, because tiles are stock and hand back bare 46-bit ids:

| file | sites | file | sites |
|---|---|---|---|
| `bidirectional_astar.cc` | 21 | `route_matcher.cc` | 12 |
| `triplegbuilder.cc` | 11 | `unidirectional_astar.cc` | 11 |
| `costmatrix.cc` | 9 | `multimodal.cc` | 9 |
| `astar_bss.cc` | 7 | `dijkstras.cc` | 7 |
| the rest | 13 | | |
| | | **total** | **100** |

A first working cross-region route needs `bidirectional_astar.cc` (21) plus `triplegbuilder.cc`
(11) to build the response — about a third of the sites. The expansion has a single chokepoint,
`BidirectionalAStar::ExpandInner`, called from four places, which is where portal expansion belongs.

The risk is not the size, it is that a missed site fails **silently** by walking into the wrong
country's graph. That argues for re-tagging at a chokepoint rather than site by site, and for a
test that loads two regions and asserts every expanded id carries a non-zero region.

---

## What none of this shows

- Thor, Sif and Odin are untouched. This is a bespoke A*, not Valhalla's own search.
- No turn restrictions, no access modes beyond auto, no time costing, no narrative.
- A portal costs zero. A real border crossing does not.
- Nothing has been built or tested for Android.
