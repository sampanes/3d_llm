// =============================================================================
// Parametric Phone Stand
// =============================================================================
// Description : An adjustable-angle phone stand with cable pass-through,
//               configurable phone slot, and a stable weighted base.
// Author      : 3D LLM Generator
// License     : MIT
//
// Print Settings (FDM):
//   Layer Height : 0.2 mm
//   Infill       : 30-40% (higher for base stability)
//   Supports     : May be needed for cable hole overhang
//   Material     : PLA or PETG
//   Nozzle       : 0.4 mm
//   Orientation  : Print upright as-is
// =============================================================================

// ─── Parameters ──────────────────────────────────────────────────────────────

// Phone dimensions (slot sizing)
phone_width     = 80;   // [60:100]  Width of phone (X), slot will be slightly wider
phone_thickness = 12;   // [8:20]    Thickness of phone with case
slot_depth      = 20;   // [10:40]   How deep the phone sits in the slot

// Stand geometry
viewing_angle   = 65;   // [30:85]   Angle from horizontal (degrees)
back_height     = 120;  // [80:200]  Height of the back support panel
back_thickness  = 4;    // [3:8]     Thickness of the back support panel

// Base dimensions
base_width      = 100;  // [80:160]  Width of the base
base_depth      = 80;   // [50:120]  Depth of the base (front to back)
base_height     = 6;    // [4:12]    Thickness / height of the base

// Cable pass-through
cable_hole_diameter = 14;  // [0:25] Set to 0 to disable cable hole
cable_hole_offset_z = 15;  // [10:30] Height of hole center above base

// Lip / front ledge that prevents the phone from sliding off
lip_height    = 12;   // [8:25]  Height of the front lip
lip_thickness = 4;    // [3:8]   Thickness of the front lip

// Aesthetics
fillet_radius = 3;    // [0:8]   Fillet on base edges (visual only, approximated)

// Resolution
$fn = 60;

// ─── Derived Values ──────────────────────────────────────────────────────────

slot_width = phone_width + 4;  // 2 mm clearance on each side

// The back panel leans at the viewing_angle; we calculate the base offset
// so the panel bottom sits at the rear of the base.
panel_base_y = base_depth - back_thickness;

// ─── Modules ─────────────────────────────────────────────────────────────────

// Stable weighted base — a wide, flat slab
module base() {
    // Main base plate with slight chamfer via hull of two rects
    hull() {
        // Bottom plate — full size
        translate([0, 0, 0])
            cube([base_width, base_depth, base_height - fillet_radius]);

        // Top of base — slightly inset for a subtle chamfer
        translate([fillet_radius, fillet_radius, base_height - fillet_radius])
            cube([
                base_width - 2 * fillet_radius,
                base_depth - 2 * fillet_radius,
                fillet_radius
            ]);
    }
}

// The angled back panel that supports the phone
module back_panel() {
    translate([
        (base_width - slot_width) / 2,
        panel_base_y,
        base_height
    ])
    rotate([90 - viewing_angle, 0, 0])
        cube([slot_width, back_height, back_thickness]);
}

// Front lip / ledge that catches the bottom of the phone
module front_lip() {
    lip_y_start = panel_base_y - phone_thickness - lip_thickness;

    translate([
        (base_width - slot_width) / 2,
        lip_y_start,
        base_height
    ])
        cube([slot_width, lip_thickness, lip_height]);
}

// Phone slot: the recessed channel where the phone's bottom edge sits
module phone_slot() {
    slot_y = panel_base_y - phone_thickness;

    translate([
        (base_width - slot_width) / 2,
        slot_y,
        base_height
    ])
        cube([slot_width, phone_thickness, slot_depth]);
}

// Cable pass-through hole in the back panel and base
module cable_hole() {
    if (cable_hole_diameter > 0) {
        hole_x = base_width / 2;
        hole_y = panel_base_y + back_thickness / 2;
        hole_z = base_height + cable_hole_offset_z;

        // Hole through the base/panel junction area
        translate([hole_x, hole_y, hole_z])
            rotate([90 - viewing_angle, 0, 0])
                cylinder(
                    d = cable_hole_diameter,
                    h = back_thickness + 10,
                    center = true
                );

        // Secondary vertical hole through the base for cable routing
        translate([hole_x, hole_y, 0])
            cylinder(d = cable_hole_diameter, h = base_height + 2);
    }
}

// Anti-slip pads (small cylinders on the bottom for grip)
module anti_slip_pads() {
    pad_r      = 4;
    pad_h      = 0.8;
    pad_inset  = 8;

    positions = [
        [pad_inset,              pad_inset,              -pad_h],
        [base_width - pad_inset, pad_inset,              -pad_h],
        [pad_inset,              base_depth - pad_inset,  -pad_h],
        [base_width - pad_inset, base_depth - pad_inset,  -pad_h],
    ];

    for (pos = positions) {
        translate(pos)
            cylinder(r = pad_r, h = pad_h);
    }
}

// ─── Assembly ────────────────────────────────────────────────────────────────

module phone_stand() {
    difference() {
        union() {
            base();
            back_panel();
            front_lip();
            phone_slot();
            anti_slip_pads();
        }

        // Subtract the cable hole from the whole assembly
        cable_hole();
    }
}

// ─── Render ──────────────────────────────────────────────────────────────────

color("SlateGray")
    phone_stand();
