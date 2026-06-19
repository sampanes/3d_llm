// =============================================================================
// Parametric Cable Management Clip
// =============================================================================
// Description : A spring-action cable clip with screw mounting hole.
//               Works for various cable diameters. The clip grips the cable
//               via two flexible arms that deflect when the cable is pressed in.
// Author      : 3D LLM Generator
// License     : MIT
//
// Print Settings (FDM):
//   Layer Height : 0.16 - 0.2 mm
//   Infill       : 100% (small part, needs strength)
//   Supports     : Not required
//   Material     : PETG or TPU recommended (PLA is brittle for spring arms)
//   Nozzle       : 0.4 mm
//   Orientation  : Print flat on the base
//   Notes        : Print slowly for the thin spring arms (~30 mm/s)
// =============================================================================

// ─── Parameters ──────────────────────────────────────────────────────────────

// Cable
cable_diameter = 6;     // [2:0.5:20] Diameter of the cable in mm

// Clip geometry
clip_wall       = 2.0;  // [1.5:0.5:4] Wall thickness around cable channel
clip_depth      = 10;   // [6:20]      Depth of clip body (Z height)
grip_percentage = 75;   // [50:90]     How much of the cable circumference is gripped (%)

// Spring arm settings
arm_thickness = 1.2;    // [0.8:0.1:2.0] Thickness of each spring arm
arm_gap       = 1.5;    // [1.0:0.5:3.0] Gap between arm tips (cable entry slot)
arm_flare     = 2.0;    // [0:4]         Outward flare at arm tips for easy insertion

// Mounting hole
mount_hole_diameter = 3.5;  // [0:0.5:6] Screw hole diameter (0 = no hole)
mount_pad_width     = 10;   // [8:20]    Width of the mounting pad
mount_pad_height    = 5;    // [3:10]    Height of the mounting pad below clip

// Resolution
$fn = 60;

// ─── Derived Values ──────────────────────────────────────────────────────────

cable_r    = cable_diameter / 2;
clip_r     = cable_r + clip_wall;
grip_angle = grip_percentage / 100 * 360;
open_angle = 360 - grip_angle;

// Total body width and height for positioning
body_width = clip_r * 2;

// ─── Modules ─────────────────────────────────────────────────────────────────

// The main clip body: a C-shaped channel that wraps around the cable
module clip_body() {
    difference() {
        // Outer cylinder
        cylinder(r = clip_r, h = clip_depth);

        // Inner channel (cable void) — runs full length + clearance
        translate([0, 0, -0.5])
            cylinder(r = cable_r, h = clip_depth + 1);

        // Cut away the opening at the top for cable insertion
        // The opening faces +Y (top)
        rotate([0, 0, 90 - open_angle / 2])
            wedge_cut(clip_r + 1, open_angle, clip_depth);
    }
}

// A pie-slice shaped cutter used to open the clip channel
module wedge_cut(r, angle, h) {
    // Use intersection of rotated planes to cut a wedge
    translate([0, 0, -0.5])
        linear_extrude(height = h + 1)
            polygon(points = concat(
                [[0, 0]],
                [for (a = [0 : 1 : angle])
                    [r * cos(a), r * sin(a)]
                ]
            ));
}

// Flexible spring arms at the opening that deflect to let the cable snap in
module spring_arms() {
    arm_length = clip_r + arm_flare;

    for (side = [-1, 1]) {
        rotate([0, 0, 90 + side * (open_angle / 2)])
            translate([cable_r - 0.5, -arm_thickness / 2, 0]) {
                // Main arm body
                cube([clip_wall + 0.5, arm_thickness, clip_depth]);

                // Flared tip for easy cable insertion
                translate([clip_wall + 0.5, 0, 0])
                    hull() {
                        cube([0.1, arm_thickness, clip_depth]);
                        translate([arm_flare, -side * arm_flare, 0])
                            cube([0.1, arm_thickness, clip_depth]);
                    }
            }
    }
}

// Flat base pad with screw mounting hole
module mounting_base() {
    pad_length = mount_pad_width;
    pad_total_h = mount_pad_height;

    translate([-pad_length / 2, -clip_r, -pad_total_h])
        difference() {
            // Rectangular mounting pad
            cube([pad_length, clip_r, pad_total_h + 0.01]);

            // Screw hole (vertical, centered in pad)
            if (mount_hole_diameter > 0) {
                translate([pad_length / 2, clip_r / 2, -0.5])
                    cylinder(d = mount_hole_diameter, h = pad_total_h + 1);

                // Countersink on bottom
                translate([pad_length / 2, clip_r / 2, -0.5])
                    cylinder(
                        d1 = mount_hole_diameter * 2,
                        d2 = mount_hole_diameter,
                        h = mount_hole_diameter * 0.6
                    );
            }
        }
}

// ─── Assembly ────────────────────────────────────────────────────────────────

module cable_clip() {
    color("OliveDrab") {
        clip_body();
        spring_arms();
        mounting_base();
    }
}

// ─── Render ──────────────────────────────────────────────────────────────────

cable_clip();
