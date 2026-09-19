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

- Mjolnir. Tiles are built by unmodified `valhalla_build_tiles`.
- The `.gph` format, including `GraphTileHeader` (272 B, `static_assert`-ed), `NodeInfo` (32 B),
  `NodeTransition` (8 B) and `DirectedEdge` (48 B).
- Thor, Sif and Odin. The proof harness is separate, on purpose: changing the runtime's *reader*
  and changing its *search* are two risks and were taken one at a time.

## Next

1. Teach Thor's bidirectional A* the same re-tagging rule and the portal expansion.
2. Sif costing across a portal — a border crossing has a real cost, and a customs queue is exactly
   the sort of thing the distance-0 portal currently ignores.
3. Only then `libvalhalla-wrapper.so` for Android.
