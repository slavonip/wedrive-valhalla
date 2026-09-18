# Experiment 6 — why the ids cannot be stable, and why it stopped mattering

Run 2026-09-19 on stock 3.6.3. Nothing patched, no format change, production untouched, no paid
resources.

Experiment 5 localised the problem: the closure is computable and causally necessary, but the
dominant cost is a country's own package turning over almost entirely in a fortnight, because
indices are identity. This asks whether that first cause can be removed — and then finds a way
round it that needs no change to Valhalla at all.

## Part A — the full lifecycle of a local id, from the source

### Where it is born

`src/mjolnir/graphbuilder.cc:1228`

```cpp
graphtile.nodes().back().set_edge_index(graphtile.directededges().size() -
                                        bundle.node_edges.size());
graphtile.nodes().back().set_edge_count(bundle.node_edges.size());
```

**`edge_index` is the size of the directed-edge vector at the moment the node is written** — a
running total over every previously emitted node's edge count. `graphtilebuilder.cc:287,297` then
writes `set_nodecount(nodes_builder_.size())` and `set_directededgecount(directededges_builder_
.size())`, so ids are `0..N-1` by construction.

**An edge's id is not a name. It is its ordinal position in a cumulative sum.** Insert one edge at
node *k* and every edge after it is renamed. That is the first cause, stated exactly, and it
explains experiment 2's measurement of 0.036 % of a tile's content rewriting 62–94 % of its bytes.

There is no indirection anywhere: a search for `remap|indirect|id_map|stable|reserved` across the
builder returns nothing but an unrelated `stable_sort`.

### The invariants that stable ids would have to break

| | invariant | where it lives |
|---|---|---|
| **I1** | `node.id()` is a dense array index | `nodes_[node.id()]` |
| **I2** | `edge.id()` is a dense array index | `directededges_[edge.id()]` |
| **I3** | a node's edges are a **contiguous run** from `edge_index()` | iteration `for (j<edge_count(); ++j, ++edgeid)` — graphfilter ×3, graphvalidator, hierarchybuilder, shortcutbuilder ×3, thor |
| **I4** | the opposing edge is found by **arithmetic, not search** | `node(endnode.id())->edge_index() + edge->opp_index()` — graphtile.h:419, graphreader.cc:721/881/895/928 |
| **I5** | `opp_index_`, `localedgeidx_`, `opp_local_idx_`, `shortcut_`, `superseded_` are **7-bit offsets inside a run**, not ids | directededge.h:1212, 1300–1303 |
| **I6** | a node's transitions are a contiguous run; `transition_count_` is 3 bits | graphtile.h:447 |
| **I7** | membership is tested by **range containment** | graphreader.cc:806 |

`edge_index()` appears at 59 call sites; `GetOpposingEdge*` at 41 across 11 files.

### The options, and why none of A, B, D is the answer

* **A — reserved slots.** Breaks I3 and I4 outright: both `edge_index + opp_index` and
  `++edgeid` assume no gaps. The format would be unchanged and the graph unreadable.
* **B — stable ordering (sort by OSM id).** Gives determinism, which experiment 1 showed already
  exists. It does not give stability: an insertion still shifts everything after it.
* **C — an indirection table**, stable id → slot. Works, and requires a new tile section, changed
  accessors, a format change and a rebuilt `libvalhalla-wrapper.so`.
* **D — coherent generations**, the current architecture.

**So insertion-stable ids are not reachable without changing the format.** Dense indexing is
structural, not an accident of Mjolnir.

## Part B — the question none of A–D asked

Every option above tries to stop the bytes from changing. None asks **how much information the
change actually contains.** Renumbering DISPLACES content; it does not invent it. That is exactly
what a binary delta is for, and it needs no change to Valhalla whatsoever.

The architecture it allows is not mixed generations:

```
the car holds coherent generation N
the server builds coherent N+1 and diffs every tile
the car downloads PATCHES and reconstructs N+1 byte for byte
```

There is then **no mixed graph and no closure** — the tiles the car ends up with are precisely the
ones the server built, and everything experiments 4 and 5 measured about stale references simply
never arises.

### Four tiles, three algorithms, reconstruction verified

```
tile                bytes    zstd -19   zstd --patch-from   xdelta3   bsdiff   verify
small L2          299 960       36 %          4 %             4 %      1 %    all ok
large L2       16 772 416       29 %          9 %            25 %      2 %    all ok
L1              4 845 832       32 %          9 %            13 %      4 %    all ok
L0             12 246 856       34 %         10 %            16 %      3 %    all ok
```

**The algorithms differ by up to six times, so testing one would have been a mistake.** The
obvious choice — `zstd --patch-from` — loses to `bsdiff` by two to three times, and `xdelta3`
collapses to 25 % on the largest tile. bsdiff wins because it suffix-sorts to find *displaced*
matches, where a streaming compressor sees only novel bytes at the displacement.

### All of Romania, every tile, every reconstruction checked

```
573 tiles         byte-identical 0     patched and VERIFIED 573     failed 0

full new package        504 871 224 B    481.5 MB
every tile, zstd -19    182 340 168 B    173.9 MB    36.1 %
BSDIFF PATCHES            9 128 912 B      8.7 MB     1.81 %

worst single tile 52 %
```

**8.7 MB instead of 481.5 MB.** Not one tile of 573 was byte-identical — the fortnight really did
change all of them, exactly as experiment 5 measured — and the patches still come to 1.81 %. The
churn is real and almost entirely predictable from the previous version.

### All six countries, every tile, every reconstruction checked

```
2827 tiles      byte-identical 0      patched and VERIFIED 2827      failed 0

full graph              2 304 369 208 B   2197.6 MB
changed tiles, zstd -19   798 943 490 B    761.9 MB   34.67 %
BSDIFF PATCHES             11 584 685 B     11.0 MB    0.50 %

worst single tile   2/000/764/033.gph at 54 %
creating all patches      504.2 s   (server, single-threaded)
APPLYING all patches       17.9 s   (what the car does)
peak bspatch RSS           45 MB    on the largest tile, which is 21 MB
```

**0.50 % for the whole installed set, and the car's side costs 17.9 seconds and 45 MB.** The
memory figure is the one that could have killed this: `bsdiff` needs roughly 17x the file size to
CREATE a patch, but that is the server's problem — `bspatch` needed about twice the tile size,
which a head unit has.

> **Not one tile of 2827 was byte-identical**, while experiment 5's masked comparison found 1103
> differing. The difference is the header: `dataset_id_` and `checksum_` move on any change to the
> input, in every tile. So "send nothing for this tile" is never available — but 11 MB across 2827
> tiles shows most of them differ by little more than those 13 bytes.

## THE FIRST ATTEMPT AT THIS REPORTED 2827 OF 2827 FAILED, and it was the harness

`bspatch` had been wrapped in `/usr/bin/time -f %M`, which the container does not have. The
command died before writing its output, every `sha256sum` then had nothing to read, and the run
printed a total failure. The patch SIZES from it were real; the verification had not happened.
Peak memory is now read from `/proc/<pid>/status` instead.

Worth keeping because the failure mode is the inverse of the usual one: a broken instrument
reported a catastrophe rather than a success, which is the safe direction — but it is the same
class of defect as measuring with a tool that is not there.

## What this settles

**The `Zmin` question is moot.** Experiments 4 and 5 asked what must travel when generations are
mixed. If generations are not mixed, nothing but patches travels, and the 432-tile closure, the
199 % figure and the stale `NodeTransition`s stop being costs to pay. They remain the measurement
of why mixing would be expensive.

**Option C is not needed.** No format change, no rebuilt `.so`, no Mjolnir patch, stock 3.6.3
throughout — and Europe is not re-downloaded.

## What is NOT settled

* **What applying the patches costs on the CAR's OWN hardware.** 17.9 s and 45 MB were measured
  on this machine, which is not an ECARX head unit. The figures are small enough that an order of
  magnitude either way would not change the conclusion, but they are not measurements of the car.
* **Whether a month behaves like a fortnight.** One interval was measured. A车 that skips three
  months compares against a much older base, and delta size against a distant ancestor is not
  established.
* **The storage cost on the server**, which must keep every generation a car might be updating
  from, or accept that a car too far behind downloads whole tiles.
* **What happens to a tile that is genuinely rewritten.** One tile needed 52 %, so the worst case
  is not the average, and a package with many such tiles would behave differently.

## Reproducing

```
experiments/06-stable-ids/exp6_all.sh        the id lifecycle, from the sources
experiments/06-stable-ids/exp6_scope.sh      how widely contiguity is relied upon
experiments/06-stable-ids/exp6e_build_image.sh   stock 3.6.3 plus the three delta tools
experiments/06-stable-ids/exp6e_s.sh         four tiles, three algorithms, verified
experiments/06-stable-ids/exp6e_full.sh      all of Romania, every reconstruction checked
experiments/06-stable-ids/exp6e_all.sh       all six countries, with timing and peak memory
```
