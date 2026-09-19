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

## Next

1. Teach Thor's bidirectional A* the same re-tagging rule and the portal expansion.
2. Sif costing across a portal — a border crossing has a real cost, and a customs queue is exactly
   the sort of thing the distance-0 portal currently ignores.
3. Only then `libvalhalla-wrapper.so` for Android.
