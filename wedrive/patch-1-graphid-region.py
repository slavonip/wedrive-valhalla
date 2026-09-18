"""WeDrive patch 1: a GraphReader that holds several independently built tile dirs.

THE IDEA, and why it needs no format change.

`GraphId` is a plain uint64 with only 46 bits used — level:3 | tileid:22 | id:21. Bits 46..63 are
free, and they are free IN MEMORY ONLY: `DirectedEdge.endnode_` and `NodeTransition` store 46
bits, so nothing written to a tile can carry a region. That is exactly why a portal has to be an
external table rather than a cross-border endnode, and it is also why tagging the high bits costs
nothing on disk.

So a region id rides in bits 46..63 while a GraphId is in memory, and is stripped whenever the id
touches a tile's bytes or a filename.

WHAT HAD TO CHANGE, and nothing else did:

  GraphId::tile_base()   masked to the low 25 bits and would have DROPPED the region, so every
                         region's copy of a tile would have collided in the cache.
  GraphId::is_valid()    compared the whole value against kInvalidGraphId, so a tagged invalid id
                         read as valid.
  GraphTile::id()        returned the header's graphid, which knows no region; the reader compares
                         `tile->id() != graphid.tile_base()` to decide a cache hit, so a tile must
                         remember which region it was loaded for.
  GraphReader            gains a region -> tile_dir map and picks the directory by the region bits.

`level()`, `tileid()` and `tile_value()` already mask, so they were left alone — checked, not
assumed.
"""
import io
import os
import re
import sys

SRC = os.path.expanduser("~/vhbuild/src")
edits = 0


def patch(path, old, new, why):
    global edits
    p = os.path.join(SRC, path)
    s = io.open(p, encoding="utf-8").read()
    if new.strip() and new.strip().splitlines()[0] in s and old not in s:
        print(f"   already applied: {path} — {why}")
        return
    assert s.count(old) == 1, f"{path}: {why}\n  expected exactly one match for:\n{old[:200]}"
    io.open(p, "w", encoding="utf-8").write(s.replace(old, new))
    edits += 1
    print(f"   {path}: {why}")


# ── 1. GraphId: the region lives in the spare high bits ─────────────────────────────────────
patch("valhalla/baldr/graphid.h",
      "constexpr uint64_t kIdIncrement = 1 << 25;",
      """constexpr uint64_t kIdIncrement = 1 << 25;

// WEDRIVE: a region id in the spare high bits, IN MEMORY ONLY.
//
// Mjolnir writes 46 bits — level:3 | tileid:22 | id:21 — and every reference stored inside a tile
// (DirectedEdge::endnode_, NodeTransition) is exactly those 46 bits. Bits 46..63 therefore never
// reach a file, which is what makes them free to carry which independently built region a GraphId
// belongs to while it is being used.
//
// It also means a cross-region link CANNOT be expressed as an endnode: there is nowhere to put
// the other region. Portals are an external table for that reason, not by preference.
constexpr uint64_t kGraphIdBits = 0x3fffffffffffULL; // the 46 bits Mjolnir writes
constexpr uint64_t kRegionBits = ~kGraphIdBits;      // bits 46..63, ours
constexpr uint32_t kRegionShift = 46;
constexpr uint32_t kMaxRegionId = 0x3ffff;           // 18 bits""",
      "region constants")

patch("valhalla/baldr/graphid.h",
      """  bool is_valid() const {
    // TODO: make this strict it should check the tile hierarchy not bit field widths
    return value != kInvalidGraphId;
  }""",
      """  bool is_valid() const {
    // TODO: make this strict it should check the tile hierarchy not bit field widths
    // WEDRIVE: compare WITHOUT the region, or a tagged invalid id reads as valid.
    return (value & kGraphIdBits) != kInvalidGraphId;
  }

  /** WEDRIVE: which independently built region this id belongs to (0 = the only one). */
  inline uint32_t region() const {
    return static_cast<uint32_t>(value >> kRegionShift);
  }

  /** WEDRIVE: the same id, tagged for a region. */
  inline GraphId with_region(const uint32_t region) const {
    return GraphId((value & kGraphIdBits) | (static_cast<uint64_t>(region) << kRegionShift));
  }

  /** WEDRIVE: the id as Mjolnir wrote it — what may be compared with tile contents. */
  inline GraphId without_region() const {
    return GraphId(value & kGraphIdBits);
  }""",
      "is_valid ignores the region; region accessors")

patch("valhalla/baldr/graphid.h",
      """  GraphId tile_base() const {
    return GraphId((value & 0x1ffffff));
  }""",
      """  GraphId tile_base() const {
    // WEDRIVE: keep the region. Dropping it would make every region's copy of the same
    // geographic tile share one cache key, and the second load would serve the first's bytes.
    return GraphId((value & 0x1ffffff) | (value & kRegionBits));
  }""",
      "tile_base preserves the region")

print(f"\n{edits} edits applied")
if edits == 0:
    print("nothing changed — the patch was already in place")
