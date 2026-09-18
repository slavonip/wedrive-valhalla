# Experiment 1 — is stock Mjolnir 3.6.3 deterministic for identical input?

Run 2026-09-18 on stock `ghcr.io/valhalla/valhalla@sha256:2b19ea46...49c43` (tag 3.6.3), locally
in Docker. Nothing patched, nothing in production touched, no paid resources.

## Input, fixed once

```
url     https://download.geofabrik.de/europe/moldova-latest.osm.pbf
bytes   101 119 511
sha256  9adf57339cb72d69373abf878c1ad1ff7a3ab2f3bc549a97d18c3a91f5275ae8
```

Downloaded **once** and read by every build. `moldova-latest` is a moving target; downloading
twice would have measured Geofabrik rather than Valhalla.

## Five builds

A, B and C are the experiment as specified: identical PBF, config, image and concurrency.
D and E vary only the thread count, because eu-core builds on a 4-core GitHub runner while
Europe is building on a 16-core Hetzner machine — if concurrency changed the bytes, a build
would not be reproducible off the machine that made it, and delta downloads would be dead before
being attempted.

```
      tiles   threads   sha256 over the whole tile set
A       114        22   6caf4f540c26ce73e749c87df5e50e59222b78f6873a6b7b17ddb508514c2075
B       114        22   6caf4f540c26ce73e749c87df5e50e59222b78f6873a6b7b17ddb508514c2075
C       114        22   6caf4f540c26ce73e749c87df5e50e59222b78f6873a6b7b17ddb508514c2075
D       114         1   6caf4f540c26ce73e749c87df5e50e59222b78f6873a6b7b17ddb508514c2075
E       114         4   6caf4f540c26ce73e749c87df5e50e59222b78f6873a6b7b17ddb508514c2075
```

**114 of 114 tiles byte-identical in every pairing, across three different thread counts.**

The builds are real, not empty: 305 132 routable ways / 3 239 964 nodes, 675 328 graph edges,
508 429 graph nodes, Directed Edge Count 1 350 656, 7004 shortcuts superseding 89 634 edges plus
2190 superseding 32 774. Every one of those counters is identical across all five. The only line
that differs anywhere in the logs is the timestamp, and — between D/E and the rest — the literal
text `Building 100 tiles with N threads`.

## Result

```
tiles total                        114
byte-identical                     114
byte-different                       0
semantic-identical but different     0
semantic-different                   0

FIRST SEMANTIC DIFFERENCE          none — there is no difference to trace
SOURCE CAUSE                       n/a
#5473                              NOT OUR CAUSE
```

## One thing that DID differ, and did not propagate

`admins.sqlite` is **not** byte-identical between runs (same 8 368 128 bytes, different content) —
SQLite page layout, not content. The tiles built from it are identical, so it does not reach the
graph. Worth knowing because `admins.sqlite` is an *input* to tile building: had the tiles
differed, this would have been the first suspect.

## Why it is deterministic, from the source

`node_bundle::node_edges` in `valhalla/mjolnir/node_expander.h` is still
`std::map<Edge, size_t>` in 3.6.3 — exactly what issue #5473 describes, and there is no
`deterministic_edge_indexes` option anywhere. So determinism here is not because the reported
code was changed.

It holds because `Edge::operator<` (`valhalla/mjolnir/node_expander.h:180`) falls through to

```cpp
return llindex_ < other.llindex_;
```

`llindex_` is the edge's own index into the GraphBuilder lat/lng sequence, so distinct edges get
distinct keys and `std::map` — an ordered container — iterates in one fixed order regardless of
insertion order or thread timing.

**With one exception, and it is the interesting one.** The same operator opens with:

```cpp
if (targetnode_ == other.targetnode_ && sourcenode_ == other.sourcenode_ &&
    sourcenode_ == targetnode_) {
  return false;
}
```

For two distinct **self-loop** edges at the same node this returns `false` in both directions, so
neither is less than the other. Under `std::map` they are the *same key* and only one survives —
and which one depends on insertion order. That is a real tie in the comparator, and it is a
plausible explanation for how the #5473 author sees non-determinism on their data while Moldova
shows none. Unverified: we have not established whether Moldova contains such edges.

## What this does and does not establish

**Does:** stock 3.6.3 is deterministic for identical input on this data, independent of thread
count. Our production builds are therefore reproducible off the machine that made them.

**Does NOT:** it says nothing about *different* inputs. Our 31-shared-paths / 0-byte-identical
failure came from two masters with different country sets, so their inputs genuinely differed and
this experiment cannot explain it. What it does is **remove non-determinism from the list of
candidates** — which leaves input context, and makes the dependency-closure measurement the next
thing to do rather than one of several things.

> **A CONCLUSION DRAWN FROM THIS AND THEN RETRACTED, kept because the error is instructive.**
> This result was briefly used to argue that the 74.6 % of tiles changing over 16 days must be
> real OSM change rather than index churn. **It proves no such thing.** Determinism is *same
> input, same output*; the 16-day figure compared **different** inputs. Between the two sits a
> third possibility — a small real edit that shifts the ids of many unchanged objects — which is
> precisely the *instability under changed input* this branch was opened to study, and which
> nothing here excludes. Proving determinism and then reasoning about changed input is the same
> conflation the branch exists to avoid, made within an hour of drawing the distinction.

**Still open, and explicitly a hypothesis rather than a finding:** whether a deterministic builder
means a rebuild's effects stop at the first ring of neighbours. That is the next experiment, not
a conclusion from this one.
