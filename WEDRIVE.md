# WeDrive's fork of Valhalla — why it exists, and what it may not do

Forked from `valhalla/valhalla` at **tag 3.6.3** (`e2f017b16080f49203de245a211b09efab09cf72`,
released 2026-02-19), not from `master`. The version is not a preference: WeDrive's car runs
`libvalhalla-wrapper.so` built from Valhalla 3.6.3 via `io.github.rallista:valhalla-mobile:0.6.1`,
and a builder that disagrees with its runtime is a defect class this project has already met twice.

`master` in this fork tracks upstream and is left alone, so syncing stays trivial. Work happens on
`research/incremental-tiles`.

## The question

WeDrive ships per-country routing tiles cut from ONE coherent build. We want to know whether
countries can instead be built and updated **independently** while staying mutually routable:

```
AT Jul   HU Aug   RO Oct   MD Jun        Vienna -> Chisinau must still route
```

## What is already measured, and must not be re-derived

| observation | value |
|---|---|
| two independently built masters, shared tile paths | **31** |
| of those, byte-identical | **0** |
| a route across that seam | 937 km, 12.04 h, 78 km/h — all plausible |
| ...and its geometry | **294.89 km jump**, 47.1587,23.8874 -> 47.2186,19.9856 |
| the same journey inside ONE master | 1345.7 km, continuous |
| one master, cut by country, shared tiles | **86 of 86 byte-identical** |
| Moldova build vs Romania build | 35 shared paths, 0 identical; all three of Moldova's level-0 tiles overwritten |

This is an OBSERVATION, not a diagnosis. It says stock Mjolnir plus our differing build contexts
produces incompatible tiles. It does not say why, and the whole point of this branch is that
nobody has established why.

## Two facts checked in the source, 2026-09-18

**1. Upstream knows the builder is non-deterministic.** Issue
[#5473](https://github.com/valhalla/valhalla/issues/5473), open since 2025-08-26, no PR attached:
*"the edge index gets assigned by tile building code in a non-deterministic way"*, and the author
wants determinism for exactly our reason — partial tile updates. It names
`valhalla::mjolnir::collect_node_edges` and proposes a `mjolnir.deterministic_edge_indexes` flag.

**2. `local_id` is an ARRAY INDEX, not an identifier.** From `valhalla/baldr/graphtile.h`:

```cpp
const NodeInfo* node(const GraphId& node) const {
  if (node.id() < header_->nodecount()) {
    return &nodes_[node.id()];
  }
}
```

This separates two goals that are easy to conflate, and only the second is what the car needs:

* **determinism** — same input, same output. That is #5473, and sorting fixes it.
* **stability** — *changed* input, unchanged ids for unchanged objects. Not #5473. Inserting one
  node into a sorted contiguous array shifts every later index, so a neighbouring tile's
  `endnode` reference silently points at the wrong node.

## A HYPOTHESIS, recorded as one — determinism may make a rebuild local

Not a finding. Nothing here has measured it, and it is written down only so the next experiment
has something to refute.

*If* the builder is deterministic, then rebuilding tile T shifts T's ids, and neighbour N must fix
its outgoing references into T — but N's own ids come from N's own unchanged input, so N's
numbering might not move, and tiles referencing N might not need rebuilding. That would stop the
cascade at one ring. Without determinism it would stop nowhere.

**Whether it actually stops there is experiment 2**, and the vertical direction is the doubtful
one: an L0 tile is 4°x4° and holds `NodeTransition`s into all 256 L2 tiles beneath it, so a single
changed L2 tile obliges a rebuild of an L0 tile shared by several countries.

Determinism alone also buys delta downloads: today a month's rebuild is measured at 74.6 % of
tiles changed, which would move 92 % of a package. How much of that is real OSM change and how
much is index churn was **unknown** — and experiment 1 has now largely answered it.

## MEASURED 2026-09-18 — experiment 1: stock 3.6.3 IS deterministic

Five clean builds of one fixed Moldova PBF (sha256 `9adf5733...5ae8`) produced **114 of 114
byte-identical tiles**, with an identical digest over the whole tile set, at **1, 4 and 22
threads**. Full write-up in `EXPERIMENT-1.md`.

Three consequences:

* **#5473 is NOT our cause.** The code it names is unchanged in 3.6.3 and there is no
  `deterministic_edge_indexes` option, yet the output is stable — because `Edge::operator<` falls
  through to `llindex_`, which is unique per edge. (It does tie for two distinct *self-loop* edges
  at one node, which is a plausible route to the behaviour the issue reports on other data.)
* **The 74.6 % of tiles changing in 16 days is STILL UNEXPLAINED.** An earlier version of this
  line concluded it must be real OSM change rather than index churn. That does not follow, and
  the error is the exact conflation this branch exists to avoid: determinism is *same input, same
  output*, while the 16-day measurement compared **different** inputs. A small real edit that
  churns the ids of unchanged objects sits between the two and is excluded by nothing measured so
  far. Experiment 2 is what settles it.
* **Non-determinism is off the list of explanations for 31/0.** What remains is input context —
  which makes the dependency closure the next thing to measure rather than one of several.

## WHERE THIS STANDS — four experiments, none of them a patch

| | question | answer |
|---|---|---|
| **1** | is the builder deterministic for identical input? | **YES** — 114/114 byte-identical over five builds at 1, 4 and 22 threads. #5473 is not our cause. |
| **2** | how far does ONE OSM edit reach? | an attribute edit: 1 tile. A topology edit that also split a level-0 road: 45 of 114. Nothing outside the affected 4° cell. |
| **3** | how far does a CLEAN local edit reach? | 6 tiles of 114; 8 on a tile boundary. The NodeTransition mechanism is demonstrated — 315 of 315 changed words in a tile six rings away resolve to references into the renumbered level-0 tile. |
| **4** | can one country be updated while neighbours stay behind? | **the closure is causally necessary** — without it 5 of 8 routes tear, with geometry jumps of 6–382 km; with it, 8 of 8 match the reference by geometry SHA. Damage reaches routes that never enter the updated country. |

**The number the architecture turns on is still missing.** Experiment 4's `Zall/X = 212 %` is an
upper observed bound, not the cost of a minimal correct update. The closure was never computed:
the GraphId scan written for it failed its own negative control (1 690 chance matches against
1 423 claimed hits), so the set used was simply "every tile that differs".

**Experiment 5 is therefore `Zmin`** — a structural decode of `NodeInfo`, `DirectedEdge`,
`NodeTransition`, hierarchy and shortcuts, identifying a reference by where it SITS rather than by
what it resembles; then the requirement that removing any single closure tile reintroduces an
observable defect. Until that exists, whether independent country updates are worth having is
not answerable, and neither is any decision about patching Valhalla.

## Research order — evidence before patches

1. One identical Moldova PBF, two clean stock-3.6.3 builds. Deterministic or not?
2. Read the **cross-tile reference format** — not all of Mjolnir. What may point into another tile?
3. Given one new node in a tile, which other tiles become invalid? Measure the **dependency
   closure**: L2<->L2, L2<->L1<->L0 transitions, shortcuts, restrictions.
4. Semantic diff of the 31 shared tiles, to the FIRST SEMANTIC difference — not the first
   differing byte.
5. Trace that field back through `graphbuilder.cc`, `hierarchybuilder.cc`, `shortcutbuilder.cc`
   to where it is assigned, with file/function/line.
6. Only then: is mixed-generation reachable, and what is the minimum patch?

## Constraints

* **The `.gph` binary format is not to be changed** while any alternative exists. The car's `.so`
  is a prebuilt artifact; changing the format means owning an NDK build of Valhalla, which is
  precisely the cost that made Valhalla an easy adoption in the first place.
* No production change, no paid build, and no patch before a diagnosis. `wedrive-maps` keeps
  using the stock `ghcr.io/valhalla/valhalla:3.6.3` image until this branch proves something.
* Lane-level navigation and AR-HUD are **out of scope here**, deliberately. They are an
  enrichment question — more attributes per edge — and would almost certainly need a format
  change, which is the opposite of this branch's constraint. Solving them together is the worst
  available outcome.
* The coherent Europe build running on 2026-09-18 is the REFERENCE. Any mixed-version graph this
  research produces has to be compared against it for connectivity and geometry.

## Where the pieces live

```
wedrive             the car: Android, UI, AR-HUD, libvalhalla-wrapper.so   (private)
wedrive-maps        the factory: Hetzner, builds, cuts, gates, manifests    (public)
wedrive-valhalla    this: the builder we may end up modifying               (public, MIT)
```

`wedrive-maps` must never vendor Valhalla source. It references a pinned image and nothing else.
