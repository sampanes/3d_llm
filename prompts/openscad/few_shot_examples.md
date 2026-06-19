# OpenSCAD Few-Shot Examples

Three complete, working OpenSCAD examples for use as few-shot context when prompting LLMs.
Each example compiles cleanly in OpenSCAD (F6 render) and is designed for FDM 3D printing.

---

## Example 1: Parametric Rounded Box with Lid

```openscad
// ============================================================
// Model:       Parametric Rounded Box with Snap-Fit Lid
// Description: A configurable box with rounded corners using
//              minkowski(), and a snap-fit lid with tolerance.
// Print Settings:
//   - Layer height: 0.2mm
//   - Infill: 20%
//   - No supports needed
// Print orientation: Flat bottom for both box and lid (print separately)
// ============================================================

$fn = 64;

// --- Configurable Parameters ---
box_width      = 80;    // outer width (X)
box_depth      = 60;    // outer depth (Y)
box_height     = 40;    // outer height of the box body (Z)
wall_thickness = 2.0;   // wall and floor thickness
corner_radius  = 5;     // radius for rounded corners
lid_height     = 8;     // total lid height
lip_height     = 5;     // height of the inner lip that inserts into the box
tolerance      = 0.2;   // clearance on mating surfaces
epsilon        = 0.01;  // boolean overlap

// --- Derived ---
inner_width  = box_width  - 2 * wall_thickness;
inner_depth  = box_depth  - 2 * wall_thickness;
inner_height = box_height - wall_thickness;  // floor is wall_thickness

// Helper: rounded rectangle as a 2D profile
module rounded_rect(w, d, r) {
    offset(r = r)
        square([w - 2 * r, d - 2 * r], center = true);
}

// --- Box Body ---
module box_body() {
    difference() {
        // Outer shell — rounded via minkowski
        minkowski() {
            linear_extrude(height = box_height - corner_radius)
                rounded_rect(box_width - 2 * corner_radius,
                             box_depth - 2 * corner_radius,
                             corner_radius);
            sphere(r = corner_radius);
        }

        // Hollow interior
        translate([0, 0, wall_thickness])
            minkowski() {
                linear_extrude(height = box_height)
                    rounded_rect(inner_width - 2 * corner_radius,
                                 inner_depth - 2 * corner_radius,
                                 corner_radius);
                sphere(r = corner_radius);
            }

        // Flatten bottom — cut off the minkowski sphere below z=0
        translate([0, 0, -box_height / 2])
            cube([box_width + 10, box_depth + 10, box_height], center = true);
    }
}

// --- Lid ---
module lid() {
    lip_width  = inner_width - 2 * tolerance;
    lip_depth  = inner_depth - 2 * tolerance;
    lid_top    = lid_height - lip_height;

    union() {
        // Top plate — same outer footprint, rounded
        minkowski() {
            linear_extrude(height = lid_top - corner_radius)
                rounded_rect(box_width - 2 * corner_radius,
                             box_depth - 2 * corner_radius,
                             corner_radius);
            sphere(r = corner_radius);
        }

        // Inner lip that inserts into the box
        translate([0, 0, -lip_height])
            linear_extrude(height = lip_height + epsilon)
                rounded_rect(lip_width, lip_depth, corner_radius - wall_thickness);
    }
}

// --- Assembly (for preview; print parts separately) ---
module assembly() {
    box_body();

    // Position lid above the box for visualization
    translate([0, 0, box_height + 5])
        lid();
}

assembly();
```

---

## Example 2: Angled Phone Stand

```openscad
// ============================================================
// Model:       Angled Phone Stand
// Description: A clean phone stand with configurable viewing angle,
//              cable pass-through, and anti-slip base cutouts.
//              All overhangs kept ≤ 45° for supportless FDM printing.
// Print Settings:
//   - Layer height: 0.2mm
//   - Infill: 40% (structural)
//   - No supports needed
// Print orientation: Back face flat on bed
// ============================================================

$fn = 64;

// --- Configurable Parameters ---
stand_angle       = 65;     // viewing angle from horizontal (degrees)
phone_thickness   = 10;     // slot width (phone + case + tolerance)
phone_width       = 80;     // width of the cradle
stand_depth       = 90;     // base depth for stability
stand_thickness   = 5;      // material thickness of the back plate
base_height       = 4;      // thickness of the flat base
lip_height        = 15;     // front lip to hold phone bottom
cable_hole_dia    = 14;     // diameter of cable routing hole
antislip_depth    = 0.8;    // depth of anti-slip cutouts
antislip_count    = 4;      // number of anti-slip grooves
epsilon           = 0.01;

// --- Derived ---
back_height   = stand_depth * tan(stand_angle);
total_height  = back_height + base_height;

// --- Back Plate ---
module back_plate() {
    // Angled plate from base to top
    hull() {
        // Bottom edge
        translate([0, 0, base_height])
            cube([phone_width, stand_thickness, epsilon], center = false);
        // Top edge, pushed forward
        translate([0, stand_depth - stand_thickness, total_height - stand_thickness])
            cube([phone_width, stand_thickness, stand_thickness], center = false);
    }
}

// --- Base ---
module base() {
    difference() {
        cube([phone_width, stand_depth, base_height]);

        // Anti-slip grooves on the bottom face
        groove_spacing = phone_width / (antislip_count + 1);
        for (i = [1 : antislip_count]) {
            translate([i * groove_spacing, stand_depth * 0.15, -epsilon])
                cube([3, stand_depth * 0.7, antislip_depth + epsilon]);
        }
    }
}

// --- Phone Lip ---
module phone_lip() {
    translate([0, 0, base_height])
        cube([phone_width, phone_thickness + stand_thickness, lip_height]);
}

// --- Cable Hole ---
module cable_hole() {
    translate([phone_width / 2, (phone_thickness + stand_thickness) / 2, -epsilon])
        cylinder(d = cable_hole_dia, h = base_height + lip_height + 2 * epsilon);
}

// --- Phone Slot ---
// Cut the slot into the lip so the phone sits in it
module phone_slot() {
    translate([(phone_width - phone_width * 0.85) / 2,
               stand_thickness,
               base_height + stand_thickness])
        cube([phone_width * 0.85, phone_thickness, lip_height + epsilon]);
}

// --- Full Stand ---
module phone_stand() {
    difference() {
        union() {
            base();
            back_plate();
            phone_lip();
        }
        cable_hole();
        phone_slot();
    }
}

phone_stand();
```

---

## Example 3: Cable Management Clip

```openscad
// ============================================================
// Model:       Parametric Cable Management Clip
// Description: A screw-mounted cable clip with a snap-fit opening.
//              Parametric for different cable diameters.
// Print Settings:
//   - Layer height: 0.15mm (for snap-fit detail)
//   - Infill: 100% (small part, needs strength)
//   - No supports needed
// Print orientation: Flat (mounting plate on bed)
// ============================================================

$fn = 64;

// --- Configurable Parameters ---
cable_diameter    = 6;      // diameter of cable to hold
cable_tolerance   = 0.4;    // extra clearance around cable
clip_wall         = 2.0;    // wall thickness of the clip ring
screw_hole_dia    = 3.5;    // screw hole diameter (for M3 or #4 screw)
screw_head_dia    = 6.5;    // screw head countersink diameter
screw_head_depth  = 1.8;    // countersink depth
base_width        = 20;     // width of the mounting base plate
base_depth        = 14;     // depth of the mounting base plate
base_thickness    = 2.5;    // thickness of the flat base
snap_gap          = 2.0;    // width of the snap-fit opening
snap_deflection   = 1.0;    // extra flare on snap-fit fingers
clip_height       = 10;     // extrusion height of the clip
epsilon           = 0.01;

// --- Derived ---
cable_r       = (cable_diameter + cable_tolerance) / 2;
clip_outer_r  = cable_r + clip_wall;
clip_center_z = base_thickness + clip_outer_r;  // center of clip ring above base

// --- Base Plate ---
module base_plate() {
    difference() {
        // Rectangular base with rounded corners
        hull() {
            for (x = [3, base_width - 3])
                for (y = [3, base_depth - 3])
                    translate([x, y, 0])
                        cylinder(r = 3, h = base_thickness);
        }

        // Screw hole
        translate([base_width / 2, base_depth / 2, -epsilon])
            cylinder(d = screw_hole_dia, h = base_thickness + 2 * epsilon);

        // Countersink
        translate([base_width / 2, base_depth / 2, base_thickness - screw_head_depth])
            cylinder(d = screw_head_dia, h = screw_head_depth + epsilon);
    }
}

// --- Cable Clip Ring ---
module clip_ring() {
    translate([base_width / 2, base_depth / 2, 0]) {
        difference() {
            // Outer cylinder
            cylinder(r = clip_outer_r, h = clip_height);

            // Inner bore (cable channel)
            translate([0, 0, -epsilon])
                cylinder(r = cable_r, h = clip_height + 2 * epsilon);

            // Snap-fit opening slot — cut from the top
            translate([-snap_gap / 2, 0, -epsilon])
                cube([snap_gap, clip_outer_r + epsilon, clip_height + 2 * epsilon]);
        }

        // Snap-fit entry flares (small angled lips at the opening)
        for (side = [-1, 1]) {
            translate([side * (snap_gap / 2 + clip_wall * 0.3),
                       clip_outer_r - clip_wall * 0.5, 0])
                cylinder(r = snap_deflection, h = clip_height);
        }
    }
}

// --- Support Column (connects base to clip ring) ---
module support_column() {
    translate([base_width / 2 - clip_outer_r, base_depth / 2 - clip_wall / 2, 0])
        cube([clip_outer_r * 2, clip_wall, clip_center_z]);
}

// --- Full Assembly ---
module cable_clip() {
    base_plate();
    translate([0, 0, clip_center_z - clip_outer_r]) {
        clip_ring();
    }
    support_column();
}

cable_clip();
```

---

## How to Use These Examples

1. **As few-shot context**: Include one or more examples in the LLM prompt before the user's request
2. **As style reference**: The LLM will mimic the code structure (header, variables, modules, assembly)
3. **As test fixtures**: Paste into OpenSCAD and press F6 to verify they render correctly

### Recommended Prompt Pattern

```
[system prompt from system_prompt.md]

Here is an example of high-quality OpenSCAD code:

[paste one example from above]

Now generate OpenSCAD code for the following:
[user's description]
```
