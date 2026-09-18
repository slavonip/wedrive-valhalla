# Experiment 4 — can one country be updated while its neighbours stay behind?

Run 2026-09-18 on stock 3.6.3, locally in Docker, 22 threads. No patches, no production change, no
paid resources.

## Design — one variable

Two masters built from real dated Geofabrik snapshots, differing in exactly one country's
fortnight. Romania and every country it borders, so Romania's cut has no artificial frontier.

```
T0    RO,HU,RS,BG,MD,UA        all @ 2026-09-01
REF   HU,RS,BG,MD,UA @ 09-01  +  RO @ 2026-09-14
```

Building "everything at T1" was rejected: if Hungary also advanced, "I updated only Romania"
would not be expressible. Experiment 1 established the builder is deterministic for identical
input, so every difference between T0 and REF traces to Romania.

```
master-T0    2 049 702 966 B        master-REF   2 050 594 734 B
                                    difference      891 768 B  — Romania's fortnight
T0 build 7m07s, REF build 7m07s, tile stage 401 s each, 2 827 tiles, 2.2 GB per master
cuts: 2 642 distinct tiles, 2.150 GB, 251 shared by more than one country (1.17x overhead)
```

### Four assemblies

```
REF                 the coherent master. The correct answer.
BROKEN_MIXED        neighbours @ T0 + Romania's cut from REF, and nothing else.  THE CONTROL.
FULL_DIFF_MIXED     neighbours @ T0 + Romania + every tile that DIFFERS between T0 and REF.
MIXED               same as above in this run; kept as a separate label for the full diff.
```

> **`FULL_DIFF_MIXED` was called `MINIMAL_MIXED` while the experiment ran, and the run output
> below still says so. The name was wrong and is corrected here.** It is not a minimal closure —
> see "what failed" below. Nothing about it was computed by a dependency-closure algorithm.

The control is the point. Without it, a working MIXED would show only that some assembly routes
correctly, never that the closure was needed.

## MEASURED

### Routes — 8 pairs, every endpoint already validated by a passing gate in the Europe build

```
route                                  REF        FULL_DIFF   BROKEN_MIXED
MD -> RO  Chisinau to Iasi           150.2 km    150.2  =    150.2  =
HU -> RO  across the frontier         89.5 km     89.5  =     80.5   jump 6.4 km
RO -> UA  Iasi to Chernivtsi         229.8 km    229.8  =    224.8   jump 266.6 km
BG -> RO  Ruse to Giurgiu              3.2 km      3.2  =      3.2  =
HU -> MD  Budapest to Chisinau      1106.7 km   1106.7  =    769.8   jump 382.4 km
BG -> HU  Sofia to Budapest          773.3 km    773.3  =    546.8   jump 363.1 km
MD -> UA  Chisinau to Odesa  [ctrl]  195.7 km    195.7  =    195.7  =
HU -> UA  Debrecen to Uzhhorod [ctrl] 145.4 km   145.4  =    100.8   jump 180.9 km

FULL_DIFF_MIXED vs REF   8 of 8 identical route-shape SHA
BROKEN_MIXED    vs REF   3 identical, 5 different, 0 refusals
```

Comparison is by **SHA of the concatenated route geometry**, so "identical" means the same
sequence of points, not merely similar numbers.

**The causal chain is closed:** remove the closure and the geometry tears reproducibly, in the
same class as the 294.89 km teleport that started this whole investigation; put the closure back
and the route matches the coherent reference exactly.

### The damage is not confined to the updated country

`HU -> UA Debrecen to Uzhhorod` does not pass through Romania. It broke anyway, with a 180.9 km
jump. Hungarian and Ukrainian tiles reference Romanian tiles whose ids moved, through shared
level-0 cells — so a Romania-only update corrupts routes that never enter Romania.

This was a control expected to stay clean. It did not, and that is a stronger result than the
Romanian routes breaking.

### Volumes

```
X    full Romania package                      0.473 GB   573 tiles
Y    Romania tiles that DIFFER                 0.467 GB   566 tiles   98.8 % of X
Zall Romania + every differing neighbour tile  ~1.00 GB   +535 tiles  212 % of X
Zmin the minimum correct update                UNKNOWN — not computed, see below
```

**212 % is `Zall / X`: an upper OBSERVED bound, not the cost of a minimal correct update.**

Observed per-country churn caused by Romania's fortnight alone:

```
RO 98.8 %   BG 98.7 %   RS 68.2 %   MD 43.8 %   HU 35.4 %   UA 25.5 %
```

### Counts

```
tiles differing across the whole build         1103
   with node/edge COUNTS changed                185
   differing with counts UNCHANGED              918
```

## WHAT FAILED, and it was mine

The dependency-closure scan did not work. It looked for 64-bit words whose low 25 bits match a
renumbered tile's `(level, tile)` key. A **negative control** — searching for the keys of tiles
that do not exist in this build at all — settled it:

```
tiles outside Romania                       2069
matching a RENUMBERED tile's key            1423
matching a NON-EXISTENT tile's key          1690   <- pure chance
```

25 bits against millions of words per tile: a coincidence is likelier than a reference. The scan
is noise, so **no dependency closure was computed**, and the set used was simply "every tile that
differs". `Zmin` remains unknown.

Running the negative control was the only reason this was caught rather than published as a
result.

## NOT ESTABLISHED — interpretations, held separately from the measurements

* **The 918 tiles that differ with unchanged counts are PROBABLY reference churn.** Experiments 2
  and 3 demonstrated that mechanism directly, including 315 of 315 changed words in a distant tile
  resolving to references into a renumbered level-0 tile. But experiment 4 decoded none of these
  918. It is a strong working interpretation, not a measurement.
* **`Y = 98.8 %` means BYTES DIFFER, not BYTES REQUIRED.** Experiment 2 measured an insertion
  worth 0.036 % of a tile's content rewriting 62–94 % of its bytes. So Romania's package
  differing by 98.8 % does not establish that 98.8 % of it must be downloaded for a correct
  update — only that 98.8 % of it is not byte-identical. Separating the two is exactly what a
  real closure would do, and it has not been done.
* **Whether the economics are actually bad is therefore still open.** On these numbers an
  independent Romania update costs about twice the Romania package and 47 % of the whole
  six-country installed set, which would make it pointless. But that figure is `Zall`, and the
  question the architecture turns on is `Zmin`.

## Experiment 5 — the question this leaves

**Decode the real reference fields of `.gph` and compute the exact dependency closure.**

Not a search for 64-bit words that look like GraphIds: a structural read of `NodeInfo`,
`DirectedEdge`, `NodeTransition`, the hierarchy and the shortcuts, so a reference is identified by
where it sits rather than by what it resembles. Then:

```
T0 -> Romania update -> EXACT closure -> EXACT_MIXED
require EXACT_MIXED == REF on every targeted route and geometry SHA
and require that removing ANY single tile of that closure reproducibly reintroduces a stale
reference or a route difference, wherever one can be observed by routing
```

The second half matters as much as the first. A closure that is merely sufficient proves nothing
about minimality, and this experiment has already shown that an absent failure is not an absent
defect.

**No Valhalla patch, no format change, no production change until `Zmin` exists.**

## Reproducing

```
experiments/04-incremental/exp4_fetch.sh       twelve dated snapshots, hashes recorded
experiments/04-incremental/exp4_build.sh       merge and build both masters, cut into six
experiments/04-incremental/exp4_closure2.py    diff, the (failed) scan, the four assemblies
experiments/04-incremental/exp4_verify.py      the negative control that invalidated the scan
experiments/04-incremental/exp4_routes.py      eight routes, compared by geometry SHA
experiments/04-incremental/exp4_run_routes.sh  configs plus the comparison
```
