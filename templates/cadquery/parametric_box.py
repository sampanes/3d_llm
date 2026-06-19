"""
Parametric Box with Lid — CadQuery Template
============================================
A fully parametric box with:
- Filleted edges for aesthetics and strength
- Screw bosses in each corner for fastening the lid
- An interlocking lip on the lid for alignment
- STL export

Usage:
    pip install cadquery
    python parametric_box.py

    # Or use in CQ-editor for interactive preview
"""

import cadquery as cq
from pathlib import Path

# ─── Parameters ───────────────────────────────────────────────────────────────

# Outer dimensions
BOX_WIDTH = 80.0    # X dimension (mm)
BOX_DEPTH = 60.0    # Y dimension (mm)
BOX_HEIGHT = 40.0   # Z dimension (mm)

# Structural
WALL_THICKNESS = 2.5       # Shell wall thickness (mm)
BOTTOM_THICKNESS = 2.5     # Floor thickness (mm)
EDGE_FILLET = 3.0          # Fillet radius on outer edges (mm)

# Lid
LID_THICKNESS = 3.0        # Top plate thickness (mm)
LID_LIP_HEIGHT = 4.0       # Interlocking lip depth into box (mm)
LID_LIP_WALL = 1.5         # Lip wall thickness (mm)
LID_TOLERANCE = 0.3        # Clearance between lid lip and box walls (mm)

# Screw bosses
BOSS_OUTER_RADIUS = 4.0    # Outer radius of corner screw bosses (mm)
BOSS_INNER_RADIUS = 1.5    # Screw hole radius (M3 = 1.5mm) (mm)
BOSS_HEIGHT_RATIO = 0.75   # Boss height as fraction of inner box height

# Output
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "stl"

# ─── Derived Values ──────────────────────────────────────────────────────────

inner_width = BOX_WIDTH - 2 * WALL_THICKNESS
inner_depth = BOX_DEPTH - 2 * WALL_THICKNESS
inner_height = BOX_HEIGHT - BOTTOM_THICKNESS
boss_height = inner_height * BOSS_HEIGHT_RATIO

# Boss positions — inset from inner corners
boss_inset = BOSS_OUTER_RADIUS + 1.0  # Small gap from walls
boss_positions = [
    ( inner_width / 2 - boss_inset,  inner_depth / 2 - boss_inset),
    (-inner_width / 2 + boss_inset,  inner_depth / 2 - boss_inset),
    (-inner_width / 2 + boss_inset, -inner_depth / 2 + boss_inset),
    ( inner_width / 2 - boss_inset, -inner_depth / 2 + boss_inset),
]


# ─── Box Body ─────────────────────────────────────────────────────────────────

def make_box() -> cq.Workplane:
    """Create the main box body: a shelled rectangular solid with screw bosses."""

    # Start with a solid block, centered on XY, sitting on Z=0
    box = (
        cq.Workplane("XY")
        .box(BOX_WIDTH, BOX_DEPTH, BOX_HEIGHT, centered=(True, True, False))
    )

    # Fillet all vertical edges
    box = box.edges("|Z").fillet(EDGE_FILLET)

    # Fillet the top horizontal edges (soften the rim)
    box = box.edges(">Z").fillet(min(EDGE_FILLET, WALL_THICKNESS * 0.4))

    # Shell: remove the top face and hollow out the interior
    box = box.faces(">Z").shell(-WALL_THICKNESS)

    # Add screw bosses in each corner
    for x, y in boss_positions:
        boss = (
            cq.Workplane("XY")
            .workplane(offset=BOTTOM_THICKNESS)
            .center(x, y)
            .circle(BOSS_OUTER_RADIUS)
            .extrude(boss_height)
        )
        # Drill the screw hole
        boss = (
            boss.faces(">Z")
            .workplane()
            .circle(BOSS_INNER_RADIUS)
            .cutBlind(-boss_height)
        )
        box = box.union(boss)

    return box


# ─── Lid ──────────────────────────────────────────────────────────────────────

def make_lid() -> cq.Workplane:
    """Create a lid with an interlocking lip and screw holes that align
    with the box's corner bosses."""

    lip_width = inner_width - 2 * LID_TOLERANCE
    lip_depth = inner_depth - 2 * LID_TOLERANCE
    lip_inner_width = lip_width - 2 * LID_LIP_WALL
    lip_inner_depth = lip_depth - 2 * LID_LIP_WALL

    # Top plate
    lid = (
        cq.Workplane("XY")
        .box(BOX_WIDTH, BOX_DEPTH, LID_THICKNESS, centered=(True, True, False))
    )

    # Fillet edges to match the box
    lid = lid.edges("|Z").fillet(EDGE_FILLET)
    lid = lid.edges("<Z").fillet(min(EDGE_FILLET * 0.5, LID_THICKNESS * 0.3))

    # Interlocking lip (drops down from the underside of the lid)
    lip_outer = (
        cq.Workplane("XY")
        .workplane(offset=-LID_LIP_HEIGHT)
        .box(lip_width, lip_depth, LID_LIP_HEIGHT, centered=(True, True, False))
    )
    lip_inner = (
        cq.Workplane("XY")
        .workplane(offset=-LID_LIP_HEIGHT - 0.01)
        .box(lip_inner_width, lip_inner_depth, LID_LIP_HEIGHT + 0.02,
             centered=(True, True, False))
    )
    lip = lip_outer.cut(lip_inner)
    lid = lid.union(lip)

    # Drill screw holes through the lid aligned with box bosses
    for x, y in boss_positions:
        lid = (
            lid.faces(">Z")
            .workplane()
            .center(x, y)
            .circle(BOSS_INNER_RADIUS)
            .cutThruAll()
        )

        # Add countersink on top face
        lid = (
            lid.faces(">Z")
            .workplane()
            .center(x, y)
            .cskHole(
                BOSS_INNER_RADIUS * 2,
                BOSS_INNER_RADIUS * 2 + 2,
                82  # countersink angle
            )
        )

    return lid


# ─── Export ───────────────────────────────────────────────────────────────────

def export_parts():
    """Build and export both parts to STL."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building box body...")
    box = make_box()
    box_path = OUTPUT_DIR / "parametric_box_body.stl"
    cq.exporters.export(box, str(box_path))
    print(f"  Exported: {box_path}")

    print("Building lid...")
    lid = make_lid()
    lid_path = OUTPUT_DIR / "parametric_box_lid.stl"
    cq.exporters.export(lid, str(lid_path))
    print(f"  Exported: {lid_path}")

    print("Done! Both parts exported.")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    export_parts()

# For CQ-editor: show the assembly with lid offset above the box
# Uncomment the lines below when using CQ-editor:
# box_result = make_box()
# lid_result = make_lid().translate((0, 0, BOX_HEIGHT + 10))
# show_object(box_result, name="Box Body", options={"color": "steelblue"})
# show_object(lid_result, name="Lid", options={"color": "cornflowerblue"})
