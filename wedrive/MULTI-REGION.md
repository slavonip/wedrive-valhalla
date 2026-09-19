# The multi-region runtime

## The idea in one line

A `GraphId` is a plain `uint64_t` using 46 of its 64 bits. The top 18 are free. Put a region number
there **in memory only**, and one `GraphReader` can hold several tile directories whose ids would
otherwise collide.

```
 63            46 45   43 42                    21 20                   0
+----------------+-------+------------------------+---------------------+
|  region (ours) | level |         tileid         |         id          |
+----------------+-------+------------------------+---------------------+
 \_ never written to disk _/ \______ stock Valhalla, untouched ________/
```

`kGraphIdBits = 0x3fffffffffff` is the stock 46-bit mask; everything above it is ours. A tagged id
written to a tile would be a format change, so it never is: the tag is applied when a tile is
loaded and stripped by `without_region()` wherever stock code needs a plain id.

## The five files that change

| file | change |
|---|---|
| `valhalla/baldr/graphid.h` | `region()`, `with_region()`, `without_region()`; `is_valid()` and `tile_base()` mask the region out so stock logic is unaffected |
| `valhalla/baldr/graphtile.h` | `GraphTile` remembers which region it was loaded as; `id()` returns its id **re-tagged** |
| `src/baldr/graphtile.cc` | the constructor records it |
| `valhalla/baldr/graphreader.h` | `AddRegion(id, dir)`, `TileDirForRegion()`, `RegionCount()`; the flat cache gains an overflow map |
| `src/baldr/graphreader.cc` | `GetGraphTile` picks the directory from the id's region; the flat cache consults the overflow map in `Get`/`Put`/`Contains`/`Clear` |

## The rule that makes it work, and the one that nearly broke it

**A GraphId read out of tile bytes carries no region.** Tiles are stock, so an `endnode` on a
`DirectedEdge` or a `NodeTransition` is a bare 46-bit id. Every one of them must be re-tagged with
the region of the node it was reached from — a tile cannot know which namespace it was loaded into.
Miss this in one place and the search silently walks into the wrong country's graph.

**`FlatTileCache` is the default and it drops the region.** Its slot is
`index_offsets_[level] + tileid`, which is computed from the stock bits alone, so two regions'
copies of the same cell share one slot and the second evicts the first. Romania's tile came back
claiming to be Moldova's. Fixed with an overflow `unordered_map` keyed on the full tagged value,
consulted by all four cache methods.

> **`Contains` was patched last and nearly was not patched at all.** The idempotency check compared
> the first 40 characters after the marker, and for `Put` and `Contains` those characters are
> identical — so once `Put` was in, `Contains` reported "already applied". The test passed anyway,
> because it never calls `Contains`: a green result standing over an unpatched function. Markers are
> method names now. This is the same failure this project keeps meeting from the other side, and it
> is why every patch script verifies each hunk by a marker that cannot collide.

## Portals

A portal is **not** a synthetic `DirectedEdge` inside a `.gph`. It is an external row:

```cpp
struct Portal { GraphId from; GraphId to; float distance; };
```

Two rows per crossing, one each way. The search expands them at a node exactly as it expands that
node's edges, so a single search with a single costing crosses namespaces without knowing it did.

**Portals are abundant, not scarce.** Geofabrik extracts overlap at the frontier, so the same
physical junction exists in both graphs at the same coordinate with different ids. Scanning the
Moldova–Romania frontier found **6254 coincident drivable junctions** across the three hierarchy
levels — every one a candidate portal, found by asking the graphs rather than by anyone typing a
border crossing from memory.

That abundance has a consequence worth designing for: with zero-cost portals everywhere in an
overlap band, the search hops between namespaces freely. The Moldova-split route crossed **five
times** for what is one continuous road. It costs nothing and the route is identical, but a
production table should either keep only the junctions on the true boundary or give a portal a
small penalty, so the path does not churn between two copies of the same tarmac.

## What is deliberately still stock

- Mjolnir, **with one exception**: `NodeInfo::can_contract()` also refuses `kBorderControl`.
  Everything else in the builder is stock, and the `.gph` format is untouched — the flag
  changes only which shortcuts get built. See *The border post* below for why.
- The `.gph` format, including `GraphTileHeader` (272 B, `static_assert`-ed), `NodeInfo` (32 B),
  `NodeTransition` (8 B) and `DirectedEdge` (48 B).
- Thor, Sif and Odin. The proof harness is separate, on purpose: changing the runtime's *reader*
  and changing its *search* are two risks and were taken one at a time.

## The border post — where +2.8 % on Chișinău → Bucharest came from

Bidirectional A* on the composite returned **469.423 km** where the monolith returned **456.458**,
and the search's own estimate of the winning connection was **1234.44** below what `recost` charged
for the very same edges. The hunt narrowed to a single pair of `GraphId`s and then, being measured
rather than reasoned about, went somewhere else entirely.

**The multi-region runtime was not at fault, and the control says so plainly.** Forced onto one and
the same corridor, the two graphs agree:

| forced route | monolith | composite |
|---|---|---|
| Chișinău → Bârlad | 166.560 km, estimate == recost | 166.560 km, estimate == recost |
| Leușeni → Bucharest | 378.947 km | 378.947 km |
| Chișinău → *(past Albița)* → Bucharest | 469.419 km | 469.417 km |

Two metres over 469 km. The composite does not compute the corridor differently — it *prefers* it,
because free-search its estimate for that corridor is 1234 too cheap.

**The 1234 is two border posts, and the cost of a post hangs on the NODE:**

```cpp
c += country_crossing_cost_ * (node->type() == baldr::NodeType::kBorderControl);  // 600 s
```

A shortcut's cost is the cost of its edges. Transitions at its *interior* nodes are not in it and
never were. So a shortcut laid through a border post hides 600 seconds from the search, and `recost`
presents the bill only after the path has been chosen. Albița–Leușeni has a post on each side:
600 + 600.

**Why the coherent build escapes it, measured on the posts themselves:**

| node | monolith | Moldova alone | Romania alone |
|---|---|---|---|
| 46.48059, 28.23211 | 4 edges, not covered | 2 edges, covered by shortcut `7257` (2297 m) | 2 edges, covered by `828` |
| 46.48380, 28.22821 | 4 edges, not covered | 2 edges, covered | 2 edges, covered |

`CanContract` demands exactly two edges at the node. In a coherent graph the post carries both
countries' carriageways and has four, so contraction is refused. A Geofabrik extract is clipped at
the border, the far side is gone, the degree falls to two — and the guard stops guarding. Shortcut
`7257` is precisely the one on the failing path.

**The guard that should have caught it regardless is an upstream omission:**

```cpp
// baldr/nodeinfo.h — every other cost-bearing node type is listed
return edge_count() >= 2 && intersection() != IntersectionType::kFork &&
       type() != NodeType::kGate && type() != NodeType::kTollBooth &&
       type() != NodeType::kTollGantry && type() != NodeType::kSumpBuster;
```

Gate 300 s, toll booth 15 s, toll gantry, sump buster — all excluded. `kBorderControl`, at 600 s the
dearest of them, is not. The stock monolith carries 168 such shortcuts at level 0 and under-charges
its own chosen path by 150; it simply never puts one where it matters. Adding the missing term is
patch 46, and it is the whole fix.

**Result, shortcuts enabled throughout — their count went *up*, 2190 → 2232 in Moldova, because a
shortcut now ends at a post instead of running through it:**

| | stock | with patch 46 |
|---|---|---|
| composite, bidirectional | 469.423 km | **456.448 km** |
| monolith, bidirectional | 456.458 km | 456.431 km |
| composite, time-dependent | 456.458 km | 456.458 km |
| estimate vs recost, composite | 1234.44 | **33.43** |
| posts covered by a shortcut (MD / RO) | 132 / 116 | **0 / 0** |
| region lost | 0 | 0 |

Every other route in the regression table is unchanged to within its previous divergence; the two
that moved are Chișinău → Bucharest and its reverse, both by ~13 km, both onto the monolith's answer.

> **The measurement that mattered most was the one that disproved the tidy theory.** The first
> account of this — two border charges where the monolith pays one, an artifact of each half seeing
> its own frontier — was wrong. Forcing both graphs onto the same crossing showed both paying both
> posts and agreeing to two metres. The posts are real and the double charge is correct; what is
> wrong is only that the search cannot see them. Three earlier suspects died the same way, by being
> measured: `shortcut_recovery_t` (12 shortcuts, zero foreign-region components, total delta 1.34),
> the forward label chain (592 labels, self-consistent to a constant −15.69 that is the origin's
> partial edge), and the meeting edge itself (`pred.opp_edgeid() == opp_pred.edgeid()`, equal with
> the region tag and without it).

## Map matching — Meili has its own everything

`map_matcher` was taken next because a car crossing a border needs its GPS snapped there, and it
was the riskiest of the three: Meili does not use Thor. It has its own candidate search
(`candidate_search.cc`), its own expansion (`routing.cc`) and its own cost model, and not one of
the Thor patches touched any of it.

Measured first, on a 770-point trace sampled at 150 m from the monolith's own Chisinau -> Iasi
shape:

| | monolith | composite, before |
|---|---|---|
| points matched | 770 / 770 | **638 / 770** |
| first failure | none | **#633 at 47.31478, 27.60826** — the Prut crossing itself |

Loki found Romanian candidates, so the last point matched; what failed was routing *between* an
MD candidate and an RO one. Seven defects were behind it, and only the first was the expected one:

1. **No portal expansion in Meili's `expand`** — the same block as Thor's, next to `NodeTransition`.
2. **Region dropped when an id is assembled from parts**: `GraphId{node.tileid(), node.level(),
   nodeinfo->edge_index()}`, and `directededge->endnode()` where it selects a tile.
3. **A fourth namespace-unaware container**, after `FlatTileCache`, `EdgeStatus` and
   `shortcut_recovery_t`: `CandidateGridQuery::grid_cache_` is keyed by `int32_t bin_id` — pure
   geography, the same square numbered identically in every region.
4. **Candidate search ran in one region only**; multiplexed per region like `loki::Search`.
5. **`expand(trans->endnode(), ...)`** dropped the region on every hierarchy change.
6. **Portals were gated on `!from_transition`.** Portals exist at level 0 (14 pairs) and level 2
   (2 pairs); Meili reaches level 0 *only* through a transition, so that one flag hid every
   level-0 crossing. Two independent prohibitions need two flags.
7. **`loki_worker_t::locations_from_shape`** — a second, separate `search_.search` that patch 23
   never touched, so the trace's own endpoints were correlated in one region.
8. **The origin was seeded untagged.** `directed_edge->endnode()` in the origin-edge branch, where
   the search is *born*. Everything downstream then propagated region 0 faithfully.

> **Two of those were found by the region-lost detector naming its own call site, not by reading
> code.** It prints a backtrace for the first six losses, and it pointed straight at
> `locations_from_shape` and then at `find_shortest_path` — both places I was not looking. The
> detector has now paid for itself twice over.

### The one that took longest was a comparison, not a lookup

With every id tagged, matching still lost 76 points *inside Moldova*, nowhere near a border. The
controls were config-only and they were decisive:

| | edges | unmatched |
|---|---|---|
| stock, no regions | 702 | 0 |
| one region registered | 702 | 0 |
| two regions, second an **empty directory** | 479 | **76** |
| two regions, tag stripped from candidates | 702 | 0 |

An empty second region contributes nothing, so the damage was the tag itself. And a stage probe
showed routing was innocent: **653 searches between states, zero empty, identical in all three
runs**. The loss was downstream, in `FindMatchResult`:

```cpp
auto candidate_nodes = graph_reader.GetDirectedEdgeNodes(edge.id, tile);  // TAGGED
...
if (prev_de && prev_de->endnode() == candidate_node)                      // RAW
```

A tagged node compared against a raw one. With one region both are 0 and it works; with two they
can never be equal, so every candidate sitting *on a node* fails to be recognised and its point is
reported unmatched. That is why the failures were scattered at intersections rather than at the
frontier.

**Result: 770 / 770, and 150.064 km against the monolith's 150.059.**

> **The harness lied twice in one hour, both times by my own hand, and both times it pointed the
> investigation backwards.** `grep -c` exits 1 when the count is zero, so `make ... | grep -c error:
> && make install` silently skipped the install and a whole round of measurements ran against a
> stale binary. And `docker exec -e VAR=""` *sets* the variable, so `getenv() != nullptr` is true
> for it — the run labelled "tag kept" had the tag stripped, which made the decisive experiment
> read as "no difference". Neither is a Valhalla fact; both are why the numbers above were
> re-measured on a known-good build before being believed.

### A finding that favours the architecture

Comparing manoeuvre counts turned up something that is not a composite defect at all:

| route | monolith | composite |
|---|---|---|
| Chisinau -> Balti (internal) | 25 | 26 |
| Chisinau -> Cahul (internal) | 28 | 28 |
| Iasi -> Bucharest (internal) | 48 | 48 |
| Bucharest -> Cluj (internal) | 44 | 46 |
| **Chisinau -> Iasi (crosses)** | **325** | **35** |
| **Chisinau -> Bucharest (crosses)** | **87** | **59** |

Internal routes agree to within a manoeuvre or two. The blow-up happens only when the route
crosses the frontier, and the extra instructions are 33 consecutive *"Keep left / right / straight
**to stay on** M1/E 581"* inside one 2.4 km stretch — the Leuseni-Albita complex. A single-pass
build ingests two Geofabrik extracts that **overlap at the border**, so the shared strip is
imported twice and every node there reads as a fork. The composite, holding each country in its
own graph and joining them with portals, does not have that problem.

Rebuilding the reference with a full config and a real admin database changed nothing (456.458 km
and 87 manoeuvres either way), which rules out the build config and leaves the overlap.

**Not yet proven:** the duplication itself was inferred from the instruction text and the fact
that it is confined to the border; a probe at one point on M1 found no duplicate edges, so the
exact mechanism is still open. Recorded as a lead, not a result.

## Matrix and isochrones — the same defect, twice more

Both remaining services turned out to be the same class: an independent graph traversal that knew
nothing of portals, plus a namespace dropped somewhere along the way. Valhalla has **four** of
these, and that is the whole reason one route test was never enough:

| service | its own traversal |
|---|---|
| route / timed route | `thor/bidirectional_astar.cc`, `unidirectional_astar.cc` |
| `sources_to_targets` | `thor/costmatrix.cc` |
| `isochrone` | `thor/dijkstras.cc` |
| `trace_route` | `meili/routing.cc`, plus its own candidate search |

**The matrix** returned 111.578 km for Chisinau -> Iasi against the monolith's 150.1, snapping the
target onto a Moldovan road. The detector named the cause: `loki_worker_t::matrix` had its own
`search_.search` — the third after route and trace. Rather than write the multiplex a third time,
it moved into `valhalla/loki/search.h` as `WeDriveCorrelate` and **all six** call sites now use it.

Inside `costmatrix.cc` the fix was a region tag on the level transition plus portal expansion — and
then a crash: `NodeInfo index out of bounds: 3111,0,23826 nodecount=3330`. The `get_opp_edge_data`
lambda picked a tile from a raw `endnode()` and then read the opposing edge out of the *wrong
region's* tile. Tile 3111 exists in both regions with different node counts, which is exactly what
an out-of-range index looks like.

**Isochrones** needed the same three things in `Dijkstras`, and repeated the lesson of patch 53:
portals live at level 0 (14 pairs) and level 2 (2 pairs), and level 0 is reachable *only* through a
`NodeTransition`. Gating the portal block on `from_transition` would have hidden all fourteen pairs
again. Two prohibitions, two flags.

Then the contour was still clipped at the Prut, and the detector pointed at
`loki_worker_t::isochrones` — a **fourth** separate call. At that point hunting them one at a time
stopped making sense: all six were enumerated at once and the remaining three converted
(`isochrone_action`, `locate_action`, and `exclude_locations` in `worker.cc`). The patch verifies
this by **listing the directory**, not by a list I could forget to update.

### Acceptance, monolith vs composite, tolerance 0.1 km per cell

| | monolith | composite |
|---|---|---|
| nine routes | — | max divergence **0.064 km** |
| timed route | 456.458 | 456.458 |
| matrix 2x2 across the border | 153.397 | 153.447 *(was 111.578 vs 150.1)* |
| isochrone 45 min from the border | span 0.724 | 0.724 *(was 0.516 — clipped at the Prut)* |
| isochrone 60 min from Chisinau | 1.369 | 1.369 |
| trace, 770 GPS points | 150.059 | 150.064 |
| **region lost** | — | **0** |

`tools/service-regress.sh` is that table as a repo tool. It builds its own 770-point trace from the
monolith's geometry, because otherwise a fresh clone would silently *skip* the matching check —
absent precisely where it is needed.

> **The clean-clone run failed, and it was right to.** `apply-patches.sh` ordered patches with
> `sort -t- -k2 -n` over the **full path**. The verifier copies itself to `/tmp/wedrive-verify`, so
> field 2 became `verify/patch` rather than a number; the numeric key degenerated, sort fell back to
> lexicographic, and **`patch-10` ran before `patch-9`**. Patches 10, 14, 19 and 21 then failed on
> the first pass and were only picked up by the second, so the tree converged after two runs and
> everything downstream looked healthy — the verifier applies twice before building. A fresh clone
> applying patches **once** got a tree missing four patches.
>
> My own harness never caught it because it copied to `/tmp/wd`, where there is no hyphen and the
> order happened to be right. That is the third time this session a difference between harnesses was
> more informative than the test itself. Sorting is on the **file name** now, and step 2 of the
> verifier checks the exit code and the count of failed patches instead of grepping for one word.

## Three countries, and updating one of them

The point of the whole exercise, stated as a test: build MD and RO, add HU separately, route across
both borders, then rebuild **only RO** from a newer OSM extract and route again without touching
MD or HU.

Vintages are genuinely different, which is what makes the last step mean anything:

| extract | OSM date |
|---|---|
| moldova | 2026-09-16 |
| romania (before) | 2026-09-01 |
| romania (after) | 2026-09-18 |
| hungary | 2026-09-18 |

Each country is built alone — its own admin database, its own tiles, nothing shared. Two borders,
each with its own pair of region ids: MD=1, RO=2, HU=3, 290 portal rows.

> **`portal_border` took its region ids from nowhere — they were hard-coded 1 and 2.** Fine for two
> countries, wrong the moment there is a second border: the RO-HU table needs 2 and 3, and the
> hard-coded pair would have stamped Hungarian nodes with Romania's namespace. They are arguments
> now, defaulting to 1 and 2 so existing calls are unchanged.

### Across three graphs, against a three-country monolith

| route | monolith | composite |
|---|---|---|
| Chisinau -> Budapest | 1040.868 | 1040.913 |
| Bucharest -> Budapest | 842.788 | 842.792 |
| Iasi -> Debrecen | 667.541 | 667.549 |
| Chisinau -> Bucharest | 456.458 | 456.448 |

45 m over 1041 km. Chisinau -> Budapest crosses **two** borders and reports exactly **two** region
seams — 1->2 at edge 583 and 2->3 at edge 1456 of 2049 — with zero region loss. One physical
frontier, one namespace change.

### Updating one country

Romania's tiles were replaced with the 2026-09-18 build and the portal tables of **its two borders**
regenerated. Nothing else was touched, and the checksums prove it: `moldova_bc` and `hungary_bc`
byte-identical before and after, `romania_bc` changed.

All seven routes came back **identical to the millimetre**, including the ones that run through
Romania. That is the result, and it needed a control before it meant anything — an accidentally
identical rebuild would produce the same table:

| | |
|---|---|
| tiles differing byte-for-byte | **636 of 636** |
| portal id pairs that changed | **20 of 32** |

So the graph really was rebuilt, the ids really did move, and routing was unaffected because the
portal table was regenerated with them.

> **What has to be regenerated is exactly: the country's tiles, and the portal tables of its
> borders.** Neighbouring *graphs* are never rebuilt. That is the whole asymmetry the architecture
> buys, and it is why a portal is an external row rather than an edge inside a `.gph`.

### Forgetting the portal table fails loudly, not silently

The negative test: fresh Romanian tiles against the **stale** MD-RO table — a pipeline that updated
a country and forgot its borders.

```
WEDRIVE: регионов 3, порталов 270, отвергнуто 20
```

Exactly the 20 pairs whose ids moved, rejected by `AddPortal`'s validation; the route still came out
right on the surviving twelve, with no crash and no region loss. Stale portals are a counter, not a
corruption — which is what patch 21 was written for, now demonstrated on a real update rather than
on a hand-made bad table.

`tools/package-update-test.sh` runs this sequence against already-built packages, and
`tools/regen-portals.sh` is the border table as data: pairs of directories, pairs of region ids and
search boxes, in one place.

### The ceiling that now matters

`EdgeLabel::region_` is **3 bits — seven usable regions** (0 means untagged). MD+RO+HU uses three;
Austria would be four. `GraphId` itself has eighteen spare bits and is not the constraint — the
label is, and it is full: `EdgeLabel` is 40 bytes and `BDEdgeLabel` exactly 64, one cache line, both
unchanged by everything above.

Seven is enough for the countries this car actually drives through and **not** enough for a European
deployment. Widening it is the next structural piece, and it is a question about `BDEdgeLabel`'s
cache line rather than about routing.

## Widening region to 8 bits — 255 regions, and the map format untouched

Seven countries were enough for research and are not enough for Europe. `GraphId` was never the
constraint: it carries the region in bits 46..63 and already allowed eighteen. The constraint was
the search label, packed without a single free bit, and five had to be found in it.

**The obvious candidate was wrong, and only a measurement showed it.** `opp_local_idx_` is 7 bits
with `kMaxLocalEdgeIndex = 7` declared right beside it, so three bits looked sufficient.
`tools/field_range.cc` walked every edge of every tileset: the constant bounds a node's *heading
array*, not the field, and **48 edges in the MD+RO+HU monolith hold values up to 12**. Narrowing it
would have silently corrupted them.

The five bits came from where the bound is provable:

| field | before | after | why it is safe |
|---|---|---|---|
| `predecessor_` | 32 | **28** | 268 435 455 labels. At 64 bytes a label that is 17 GB of labels alone — a physical ceiling, not an estimate |
| `mode_` | 4 | **3** | `TravelMode` has five values; a `static_assert` holds it, not a comment |

`kInvalidLabel` occupies all 32 bits, so inside the label it is stored as its own 28-bit marker and
the accessor hands the original constant back out — the global constant is untouched and every
`== kInvalidLabel` outside the label still reads true. Five single-bit flags moved into the freed
space, and the sizes are held by `static_assert` in the header itself: `EdgeLabel` 40 bytes,
`BDEdgeLabel` exactly 64, one cache line.

> **The guard earned its keep on the way through.** `AddRegion` had refused anything above 7 since
> the prototype, and the first attempt to build a portal table with region 8 stopped with
> *"region id 8 exceeds the 8 that EdgeLabel's 3 spare bits can carry"* instead of silently
> truncating to 0 and sending the car into the wrong country. The cap moved with the field
> (8 -> 256); the guard stayed.

### Proven on the graph, not only in a unit test

The same three countries were re-labelled **8, 9 and 10** — past the old ceiling. **No tiles were
rebuilt**: only the config and the portal table changed, which is the point.

| route | regions 1/2/3 | regions 8/9/10 |
|---|---|---|
| Chisinau -> Budapest | 1040.913 | 1040.913 |
| Bucharest -> Budapest | 842.792 | 842.792 |
| Iasi -> Debrecen | 667.549 | 667.549 |
| Chisinau -> Bucharest | 456.448 | 456.448 |

Seams: `8->9` at edge 583 and `9->10` at edge 1456 — the same edges as before, different numbers.
Region lost 0, portals rejected 0.

`gid_test` covers regions 8, 63, 200 and 255 through `GraphId` *and* through the label, the
`kInvalidLabel` round-trip after the narrowing, the 2^28-2 boundary index, and both sizes. The
label's fields are `protected`, so the test reaches them with a derived struct of its own rather
than adding test hooks to a production header.

> **A green suite hid a stand problem, and the tell was a route that cannot possibly be affected.**
> `verify-from-clone` step 9 reported four divergences including **Iasi -> Bucharest, entirely
> inside Romania** — a route no multi-region code can change. The cause was `package-update-test.sh`
> leaving Romania swapped to the 2026-09-18 build, so the next run compared a composite on fresh
> Romania against a monolith on the old one and charged the difference to the code. The test is
> non-destructive now: it restores the previous build, regenerates the portal tables, and
> **compares checksums against the ones it recorded at the start** — proving the restore rather
> than promising it.

## The manifest, and why a portal table carries two versions

First piece of the package pipeline, and its shape is dictated by a measurement rather than by
taste. Updating Romania 2026-09-01 -> 2026-09-18 changed **636 of 636 tiles** and **20 of 32 portal
id pairs**. A portal table therefore belongs not to a border but to a *specific pair of builds*, so
each entry names both versions:

```
portals:
  MD-RO:
    versions: [MD-2026-09-16, RO-2026-09-01]
```

`tools/make-manifest.py build` writes this from what is actually on disk — graph version from the
source extract's OSM timestamp, checksum from the files themselves — and `plan` answers the
question the downloader has to get right:

| country updated | download | leave alone |
|---|---|---|
| **RO** | `ro.tar` + **MD-RO** + **RO-HU** | `md.tar`, `hu.tar` |
| MD | `md.tar` + MD-RO | `ro.tar`, `hu.tar`, RO-HU |
| HU | `hu.tar` + RO-HU | `md.tar`, `ro.tar`, MD-RO |

> **Updating one country pulls ALL of its portal tables, not just the border with a neighbour that
> also changed.** Romania's ids move as a whole when it is rebuilt, and Romania's ids appear in
> both of its tables. Stale ones do not corrupt anything — `AddPortal` rejects them and says how
> many — but the crossings they describe simply stop existing until the tables catch up.

The checksum does real work rather than decorating the file: the two Romanian builds differ by
**0.24 %** in size, so size alone would not tell them apart, while the digests differ from the
first byte.

## Next

1. Teach Thor's bidirectional A* the same re-tagging rule and the portal expansion.
2. Sif costing across a portal — a border crossing has a real cost, and a customs queue is exactly
   the sort of thing the distance-0 portal currently ignores.
3. Only then `libvalhalla-wrapper.so` for Android.
