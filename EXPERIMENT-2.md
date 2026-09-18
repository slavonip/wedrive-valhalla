# Experiment 2 — the blast radius of one OSM edit

Run 2026-09-18 on stock `ghcr.io/valhalla/valhalla@sha256:2b19ea46...49c43` (tag 3.6.3), locally
in Docker, 22 threads. Nothing patched, nothing in production touched, no paid resources.

Experiment 1 asked whether identical input gives identical output. It does. This asks the
question that actually decides the architecture: **when the input changes a little, how much of
the graph moves?**

## Input

```
base    https://download.geofabrik.de/europe/moldova-latest.osm.pbf
        101 119 511 bytes
        sha256 9adf57339cb72d69373abf878c1ad1ff7a3ab2f3bc549a97d18c3a91f5275ae8
        osmosis_replication_timestamp=2026-09-16T20:21:21Z, sequence 4911
```

Target tile chosen as an L2 tile whose **eight neighbours were all built**, so propagation
outwards could be seen if it happened, and small enough to read (1.2 MB rather than Chisinau's
12 MB):

```
2/000/792/834.gph     lon 28.50..28.75   lat 47.50..47.75
1/049/528.gph         the L1 tile above it
0/003/112.gph         the L0 tile above that,  lon 28..32  lat 46..50
```

Target way: **OSM way 44278477**, `highway=primary`, "Strada Națională", 8 nodes, midpoint
47.57479, 28.56396 — every node at least 0.03° clear of the tile edges.

```
M1   modify   rename it to "Strada Națională WEDRIVE-M1"        no topology change
M2   create   two new nodes + one residential way, attached to
              node 565330077 — a node of that PRIMARY way       topology change
```

Both applied with `osmium apply-changes`, M2 also passed through `osmium sort`. Both verified
present in the PBF **and** in the built graph before anything was concluded.

## TWO MEASUREMENT TRAPS, both hit, both removed

**1. The header stamp reports 100 % of tiles changed.** `osmium apply-changes` drops the osmosis
replication timestamp, so the mutated builds get a different `dataset_id_` — and `checksum_`,
which `graphtileheader.h` documents as *"for road tiles: hashed md5 of the OSM PBFs"*. Both are
per-build constants present in **every** tile:

```
byte 32..40   dataset_id_    A/B 23067d4d03000000   M1/M2 0100000000000000
byte 88..96   checksum_      A/B 6573455d331a83e4   M1 06efa960e043cfa9  M2 ebdd3e4da2a40a31
```

Left in, every tile differs by exactly 13 bytes and the answer is "114 of 114 changed". This
repository already recorded this trap — *"four bytes of build stamp at offset 32 that made the
first run report 100 %"* — and it was walked into again. **Everything below masks 32..40 and
88..96 and nothing else.**

**2. The wrong L1 tile was sampled first.** `1/049/888` covers latitude 48–49; the edit is at
47.57. The tile above the edit is `1/049/528`. A sample picked by eye rather than computed is
how a propagation map ends up pointing at the wrong place.

## M1 — one tag, on one primary way

```
                           nodes             directed edges
2/000/792/834  L2    5496 -> 5496       13825 -> 13825      UNCHANGED
1/049/528      L1   14447 -> 14447      31132 -> 31132      UNCHANGED
0/003/112      L0   13042 -> 13042      28934 -> 28934      changed, +32 bytes:
                          textlist   2436 of   9792 bytes  (24.9 %)
                          edgeinfo   4009 of 776200 bytes  ( 0.5 %)
                          fixed        26 of 1897736 bytes
```

**Exactly one tile of 114 changed**, and only its name-bearing sections. Node and edge counts
did not move anywhere.

The tile is the **level 0** one because `primary` is a level-0 road class in Valhalla — confirmed
independently: the string `WEDRIVE-M1` appears exactly once in the whole graph, in `0/003/112.gph`
and nowhere else.

**An attribute-only edit is perfectly local.**

## M2 — one new way, two new nodes

> **This mutation is a TOPOLOGY change that also touched a LEVEL-0 ROAD.** It attached to an
> existing node of the primary way, which makes that node a junction and splits a level-0 edge.
> So M2 conflates "add a local street" with "split a highway". That is realistic — real OSM edits
> do exactly this — but it is not the isolated case, and experiment 3 separates them.

```
                        counts                    fixed      edgeinfo   textlist
2/000/792/834  L2   +2 nodes  +2 edges           62.2 %      93.0 %     94.1 %   +232 B
0/003/112      L0   +1 node   +2 edges           57.7 %      90.7 %     95.7 %   +168 B
1/049/528      L1   counts UNCHANGED             627 bytes        —          —
2/000/791/394  ring 1, counts UNCHANGED          369 bytes
2/000/787/074  ring 4, counts UNCHANGED          256 bytes
2/000/785/640  ring 6, counts UNCHANGED          318 bytes
```

**45 tiles of 114 changed**, in two qualitatively different classes:

| | |
|---|---|
| **2 tiles** | direct data change **plus** massive ID churn. Two nodes added to a tile holding 5496 — **0.036 % of its content** — rewrote **62–94 % of the file** |
| **43 tiles** | **pure reference churn.** Node and edge counts identical; only the fixed-record section differs, by 44–627 bytes. That section is where `GraphId`s and `endnode` references live |

The 93 % in `edgeinfo` and 94 % in `textlist` is index-as-identity seen from the other side:
both are addressed by offset, so inserting anything shifts everything after it.

## The radius is bounded — but not by distance

A level-2 tile **six rings away** changed. That is ~120 km, and no level-2 edge reaches it, so a
horizontal explanation was already in trouble. Checked geographically instead:

```
level-0 tiles changed:  3112 (lon 28..32, lat 46..50)
                        3111 (lon 24..28, lat 46..50)

non-level-0 tiles                                     111
   changed AND inside a changed L0 cell                43
   changed but OUTSIDE any changed L0 cell              0
   inside a changed L0 cell but unchanged              57
```

**Nothing changed outside the affected 4° level-0 cells.** Inside them, only the tiles that
actually held a reference to something renumbered — not all of them.

> **MECHANISM — INFERENCE, NOT PROOF.** The likely explanation is that a level-2 tile carries
> `NodeTransition`s into the level-0 tile above it; the level-0 tile's node ids moved, so every
> level-2 tile inside that 4° cell holding such a transition had to be rewritten. It fits: the
> distant tiles changed **only** in the fixed-record section, with counts unchanged, which is
> where transitions live. **It has not been demonstrated.** Nobody has decoded a transition
> record and shown the specific GraphId before and after. Experiment 3 does that, and may refute
> it.

## What it means for the 74.6 %

The amplification is measured, not assumed: **0.036 % of a tile's content changed, 62–94 % of its
bytes moved**, and one edit reached 45 of 114 tiles. So the 74.6 % of tiles changing over 16 days
is **fully consistent with ID churn** and is no evidence of 74.6 % real change.

It is still not decomposed into real change versus induced churn — that needs a different
measurement. What has changed is that the claim "it must be real OSM change", made after
experiment 1 and retracted, now has positive evidence against it.

## And for the architecture

Moldova is a poor country for judging the *relative* size of a closure: two 4° cells cover almost
all of it, so "bounded by the L0 cell" is very nearly "bounded by the country". On Europe a 4°
cell is a small fraction, and the number worth measuring is closure bytes against the size of the
country being updated — not against a count of Moldovan files.

## Reproducing

```
experiments/02-closure/make_mutations.py    pick the target way, write both .osc, apply them
experiments/02-closure/fix_m2.py            M2 again with ids that keep PBF sort order
experiments/02-closure/closure.sh           build M1 and M2
experiments/02-closure/closure2.py          changed tiles, header masked, by level and ring
experiments/02-closure/sections.py          which SECTION of each tile moved
experiments/02-closure/vertical.py          are the changes confined to the L0 cells
experiments/02-closure/verify_mutations.py  did the edits reach the PBF and the graph
experiments/02-closure/byteranges.py        which byte ranges differ, before trusting any count
```

An early failure worth keeping: M2 first used negative OSM ids, as a `.osc` normally does for
not-yet-uploaded objects. `valhalla_build_tiles` refused the result with
`Detected unsorted input data` — a PBF must be ordered by type then ascending id. High positive
ids plus an explicit `osmium sort` pass fixed it.
