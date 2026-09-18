# WeDrive multi-region Valhalla — the design, and what it rests on

This branch is the first in the fork that CHANGES Valhalla's source. `research/incremental-tiles`
read it for six experiments and altered nothing; the question it answered — can generations be
mixed — turned out to be the wrong one to build on. This asks a different one:

> can one routing search run across several INDEPENDENTLY BUILT graphs,
> without changing the `.gph` format?

If it can, there is no Europe master: Moldova, Romania and each slice of Germany are built
separately on free runners, and a national frontier is no different from a line drawn through
Bavaria.

## What the tiles force on us, measured

Two independent Mjolnir runs, each knowing nothing of the other (stock 3.6.3):

```
moldova  114 tiles  114 MB        romania  636 tiles  373 MB

the SAME FILENAME in both:  35        byte-identical: 0
   level 0: 3    level 1: 6    level 2: 26
```

One `tile_dir` cannot hold both. The grid is global, so the same 0.25° cell has the same path in
every build, and the contents disagree because each build numbered its own objects.

## Where a region id can live, and where it cannot

`GraphId` is a plain `uint64_t`, not a bitfield:

```cpp
value = level | (tileid << 3) | (id << 25);     // 46 bits used
constexpr uint64_t kInvalidGraphId = 0x3fffffffffff;
```

**Bits 46..63 are free — 18 of them, 262 144 regions.** And they are free *in memory only*:
`DirectedEdge.endnode_` and `NodeTransition` each store exactly 46 bits, so nothing written into
a tile can carry a region.

That single fact settles two things at once:

* a region tag costs **nothing on disk**, so the format does not change; and
* **a cross-region link cannot be an endnode** — there is nowhere to put the other region. Portals
  have to be an external table. That is not a design preference, it is the only option the format
  leaves.

## What had to change, and what deliberately did not

Checked rather than assumed: `level()`, `tileid()` and `tile_value()` all mask, so region bits in
the high end do not disturb them. Four things did need changing.

| | why |
|---|---|
| `GraphId::tile_base()` | masked to the low 25 bits, which would DROP the region — every region's copy of a tile would then share one cache key and the second load would serve the first's bytes |
| `GraphId::is_valid()` | compared the whole value against `kInvalidGraphId`, so a tagged invalid id read as valid |
| `GraphTile::id()` | returned the header's graphid, which knows no region; the reader decides a cache hit by `tile->id() != graphid.tile_base()`, so a tile must answer with the region it was loaded FOR |
| `GraphReader::GetGraphTile` | gains a region → tile_dir map and picks the directory from the id's region bits |

**Region 0 is the default and `with_region(0)` is the identity**, so a single-region setup is
bit-for-bit the stock behaviour. That is deliberate: the patch stays invisible until a second
region is registered, or every measurement this project has taken would need repeating.

## Order of work

```
0  build STOCK 3.6.3 from source, unmodified        <- first, always
1  build MD and RO independently                     done: 35 shared paths, 0 identical
2  hold both at once, colliding filenames and all    the patch above
3  read a node from each and prove they differ       the first real test
4  one real MD<->RO portal
5  Thor treats a portal as an edge of the search
6  several crossings, and Thor picks
7  cut Moldova artificially in two, compare with whole Moldova
8  only then: carry it into the Android build and rebuild the .so
```

Step 0 is not ceremony. Patching before the toolchain is proven makes "my change broke it" and
"it never built" indistinguishable, and this project has lost time to exactly that confusion more
than once.

## What this does NOT claim

Nothing here has routed anything yet. The patch makes two graphs *loadable at once*; it says
nothing about whether Thor can search across them, which is steps 4–6 and the real question.
