"""WeDrive patch 6: region propagation through Thor, at the chokepoint rather than at 100 sites.

THE FINDING THAT SHAPES THIS PATCH: EdgeLabel bit-packs its two GraphIds to 46 bits each --
`edgeid_ : 46` and `endnode_ : 46` -- and both 64-bit words are exactly full. There is nowhere to
put a region tag inside an id. EdgeLabel is 40 bytes and BDEdgeLabel is exactly 64, one cache line,
so widening them is not free either.

What makes it tractable anyway is that `endnode()` and `edgeid()` are ACCESSORS. Every one of the
100 endnode() reads in Thor goes through one of them. So the region is stored ONCE per label, in
the 3 bits the struct already declares as `spare`, and re-applied on the way out. The 100 call
sites need no edit and cannot be missed.

The rule this encodes:

    normal edge : successor region = predecessor region   (inherited; the stored 46-bit endnode
                                                           has no region of its own)
    portal      : successor region = portal target region (the ONLY thing allowed to switch)

3 bits means regions 1..7, with 0 meaning "untagged / single region". That cap is enforced
loudly in AddRegion rather than silently truncated, because a silent truncation here would route
a car into the wrong country's graph.
"""
import io
import os

SRC = "/src/valhalla"


def patch(relpath, edits):
    p = os.path.join(SRC, relpath)
    s = io.open(p, encoding="utf-8").read()
    changed = False
    for name, old, new in edits:
        if name in s:
            print("      ok   already applied: %s" % name)
            continue
        n = s.count(old)
        assert n == 1, "%s: wanted 1 match for %s, found %d" % (relpath, name, n)
        s = s.replace(old, new)
        changed = True
        print("      +    %s" % name)
    if changed:
        io.open(p, "w", encoding="utf-8").write(s)


print("   valhalla/sif/edgelabel.h")
patch(
    "valhalla/sif/edgelabel.h",
    [
        # 1. The storage. `spare : 3` becomes the region, so the struct does not grow by a byte.
        (
            "WEDRIVE region storage",
            "  uint32_t spare : 3;",
            "  // WEDRIVE region storage: the region this label's edge AND end node belong to.\n"
            "  // Both ids are stored region-less (46 bits each, no room), so this is the only\n"
            "  // copy and the accessors below put it back. 3 bits: regions 1..7, 0 = untagged.\n"
            "  uint32_t region_ : 3;",
        ),
        # 2. Default ctor initialises it.
        (
            "WEDRIVE region default",
            "        destonly_access_restr_mask_(0), cost_(0, 0), sortcost_(0) {\n"
            "    assert(path_id_ <= baldr::kMaxMultiPathId);",
            "        destonly_access_restr_mask_(0), region_(0), // WEDRIVE region default\n"
            "        cost_(0, 0), sortcost_(0) {\n"
            "    assert(path_id_ <= baldr::kMaxMultiPathId);",
        ),
        # 3. Value ctor takes the region from the edge id, which EdgeMetadata now carries.
        (
            "WEDRIVE region from edgeid",
            "        tunnel_(edge->tunnel()), destonly_access_restr_mask_(destonly_access_restr_mask), cost_(cost),\n"
            "        sortcost_(sortcost) {\n"
            "    dest_only_ = destonly ? destonly : edge->destonly();",
            "        tunnel_(edge->tunnel()), destonly_access_restr_mask_(destonly_access_restr_mask),\n"
            "        // WEDRIVE region from edgeid: an edge and its end node are in the same region.\n"
            "        // Only a portal may differ, and a portal builds its label deliberately.\n"
            "        region_(static_cast<uint32_t>(edgeid.region())), cost_(cost), sortcost_(sortcost) {\n"
            "    dest_only_ = destonly ? destonly : edge->destonly();\n"
            "    // Fail fast rather than truncate: 3 bits cannot hold region 8, and a truncated\n"
            "    // region silently routes into another country's graph.\n"
            "    assert(edgeid.region() < 8 && \"WEDRIVE: region id exceeds EdgeLabel's 3 bits\");",
        ),
        # 4. THE CHOKEPOINT. Both accessors re-apply the region on the way out.
        (
            "WEDRIVE tagged edgeid",
            "  baldr::GraphId edgeid() const {\n    return baldr::GraphId(edgeid_);\n  }",
            "  baldr::GraphId edgeid() const {\n"
            "    // WEDRIVE tagged edgeid: stored region-less, handed back tagged, so every caller\n"
            "    // in Thor gets a resolvable id without any of them being edited.\n"
            "    return baldr::GraphId(edgeid_).with_region(region_);\n  }",
        ),
        (
            "WEDRIVE tagged endnode",
            "  baldr::GraphId endnode() const {\n    return baldr::GraphId(endnode_);\n  }",
            "  baldr::GraphId endnode() const {\n"
            "    // WEDRIVE tagged endnode: this single line is what covers all 100 endnode() reads\n"
            "    // across the 13 Thor files. The stored 46-bit value never had a region.\n"
            "    return baldr::GraphId(endnode_).with_region(region_);\n  }",
        ),
        # 5. An explicit reader, for the portal code and the debug gate.
        (
            "WEDRIVE region accessor",
            "  const Cost& cost() const {\n    return cost_;\n  }",
            "  /**\n"
            "   * WEDRIVE region accessor: which graph namespace this label lives in.\n"
            "   */\n"
            "  uint32_t region() const {\n    return region_;\n  }\n\n"
            "  const Cost& cost() const {\n    return cost_;\n  }",
        ),
    ],
)

print("   valhalla/thor/pathalgorithm.h")
patch(
    "valhalla/thor/pathalgorithm.h",
    [
        # EdgeMetadata rebuilds an id from tileid+level+index and drops the region doing it.
        # This is the one place an edge id is MANUFACTURED rather than copied.
        (
            "WEDRIVE keep region in edge_id",
            "    baldr::GraphId edge_id = {node.tileid(), node.level(), nodeinfo->edge_index()};",
            "    // WEDRIVE keep region in edge_id: this constructor takes tileid/level/index and\n"
            "    // knows nothing of the region, so it must be re-applied from the node we came from.\n"
            "    baldr::GraphId edge_id =\n"
            "        baldr::GraphId(node.tileid(), node.level(), nodeinfo->edge_index())\n"
            "            .with_region(node.region());",
        ),
    ],
)

print("\n   verification, each hunk by a marker that cannot collide with another:")
for relpath, markers in (
    (
        "valhalla/sif/edgelabel.h",
        [
            "WEDRIVE region storage",
            "WEDRIVE region default",
            "WEDRIVE region from edgeid",
            "WEDRIVE tagged edgeid",
            "WEDRIVE tagged endnode",
            "WEDRIVE region accessor",
        ],
    ),
    ("valhalla/thor/pathalgorithm.h", ["WEDRIVE keep region in edge_id"]),
):
    s = io.open(os.path.join(SRC, relpath), encoding="utf-8").read()
    for m in markers:
        print("      %s %s" % ("ok     " if m in s else "MISSING", m))

# The struct must not have grown: BDEdgeLabel is exactly one cache line and the regression gate
# depends on single-region routing being untouched.
s = io.open(os.path.join(SRC, "valhalla/sif/edgelabel.h"), encoding="utf-8").read()
print("      %s no leftover `spare` bitfield in EdgeLabel"
      % ("ok     " if "uint32_t spare : 3;" not in s else "MISSING"))
