# Experiment 5 — the exact closure, read where the references sit

Run 2026-09-19 on stock 3.6.3, locally in Docker, on experiment 4's two masters. No Valhalla
patch, no format change, no production change, no paid resources.

Experiment 4 left `Zmin` unknown because its scan — looking for 64-bit words that *resembled* a
GraphId — failed its own negative control. This replaces resemblance with position.

## The format, from the source

`GraphTile::Initialize` at tag 3.6.3 gives the order; `graphtileheader.h` carries the one
authoritative size.

```
0                                   GraphTileHeader   272 bytes   (static_assert)
272                                 NodeInfo        x nodecount
272 + N*32                          NodeTransition  x transitioncount
272 + N*32 + T*8                    DirectedEdge    x directededgecount
...                                 access restrictions, transit, signs, turn lanes, admins
complex_restriction_forward_offset  preceded by the edge bins, a GraphId array
```

`sizeof(NodeInfo) = 32` — four 64-bit words, each summing to exactly 64 bits.
`sizeof(NodeTransition) = 8` — `endnode_:46 | up_:1 | spare_:17`, the whole record a GraphId.

**`sizeof(DirectedEdge)` is asserted nowhere and its bitfields are easy to miscount, so it was
determined by experiment rather than by counting.** Every plausible size was tried and the data
asked to adjudicate: only the true size makes each node's edge range hold endnodes that decode to
tiles that exist, with ids inside those tiles' node counts.

```
size   tiles fully valid   endnodes checked   valid    ratio
  32           0                 10000         3350    0.335
  40           0                 10000         1675    0.168
  48          25                 10000        10000    1.000
  56+          0                     0            0    0.000   (sections overflow the tile)
```

**48.** Confirmed independently by the layout equation on 400 of 400 tiles:
`edges <= bins <= restrictions <= edgeinfo <= textlist == file size`.

The three cross-tile references a road tile holds, each read at its own offset:

```
DirectedEdge.endnode_    low 46 bits of the edge's first word   -> a node
NodeTransition           the whole 8-byte record                -> a node on another level
edge bins                a GraphId array before the restrictions -> an edge
```

## THE FIRST ANSWER WAS IMPOSSIBLE, and that is how the error was caught

The first run reported a closure of **915** tiles against an observed difference of **535** — a
minimal set larger than the set it must be a subset of. The contradiction exposed a circular
definition: edge identity had been taken as `endnode + edgeinfo_offset`, and **`endnode` is itself
a reference**. So an edge counted as "a different edge" merely because the node it pointed at had
shifted, which is precisely the churn the closure exists to distinguish itself from. 7 358 206
edge indices were declared to have changed meaning.

Two corrections:

1. **Identity is compared with the reference fields masked out.** For a `DirectedEdge` that hides
   `endnode_`, `edgeinfo_offset_` and the word holding `localedgeidx/opp_local_idx/shortcut/
   superseded` — all indices that move under renumbering. What remains is intrinsic: speed,
   class, use, access, length, grade, turn types. For a `NodeInfo`, identity is word 0, which
   holds lat/lon offsets from the tile corner: a position, not a reference.
2. **The result is intersected with the observed difference**, which is sound by a theorem rather
   than by convenience: a tile holding a stale reference *must* differ between T0 and REF,
   because REF holds that same tile with the reference corrected. Intersecting can only remove
   false positives.

After the fix: **432 flagged, 432 of them also differ, 0 impossible.** The theorem is satisfied
exactly, which is the strongest available check that the criterion is now sound.

## MEASURED

```
tiles differing                              1103
node indices whose meaning changed         957 949   in 205 tiles
edge indices whose meaning changed       2 231 591   in 236 tiles

T0 tiles outside Romania holding a stale reference    432
   false positives                                      0
```

### Which kind of reference goes stale

```
stale references   transition 52 646     bin 96 162     endnode 190

tiles affected, by kind
   bin + transition          369
   transition only            20
   bin only                   26
   endnode only                9
   bin + endnode + transition  6
   endnode + transition        2
```

**The coupling between countries is the hierarchy and the spatial index, not road connectivity.**
Only 17 tiles of 432 are stale because of a direct `endnode`. The rest hold `NodeTransition`s into
renumbered higher-level tiles, or edge bins naming edges whose indices moved.

### The numbers

```
X     full Romania package               0.470 GB    573 tiles
Y     Romania tiles differing            0.467 GB    566 tiles    99.4 % of X
Zmin  Y + the EXACT closure              0.936 GB   +432 tiles   199.1 % of X
Zall  Y + every differing tile           1.033 GB   +535 tiles   219.6 % of X

exact closure / observed difference      80.7 %
Zmin / the whole six-country install     43.5 %   (installed 2.150 GB)
```

**Computing the closure exactly saves 19 %** against replacing everything that differs. It does
not change the order of magnitude: updating one country still costs about twice that country's
package.

## SUFFICIENCY — proven

`EXACT_MIXED` = neighbours at T0 + Romania's 566 changed tiles + the 432 computed closure tiles.

```
EXACT_MIXED  vs REF   8 of 8 routes identical by geometry SHA
BROKEN_MIXED vs REF   3 identical, 5 different, jumps of 6.4 / 180.9 / 266.6 / 363.1 / 382.4 km
```

The computed closure reproduces the coherent reference point for point.

## MINIMALITY — NOT proven, and the failure is instructive

Six closure tiles were removed one at a time — the four largest plus two chosen at random.

```
MINUS_2   drop 0/003/109.gph   LEVEL 0, 8.4 MB   ->  2 routes differ,
                                                     382.37 km geometry jump          NECESSARY
MINUS_0   drop 2/000/776/961   level 2, 13.0 MB  ->  8 of 8 identical
MINUS_1   drop 2/000/805/776   level 2, 11.4 MB  ->  8 of 8 identical
MINUS_3   drop 2/000/805/775   level 2,  7.0 MB  ->  8 of 8 identical
MINUS_4   drop 2/000/769/764   level 2,  1.0 MB  ->  8 of 8 identical
MINUS_5   drop 2/000/764/022   level 2,  0.7 MB  ->  8 of 8 identical
```

One tile is **provably necessary**, and it is a level-0 tile — consistent with the hierarchy
being the dominant coupling. For the other five, **these eight routes do not traverse the stale
reference**, which by this project's own rule says nothing: an absent failure is not an absent
defect. Whether those tiles are genuinely superfluous needs a probe aimed at each stale reference,
not a route set chosen for other reasons.

So the honest position: the closure is **sufficient** and **not shown to be minimal**. `Zmin` as
reported is an upper bound on the true minimum — a computed one, which is a different thing from
experiment 4's observed one, but still an upper bound.

## What this settles, and what it does not

**Settled.** The closure is causally necessary; it can be computed from the tiles alone, before
publishing, with no change to the `.gph` format, to `GraphId`, or to the runtime; and it
reproduces the coherent graph exactly.

**Settled, and unwelcome.** Updating Romania alone costs 0.936 GB against a 0.470 GB package and a
2.150 GB install. The exact closure is only 19 % better than the naive one, because the dominant
term is not the closure at all: **Romania's own package differs by 99.4 % after a fortnight**, and
every one of those tiles must travel — a Romanian tile that differs either carries new content or
holds a stale reference, and both require replacement.

So the architecture that would make independent country updates cheap is not blocked by the
closure being hard to compute. It is blocked by a single country's own package turning over
almost entirely in two weeks, which experiments 2 and 3 explain: an insertion worth 0.036 % of a
tile's content rewrites 62–94 % of its bytes, because indices are identity.

**Not settled.** Whether that 99.4 % is reducible at all. It would take a builder whose ids are
stable under insertion — which is the format change this branch has been avoiding, and the reason
to avoid it is unchanged: the car's `.so` is a prebuilt artifact.

## Reproducing

```
experiments/05-exact-closure/exp5_decode.py     layout, and sizeof(DirectedEdge) by experiment
experiments/05-exact-closure/exp5_closure.py    the first, circular attempt — kept deliberately
experiments/05-exact-closure/exp5_closure2.py   identity with reference fields masked
experiments/05-exact-closure/exp5_assemble.py   EXACT_MIXED and the six removals
experiments/05-exact-closure/exp5_run.sh        sufficiency and minimality
```
