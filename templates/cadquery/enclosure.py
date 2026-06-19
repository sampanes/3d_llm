"""
Parametric Electronics Enclosure — CadQuery Template
=====================================================
A project enclosure designed for housing PCBs / electronics with:
- PCB mounting standoffs (configurable positions)
- Ventilation slots on side panels
- Cable gland / cable entry opening
- Screw-together top and bottom halves

Usage:
    pip install cadquery
    python enclosure.py

    # Or use in CQ-editor for interactive preview
"""

import cadquery as cq
from pathlib import Path

# ─── Parameters ───────────────────────────────────────────────────────────────

# Enclosure outer dimensions
ENCL_WIDTH = 100.0    # X dimension (mm)
ENCL_DEPTH = 70.0     # Y dimension (mm)
ENCL_HEIGHT = 35.0    # Z total height (mm) — split between top and bottom

# Structural
WALL = 2.5                # Wall thickness (mm)
EDGE_FILLET = 3.0         # Fillet radius on outer edges (mm)
SPLIT_RATIO = 0.65        # Bottom gets this fraction of total height

# PCB mounting
PCB_WIDTH = 80.0          # PCB X dimension (mm)
PCB_DEPTH = 50.0          # PCB Y dimension (mm)
STANDOFF_HEIGHT = 5.0     # Height of PCB standoffs (mm)
STANDOFF_OUTER_R = 3.0    # Standoff outer radius (mm)
STANDOFF_HOLE_R = 1.3     # Screw hole radius (M2.5) (mm)
STANDOFF_HOLE_INSET = 3.5 # Distance from PCB edge to mounting hole center (mm)

# Ventilation
VENT_SLOT_WIDTH = 1.5     # Width of each vent slot (mm)
VENT_SLOT_LENGTH = 20.0   # Length of each vent slot (mm)
VENT_SLOT_SPACING = 3.5   # Center-to-center spacing between slots (mm)
VENT_COUNT = 6            # Number of vent slots per side

# Cable gland opening
CABLE_HOLE_DIAMETER = 12.0   # Cable entry hole diameter (mm)
CABLE_HOLE_FACE = "front"    # Which face: "front", "back", "left", "right"
CABLE_HOLE_Z_OFFSET = 0.0   # Z offset from split line (negative = into bottom half)

# Assembly screws (corner posts)
SCREW_BOSS_R = 4.0        # Outer radius of corner screw bosses (mm)
SCREW_HOLE_R = 1.5        # Screw hole radius (M3 = 1.5) (mm)
SCREW_BOSS_INSET = 2.0    # Inset from inner corner (mm)

# Output
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "stl"

# ─── Derived Values ──────────────────────────────────────────────────────────

bottom_height = ENCL_HEIGHT * SPLIT_RATIO
top_height = ENCL_HEIGHT - bottom_height

inner_width = ENCL_WIDTH - 2 * WALL
inner_depth = ENCL_DEPTH - 2 * WALL

# PCB standoff positions (4 corners of the PCB, centered in enclosure)
pcb_x_offset = 0  # PCB centered in enclosure
pcb_y_offset = 0
standoff_positions = [
    (pcb_x_offset - PCB_WIDTH / 2 + STANDOFF_HOLE_INSET,
     pcb_y_offset - PCB_DEPTH / 2 + STANDOFF_HOLE_INSET),
    (pcb_x_offset + PCB_WIDTH / 2 - STANDOFF_HOLE_INSET,
     pcb_y_offset - PCB_DEPTH / 2 + STANDOFF_HOLE_INSET),
    (pcb_x_offset + PCB_WIDTH / 2 - STANDOFF_HOLE_INSET,
     pcb_y_offset + PCB_DEPTH / 2 - STANDOFF_HOLE_INSET),
    (pcb_x_offset - PCB_WIDTH / 2 + STANDOFF_HOLE_INSET,
     pcb_y_offset + PCB_DEPTH / 2 - STANDOFF_HOLE_INSET),
]

# Corner boss positions (at inner corners of the enclosure)
boss_positions = [
    ( inner_width / 2 - SCREW_BOSS_INSET - SCREW_BOSS_R,
      inner_depth / 2 - SCREW_BOSS_INSET - SCREW_BOSS_R),
    (-inner_width / 2 + SCREW_BOSS_INSET + SCREW_BOSS_R,
      inner_depth / 2 - SCREW_BOSS_INSET - SCREW_BOSS_R),
    (-inner_width / 2 + SCREW_BOSS_INSET + SCREW_BOSS_R,
     -inner_depth / 2 + SCREW_BOSS_INSET + SCREW_BOSS_R),
    ( inner_width / 2 - SCREW_BOSS_INSET - SCREW_BOSS_R,
     -inner_depth / 2 + SCREW_BOSS_INSET + SCREW_BOSS_R),
]


# ─── Bottom Half ──────────────────────────────────────────────────────────────

def make_bottom() -> cq.Workplane:
    """Create the bottom half of the enclosure with standoffs and screw bosses."""

    # Main shell: solid box, shelled from top
    bottom = (
        cq.Workplane("XY")
        .box(ENCL_WIDTH, ENCL_DEPTH, bottom_height, centered=(True, True, False))
        .edges("|Z").fillet(EDGE_FILLET)
        .faces(">Z").shell(-WALL)
    )

    # PCB mounting standoffs
    for x, y in standoff_positions:
        standoff = (
            cq.Workplane("XY")
            .workplane(offset=WALL)
            .center(x, y)
            .circle(STANDOFF_OUTER_R)
            .extrude(STANDOFF_HEIGHT)
        )
        # Drill screw hole into standoff
        standoff = (
            standoff.faces(">Z").workplane()
            .circle(STANDOFF_HOLE_R)
            .cutBlind(-STANDOFF_HEIGHT)
        )
        bottom = bottom.union(standoff)

    # Corner screw bosses (run full height of bottom interior)
    boss_h = bottom_height - WALL
    for x, y in boss_positions:
        boss = (
            cq.Workplane("XY")
            .workplane(offset=WALL)
            .center(x, y)
            .circle(SCREW_BOSS_R)
            .extrude(boss_h)
        )
        boss = (
            boss.faces(">Z").workplane()
            .circle(SCREW_HOLE_R)
            .cutBlind(-boss_h * 0.8)
        )
        bottom = bottom.union(boss)

    # Cable gland hole
    bottom = _cut_cable_hole(bottom, bottom_height)

    return bottom


# ─── Top Half ─────────────────────────────────────────────────────────────────

def make_top() -> cq.Workplane:
    """Create the top half (lid) with ventilation slots and screw holes."""

    # Main shell: solid box, shelled from bottom (which becomes the open face)
    top = (
        cq.Workplane("XY")
        .box(ENCL_WIDTH, ENCL_DEPTH, top_height, centered=(True, True, False))
        .edges("|Z").fillet(EDGE_FILLET)
        .faces("<Z").shell(-WALL)
    )

    # Ventilation slots on the +Y face (right side when looking from front)
    top = _cut_vent_slots(top, face_axis=">Y", height=top_height)

    # Also add vents on the -Y face
    top = _cut_vent_slots(top, face_axis="<Y", height=top_height)

    # Through-holes for corner screws
    for x, y in boss_positions:
        top = (
            top.faces(">Z").workplane()
            .center(x, y)
            .circle(SCREW_HOLE_R)
            .cutThruAll()
        )
        # Countersink
        top = (
            top.faces(">Z").workplane()
            .center(x, y)
            .cskHole(
                SCREW_HOLE_R * 2,
                SCREW_HOLE_R * 2 + 2.5,
                82
            )
        )

    return top


# ─── Ventilation Slots ───────────────────────────────────────────────────────

def _cut_vent_slots(part: cq.Workplane, face_axis: str, height: float) -> cq.Workplane:
    """Cut a series of rectangular ventilation slots into a face."""

    total_span = (VENT_COUNT - 1) * VENT_SLOT_SPACING
    start_offset = -total_span / 2
    slot_z = height / 2  # Center the slots vertically

    for i in range(VENT_COUNT):
        x_offset = start_offset + i * VENT_SLOT_SPACING

        slot = (
            cq.Workplane("XY")
            .workplane(offset=slot_z - VENT_SLOT_LENGTH / 2)
            .center(x_offset, ENCL_DEPTH / 2 if ">" in face_axis else -ENCL_DEPTH / 2)
            .box(VENT_SLOT_WIDTH, WALL + 2, VENT_SLOT_LENGTH,
                 centered=(True, True, False))
        )
        part = part.cut(slot)

    return part


# ─── Cable Gland Hole ────────────────────────────────────────────────────────

def _cut_cable_hole(part: cq.Workplane, part_height: float) -> cq.Workplane:
    """Cut a cable entry hole on the specified face."""

    hole_z = part_height * 0.5 + CABLE_HOLE_Z_OFFSET
    r = CABLE_HOLE_DIAMETER / 2

    face_map = {
        "front": (0, -ENCL_DEPTH / 2, hole_z, 90, 0),
        "back":  (0,  ENCL_DEPTH / 2, hole_z, 90, 0),
        "left":  (-ENCL_WIDTH / 2, 0, hole_z, 0, 90),
        "right": ( ENCL_WIDTH / 2, 0, hole_z, 0, 90),
    }

    x, y, z, rx, ry = face_map.get(CABLE_HOLE_FACE, face_map["front"])

    hole = (
        cq.Workplane("XY")
        .workplane(offset=z)
        .center(x, y)
        .circle(r)
        .extrude(WALL + 4)  # Extend through the wall
    )

    # Rotate the hole to be perpendicular to the chosen face
    if CABLE_HOLE_FACE in ("front", "back"):
        # Hole along Y axis — already correct if extruded along Y
        hole = (
            cq.Workplane("XZ")
            .workplane(offset=y)
            .center(x, z)
            .circle(r)
            .extrude(WALL + 4 if "back" in CABLE_HOLE_FACE else -(WALL + 4))
        )
    else:
        hole = (
            cq.Workplane("YZ")
            .workplane(offset=x)
            .center(y, z)
            .circle(r)
            .extrude(WALL + 4 if "right" in CABLE_HOLE_FACE else -(WALL + 4))
        )

    part = part.cut(hole)
    return part


# ─── Export ───────────────────────────────────────────────────────────────────

def export_parts():
    """Build and export both halves of the enclosure."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building bottom half...")
    bottom = make_bottom()
    bottom_path = OUTPUT_DIR / "enclosure_bottom.stl"
    cq.exporters.export(bottom, str(bottom_path))
    print(f"  Exported: {bottom_path}")

    print("Building top half...")
    top = make_top()
    top_path = OUTPUT_DIR / "enclosure_top.stl"
    cq.exporters.export(top, str(top_path))
    print(f"  Exported: {top_path}")

    print("Done! Both halves exported.")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    export_parts()

# For CQ-editor — uncomment to preview the assembly:
# bottom_result = make_bottom()
# top_result = make_top().translate((0, 0, bottom_height + 5))
# show_object(bottom_result, name="Bottom", options={"color": "darkslategray"})
# show_object(top_result, name="Top", options={"color": "slategray", "alpha": 0.7})
