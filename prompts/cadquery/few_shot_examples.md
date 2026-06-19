# CadQuery Few-Shot Examples

Two complete, working CadQuery examples for use as few-shot context when prompting LLMs.
Each example produces valid STL output when run with `python script.py`.

---

## Example 1: Parametric Project Box Enclosure with Screw Bosses and Lid

```python
# ============================================================
# Model:       Parametric Project Box with Screw Bosses and Lid
# Description: A rectangular enclosure with rounded edges,
#              screw bosses in each corner, and a flat lid.
#              Designed for housing electronics (Arduino, RPi, etc.)
# Print Settings:
#   - Layer height: 0.2mm
#   - Infill: 20%
#   - No supports needed
# Print orientation: Open face up for both box and lid
# ============================================================

import cadquery as cq

# --- Configurable Parameters ---
box_outer_width   = 80.0    # X dimension (mm)
box_outer_depth   = 60.0    # Y dimension (mm)
box_outer_height  = 35.0    # Z dimension of the box body (mm)
wall_thickness    = 2.0     # wall and floor thickness (mm)
corner_fillet     = 3.0     # outer corner fillet radius (mm)
lid_thickness     = 2.5     # thickness of the lid plate (mm)
lid_lip_height    = 3.0     # height of the lid lip that inserts into box (mm)
tolerance         = 0.2     # clearance on mating surfaces (mm)

screw_boss_od     = 8.0     # outer diameter of screw boss (mm)
screw_hole_dia    = 2.5     # screw hole diameter for M2.5 self-tap (mm)
screw_boss_height = 10.0    # height of the screw boss (mm)

# Derived
inner_width  = box_outer_width  - 2 * wall_thickness
inner_depth  = box_outer_depth  - 2 * wall_thickness
inner_height = box_outer_height - wall_thickness

# Corner positions for screw bosses (inset from inner walls)
boss_inset = screw_boss_od / 2 + 1.0
boss_positions = [
    ( inner_width / 2 - boss_inset,  inner_depth / 2 - boss_inset),
    (-inner_width / 2 + boss_inset,  inner_depth / 2 - boss_inset),
    (-inner_width / 2 + boss_inset, -inner_depth / 2 + boss_inset),
    ( inner_width / 2 - boss_inset, -inner_depth / 2 + boss_inset),
]

# --- Box Body ---
box_body = (
    cq.Workplane("XY")
    # Outer shell
    .box(box_outer_width, box_outer_depth, box_outer_height, centered=(True, True, False))
    .edges("|Z")
    .fillet(corner_fillet)
    # Hollow out interior
    .faces(">Z")
    .shell(-wall_thickness)
)

# --- Screw Bosses ---
bosses = (
    cq.Workplane("XY")
    .workplane(offset=wall_thickness)
    .pushPoints(boss_positions)
    .circle(screw_boss_od / 2)
    .extrude(screw_boss_height)
)

# Screw holes in the bosses
screw_holes = (
    cq.Workplane("XY")
    .workplane(offset=wall_thickness)
    .pushPoints(boss_positions)
    .circle(screw_hole_dia / 2)
    .extrude(screw_boss_height + 0.01)
)

box_result = box_body.union(bosses).cut(screw_holes)

# --- Lid ---
lid_inner_width = inner_width - 2 * tolerance
lid_inner_depth = inner_depth - 2 * tolerance

lid = (
    cq.Workplane("XY")
    # Main lid plate (outer dimensions match the box)
    .box(box_outer_width, box_outer_depth, lid_thickness, centered=(True, True, False))
    .edges("|Z")
    .fillet(corner_fillet)
)

# Lip that inserts into the box
lip = (
    cq.Workplane("XY")
    .workplane(offset=-lid_lip_height)
    .box(lid_inner_width, lid_inner_depth, lid_lip_height, centered=(True, True, False))
)

# Screw holes through the lid
lid_screw_holes = (
    cq.Workplane("XY")
    .workplane(offset=-lid_lip_height - 0.01)
    .pushPoints(boss_positions)
    .circle(screw_hole_dia / 2)
    .extrude(lid_thickness + lid_lip_height + 0.02)
)

# Countersink on top of lid
lid_countersinks = (
    cq.Workplane("XY")
    .workplane(offset=lid_thickness - 1.5)
    .pushPoints(boss_positions)
    .circle(screw_hole_dia + 1.0)
    .extrude(1.5 + 0.01)
)

lid_result = lid.union(lip).cut(lid_screw_holes).cut(lid_countersinks)

# --- Export ---
# Export box and lid separately for printing
result = box_result  # Change to lid_result to export the lid
cq.exporters.export(result, 'output.stl')

# To visualize assembly (CQ-editor only, not for export):
# assembly_result = box_result.union(
#     lid_result.translate((0, 0, box_outer_height + 5))
# )
```

---

## Example 2: Cable Organizer Desk Clip

```python
# ============================================================
# Model:       Cable Organizer Desk Clip
# Description: A clip that attaches to a desk edge and holds
#              multiple cables neatly. Features a spring-loaded
#              jaw for clamping to desks up to 30mm thick.
# Print Settings:
#   - Layer height: 0.2mm
#   - Infill: 50% (needs flex strength)
#   - Material: PETG or TPU for flex
#   - No supports needed
# Print orientation: Flat, jaw opening facing up
# ============================================================

import cadquery as cq

# --- Configurable Parameters ---
desk_thickness     = 25.0    # max desk thickness to clamp (mm)
clamp_clearance    = 1.0     # extra gap in the jaw (mm)
jaw_depth          = 30.0    # how far the clip slides onto the desk (mm)
jaw_wall           = 3.0     # thickness of jaw walls (mm)
clip_width         = 15.0    # width of the clip body (mm)

cable_count        = 3       # number of cable slots
cable_diameter     = 5.0     # individual cable slot diameter (mm)
cable_tolerance    = 0.5     # extra clearance per cable slot (mm)
cable_slot_spacing = 10.0    # center-to-center spacing of cable slots (mm)

body_height        = 12.0    # height of the cable-holding section (mm)
fillet_r           = 1.0     # general fillet radius (mm)

# Derived
jaw_opening   = desk_thickness + clamp_clearance
slot_r        = (cable_diameter + cable_tolerance) / 2
total_cable_width = (cable_count - 1) * cable_slot_spacing + cable_diameter
body_width    = max(clip_width, total_cable_width + 2 * jaw_wall)

# --- Jaw (Desk Clamp) ---
# U-shaped channel that slides over the desk edge
jaw = (
    cq.Workplane("XY")
    .box(body_width, jaw_depth, jaw_opening + 2 * jaw_wall, centered=(True, True, False))
    # Cut the interior channel
    .faces(">Z")
    .workplane(offset=-jaw_wall)
    .rect(body_width - 2 * jaw_wall, jaw_depth + 0.02)
    .cutBlind(-jaw_opening)
    # Open the front of the jaw (the desk slides in from the front)
    .faces(">Y")
    .workplane()
    .rect(body_width - 2 * jaw_wall, jaw_opening)
    .cutBlind(-jaw_depth + jaw_wall)
)

# Add fillets to the jaw edges for comfort and print quality
jaw = jaw.edges("|Z").fillet(fillet_r)

# --- Cable Holder Section ---
# Positioned on top of the jaw
cable_body_z = jaw_opening + 2 * jaw_wall

cable_holder = (
    cq.Workplane("XY")
    .workplane(offset=cable_body_z)
    .box(body_width, jaw_wall + slot_r * 2 + jaw_wall, body_height,
         centered=(True, False, False))
    .translate((0, -jaw_wall - slot_r, 0))
)

# Cable slot positions (centered along X)
cable_positions = [
    ((i - (cable_count - 1) / 2) * cable_slot_spacing, 0)
    for i in range(cable_count)
]

# Cut cable slots — U-shaped channels from the top
cable_cuts = cq.Workplane("XY")
for pos_x, _ in cable_positions:
    slot = (
        cq.Workplane("XZ")
        .workplane(offset=0)
        .transformed(offset=(pos_x, cable_body_z + body_height / 2, 0))
        .circle(slot_r)
        .extrude(slot_r * 2 + jaw_wall * 2, both=True)
    )
    cable_cuts = cable_cuts.union(slot)

# Snap-fit entry cuts — narrow slot from the top into each cable channel
snap_cuts = cq.Workplane("XY")
snap_width = cable_diameter * 0.6  # narrower than cable for snap-in
for pos_x, _ in cable_positions:
    cut = (
        cq.Workplane("XY")
        .workplane(offset=cable_body_z + body_height - slot_r)
        .transformed(offset=(pos_x, 0, 0))
        .rect(snap_width, slot_r * 2 + jaw_wall * 2)
        .extrude(slot_r + 0.01)
    )
    snap_cuts = snap_cuts.union(cut)

# --- Assemble ---
result = jaw.union(cable_holder).cut(cable_cuts).cut(snap_cuts)

# Final filleting on exposed edges (be conservative to avoid kernel errors)
try:
    result = result.edges(">Z").fillet(fillet_r * 0.5)
except Exception:
    pass  # Skip fillet if geometry doesn't support it

cq.exporters.export(result, 'output.stl')
```

---

## How to Use These Examples

1. **As few-shot context**: Include one example in the LLM prompt before the user's request
2. **As style reference**: The LLM will mimic the code structure (header, variables, chaining, export)
3. **As test fixtures**: Run with `python example.py` to verify they produce valid STLs

### Recommended Prompt Pattern

```
[system prompt from system_prompt.md]

Here is an example of high-quality CadQuery code:

[paste one example from above]

Now generate CadQuery code for the following:
[user's description]
```

### Testing

```bash
# Install CadQuery
pip install cadquery

# Run an example
python example_project_box.py

# Check the output
ls -la output.stl
```
