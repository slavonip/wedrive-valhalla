# Experiment 3 — a clean local edit, and the mechanism decoded

Run 2026-09-18, stock 3.6.3, same fixed Moldova PBF
(`9adf57339cb72d69373abf878c1ad1ff7a3ab2f3bc549a97d18c3a91f5275ae8`), 22 threads. Nothing
patched, production untouched, no paid resources.

Experiment 2's topology mutation attached to a node of a **primary** way, so it both added a
street and split a level-0 edge. Its 45-tile blast radius could not be attributed. These two
separate the cases, and then decode what actually moved.

## The mutations

Both attach a new `residential` way (two new nodes) to a node met **only** by local-class ways —
`residential`, `unclassified`, `living_street`. `track` and `service` are excluded because each
carries its own costing treatment, and an edit on one risks measuring the filter rather than the
insertion.

```
M3   node 1999327731  47.64054,28.64065   on way 189291148  living_street
     12.1 km from the nearest edge of L2 tile 792834 — as interior as the tile allows

M4   node 7161095484  47.74999,28.60431   on way 766761780  living_street
     0.00001 deg from the tile's northern edge, so the new way CROSSES into tile 794274
```

> A bug caught before it mattered: the first M4 search accepted a node **5 km outside** the tile,
> because the test was `d > 0.012 → reject` and a negative distance passes that. The boundary
> case has to be `0 < d <= 0.012`.

## Tiles that moved

Header `dataset_id_` and `checksum_` masked throughout, as in experiment 2.

```
M3                                                     M2, for contrast
  6 of 114 tiles      L0 1/3  L1 1/11  L2 4/100          45 of 114
  0/003/112      L0         12 bytes of 2 683 760          1 807 647  (67.4 %)
  1/049/528      L1        273 bytes of 2 892 304                627
  2/000/792/834  L2    899 676 bytes  (70.13 %)  +336       912 954  (71.2 %)
  2/000/792/833  L2         29 bytes
  2/000/794/274  L2         25 bytes
  2/000/792/835  L2         23 bytes

M4
  8 of 114 tiles      L0 1/3  L1 1/11  L2 6/100
  2/000/792/834  L2    870 407 bytes  (67.85 %)  +264   the tile the anchor is in
  2/000/794/274  L2    763 994 bytes  (71.66 %)  +112   the tile the new way crosses INTO
  2/000/794/273  L2         45 bytes
  2/000/794/275  L2         36 bytes
  2/000/795/714  L2         22 bytes
  2/000/792/835  L2          2 bytes
  1/049/528      L1        422 bytes      0/003/112  L0  126 bytes
```

**Nothing changed outside the affected level-0 cell in either case** — 0 tiles, both times.

**The separation worked.** A clean local edit reaches **6 tiles**; the same kind of edit that also
splits a level-0 road reaches **45**. Experiment 2's radius was dominated by the level-0 split, as
suspected.

M4 shows the horizontal dependency directly: because the new way crosses the boundary, **two**
level-2 tiles are rewritten ~70 % each rather than one.

## Churn measured per OSM OBJECT, not per byte

`valhalla_ways_to_edges` is Valhalla's own reader answering "which GraphIds does this OSM way
own". Diffing its output across builds measures ID churn on objects rather than on file offsets.

```
             ways in both     GraphIds moved          new ways
M3              262 503       1 594   (0.607 %)             1
M4              262 503       2 969   (1.131 %)             1
```

**One new residential street moves the GraphIds of 1 594 unrelated OSM ways.**

## The mechanism, decoded

Experiment 2 left this as an inference. A GraphId is `level:3 | tileid:22 | id:21`, so
`value & 0x1FFFFFF` names (level, tile) without needing any struct layout. Reading the changed
regions as aligned 64-bit words and asking what they point at:

*(decoder validated first: way 44278477's edges decode to level 0, tile 3112, ids 16091, 16092,
16095, 16096 — matching `valhalla_ways_to_edges`.)*

```
M2  2/000/785/640   six rings, ~120 km away    315 of 315 changed words
      @36344   A -> L0 t3112 id8672      B -> L0 t3112 id8673
      @36352   A -> L0 t3112 id8673      B -> L0 t3112 id8674
      every one a reference into LEVEL 0 TILE 3112 with the id shifted by +1

M2  2/000/787/074   four rings away            253 of 253 words, same pattern

M2  1/049/528       the L1 tile                387 words -> L2 t792834, ids +2
                                               231 words -> L0 t3112,   ids +1

M3  2/000/792/833   ring 1, clean edit          29 of 29 words -> L2 t792834, ids shifted
M4  2/000/794/273   ring 1, boundary edit       44 of 44 words -> L2 t794274, ids shifted
```

**CONFIRMED.** The distant level-2 tiles hold references into the level-0 tile, and they moved
because the level-0 tile gained a node (+1) and every id after the insertion point shifted by one.
M2's level-0 tile gained a node; M3's did not, and M3 accordingly touched three neighbours instead
of forty-three.

The shift is exactly the count delta: +1 node in L0 shifts L0 ids by 1, +2 nodes in L2 shifts L2
ids by 2.

## The rule this gives

```
a tile's ids shift            <=>  its node/edge COUNTS change
every reference to a shifted id must be rewritten

references come from
   horizontal   neighbouring tiles whose edges cross into it
   vertical     every tile in the same L0/L1 cell holding a NodeTransition into it

and nowhere else -- 0 changed tiles outside the level-0 cell, in all three mutations
```

So the closure is governed by **which level's counts changed**:

| the edit | counts change at | tiles to replace |
|---|---|---|
| attribute only (M1) | nowhere | **1** |
| local topology (M3) | L2 only | **6** |
| local topology on a tile boundary (M4) | two L2 tiles | **8** |
| topology splitting a level-0 road (M2) | L0 **and** L2 | **45** |

## The practical answer

**The minimum set to replace when updating an area is**

```
{ tiles whose own content changed }
      union
{ tiles holding a reference into any tile whose COUNTS changed }
```

and both halves are computable **before publishing**, from the tile headers alone: compare
`nodecount_` and `directededgecount_` between generations to find which tiles renumbered, then
ship every tile that references them.

Nothing here requires a change to the `.gph` format, to GraphId, or to the runtime.

## What is NOT established

* Moldova is a poor country for judging the *relative* size of a closure: two 4° cells cover
  nearly all of it, so "bounded by the level-0 cell" is very nearly "bounded by the country". The
  number that matters is closure bytes against the size of the country being updated, measured on
  a graph where a 4° cell is a small fraction. That is a Romania-scale or Europe-scale experiment.
* Real OSM months contain thousands of edits, not one. Whether their closures stay disjoint or
  saturate is unmeasured — and at 6 tiles per edit over 114 tiles, saturation on a country the
  size of Moldova looks likely, which would explain the 74.6 % figure without any of it being
  real change.
* Shortcut edges were not isolated. None of these mutations touched a road class that carries
  shortcuts, so the question of whether a shortcut can depend on topology outside its own tile
  remains open.
* Nothing has been shown about mixing **generations**. Everything here is one edit against one
  base. The compatibility question — can a tile from October sit beside one from August — needs
  the closure to be replaced as a set and the result routed.

## Reproducing

```
experiments/03-clean-closure/exp3_mutations.py   pick local-only anchors, write and apply both .osc
experiments/03-clean-closure/exp3_run.sh         build M3 and M4, index ways to edges
experiments/03-clean-closure/exp3_report.py      tiles moved, by level and ring; per-way ID churn
experiments/03-clean-closure/decode.py           decode the changed words as GraphIds
```
