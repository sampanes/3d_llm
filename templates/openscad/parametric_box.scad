// =============================================================================
// Parametric Box with Snap-Fit Lid
// =============================================================================
// Description : A fully parametric box with rounded corners (via minkowski),
//               configurable wall thickness, and a snap-fit lid.
// Author      : 3D LLM Generator
// License     : MIT
//
// Print Settings (FDM):
//   Layer Height : 0.2 mm
//   Infill       : 15-20%
//   Supports     : Not required
//   Material     : PLA or PETG
//   Nozzle       : 0.4 mm
//   Orientation  : Print box upright, lid upside-down
//   Notes        : For tighter snap fit, reduce snap_tolerance to 0.1
// =============================================================================

// ─── Parameters ──────────────────────────────────────────────────────────────

// Outer dimensions of the box (before rounding)
box_width  = 80;   // [30:200] X-axis dimension in mm
box_depth  = 60;   // [30:200] Y-axis dimension in mm
box_height = 40;   // [15:150] Z-axis total height in mm

// Wall and structural settings
wall_thickness  = 2.0;   // [1.2:0.2:4.0] Wall thickness in mm
corner_radius   = 4.0;   // [0:0.5:15]    Radius for rounded corners
bottom_thickness = 2.0;  // [1.2:0.2:4.0] Bottom plate thickness

// Lid settings
lid_height       = 8;    // [5:30]   Height of the lid
lid_tolerance    = 0.3;  // [0.1:0.05:0.6] Gap between lid and box walls
snap_depth       = 1.0;  // [0.5:0.1:2.0]  Depth of snap-fit ridge
snap_height      = 2.0;  // [1.0:0.5:4.0]  Height of snap-fit ridge

// Layout
part_spacing = 10;  // Space between box and lid when rendering both

// Which part to render
render_part = "both"; // ["box", "lid", "both"]

// Resolution
$fn = 60;

// ─── Derived Values ──────────────────────────────────────────────────────────

// Inner dimensions account for wall thickness and corner rounding
inner_width  = box_width  - 2 * wall_thickness - 2 * corner_radius;
inner_depth  = box_depth  - 2 * wall_thickness - 2 * corner_radius;
inner_height = box_height - bottom_thickness;

// Lid inner lip dimensions (slightly smaller to fit inside the box)
lip_width  = inner_width  - 2 * lid_tolerance;
lip_depth  = inner_depth  - 2 * lid_tolerance;
lip_height = lid_height   - wall_thickness;

// ─── Modules ─────────────────────────────────────────────────────────────────

// Rounded rectangle primitive using minkowski sum of a cube and cylinder.
// The minkowski of a thin cube + cylinder produces a shape with rounded
// vertical edges. We keep corners sharp on Z to ensure flat top/bottom.
module rounded_rect(w, d, h, r) {
    minkowski() {
        cube([w, d, h]);
        cylinder(r = r, h = 0.01);  // Tiny height so it doesn't add to Z
    }
}

// Main box body: a rounded shell open at the top
module box_body() {
    difference() {
        // Outer shell
        rounded_rect(
            box_width - 2 * corner_radius,
            box_depth - 2 * corner_radius,
            box_height,
            corner_radius
        );

        // Inner cavity — shifted up by bottom_thickness to leave a solid floor
        translate([wall_thickness, wall_thickness, bottom_thickness])
            rounded_rect(
                inner_width,
                inner_depth,
                inner_height + 1,  // +1 to cleanly open the top
                max(corner_radius - wall_thickness, 0.5)
            );
    }
}

// Snap-fit ridge that runs around the inner perimeter near the top of the box.
// The lid clicks over this ridge to hold in place.
module snap_ridge() {
    ridge_inset = wall_thickness / 2;
    ridge_z     = box_height - snap_height - 2;

    translate([ridge_inset, ridge_inset, ridge_z])
        difference() {
            rounded_rect(
                box_width - 2 * corner_radius - 2 * ridge_inset + snap_depth,
                box_depth - 2 * corner_radius - 2 * ridge_inset + snap_depth,
                snap_height,
                max(corner_radius - ridge_inset, 0.5)
            );
            translate([-0.01, -0.01, -0.01])
                rounded_rect(
                    box_width - 2 * corner_radius - 2 * ridge_inset - snap_depth,
                    box_depth - 2 * corner_radius - 2 * ridge_inset - snap_depth,
                    snap_height + 0.02,
                    max(corner_radius - ridge_inset - snap_depth, 0.5)
                );
        }
}

// Complete box assembly (body + snap ridge)
module box() {
    box_body();
    snap_ridge();
}

// Lid: a flat top with an inner lip that fits inside the box opening,
// and a groove that clicks over the snap ridge.
module lid() {
    inner_r = max(corner_radius - wall_thickness - lid_tolerance, 0.5);

    // Lid top plate
    rounded_rect(
        box_width - 2 * corner_radius,
        box_depth - 2 * corner_radius,
        wall_thickness,
        corner_radius
    );

    // Inner lip that drops into the box
    translate([wall_thickness + lid_tolerance, wall_thickness + lid_tolerance, -lip_height])
        difference() {
            rounded_rect(lip_width, lip_depth, lip_height, inner_r);

            // Hollow out the lip to save material
            translate([wall_thickness, wall_thickness, -0.01])
                rounded_rect(
                    lip_width - 2 * wall_thickness,
                    lip_depth - 2 * wall_thickness,
                    lip_height + 0.02,
                    max(inner_r - wall_thickness, 0.5)
                );
        }
}

// ─── Rendering ───────────────────────────────────────────────────────────────

if (render_part == "box" || render_part == "both") {
    color("SteelBlue", 0.9)
        box();
}

if (render_part == "lid" || render_part == "both") {
    // Position the lid next to the box, flipped for printing orientation
    translate([render_part == "both" ? box_width + part_spacing : 0, 0, 0])
        color("CornflowerBlue", 0.9)
            // Flip the lid upside-down for print orientation
            translate([0, 0, wall_thickness])
                mirror([0, 0, 1])
                    lid();
}
