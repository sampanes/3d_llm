// =============================================================================
// Parametric Threaded Cap (FDM-Friendly)
// =============================================================================
// Description : A threaded bottle/jar cap with simplified thread profile
//               suitable for FDM printing. Uses helical groove approximation
//               via stacked rotated slices. Includes optional knurled grip.
// Author      : 3D LLM Generator
// License     : MIT
//
// Print Settings (FDM):
//   Layer Height : 0.15 - 0.2 mm (finer = better thread quality)
//   Infill       : 20-30%
//   Supports     : Not required
//   Material     : PLA or PETG
//   Nozzle       : 0.4 mm
//   Orientation  : Print cap upside-down (open end up)
//   Notes        : Test thread fit; adjust thread_tolerance if too tight/loose.
//                  Print a short test piece first (set cap_height = 8).
// =============================================================================

// ─── Parameters ──────────────────────────────────────────────────────────────

// Thread specifications
thread_outer_diameter = 30;   // [15:80]  Outer diameter of the thread (mm)
thread_pitch          = 3.0;  // [1.5:0.5:6.0] Distance between thread peaks (mm)
thread_depth          = 1.2;  // [0.6:0.1:2.5] Radial depth of the thread groove
thread_starts         = 1;    // [1:4]    Number of thread starts (1=single, 2=double, etc.)
thread_tolerance      = 0.4;  // [0.2:0.05:0.8] Extra clearance for mating fit

// Cap dimensions
cap_height    = 15;   // [8:40]   Total height of the cap
cap_wall      = 2.5;  // [2:5]    Wall thickness of the cap body
cap_top       = 2.0;  // [1.5:4]  Thickness of the cap's closed top

// Knurling (grip texture on the outside)
knurl_enable  = true;           // Enable/disable knurled grip
knurl_count   = 36;   // [12:72] Number of knurl ridges around circumference
knurl_depth   = 0.6;  // [0.3:0.1:1.5] Depth of each knurl groove
knurl_width   = 0.8;  // [0.4:0.1:1.5] Width of each knurl groove

// Resolution
$fn = 120;  // High resolution needed for threads

// ─── Derived Values ──────────────────────────────────────────────────────────

cap_outer_r   = thread_outer_diameter / 2 + cap_wall;
thread_r      = thread_outer_diameter / 2;
thread_inner_r = thread_r - thread_depth;

// Number of full turns the thread makes over the cap height
thread_turns = (cap_height - cap_top) / thread_pitch;

// Angular step per layer for the helical approximation
// We use fine slicing (0.2mm steps) for smooth threads
slice_height = 0.2;
num_slices   = floor((cap_height - cap_top) / slice_height);

// ─── Modules ─────────────────────────────────────────────────────────────────

// A single thread tooth cross-section (trapezoidal for FDM strength)
// This is a 2D profile that gets swept helically.
module thread_tooth_2d() {
    // Trapezoidal tooth: wider at root, narrower at peak
    root_half = thread_pitch / (thread_starts * 4);
    tip_half  = root_half * 0.6;

    polygon([
        [-root_half, 0],
        [-tip_half,  thread_depth],
        [ tip_half,  thread_depth],
        [ root_half, 0]
    ]);
}

// Internal thread via helical groove subtracted from inner cylinder wall.
// Uses stacked ring segments, each rotated slightly, to approximate a helix.
module internal_threads() {
    thread_height = cap_height - cap_top;

    for (start = [0 : thread_starts - 1]) {
        start_angle = start * (360 / thread_starts);

        for (i = [0 : num_slices - 1]) {
            z = i * slice_height;
            angle = start_angle + (z / thread_pitch) * 360;

            translate([0, 0, z])
                rotate([0, 0, angle])
                    translate([thread_inner_r, 0, 0])
                        linear_extrude(height = slice_height + 0.01)
                            thread_tooth_2d();
        }
    }
}

// Cap body: hollow cylinder with closed top
module cap_body() {
    difference() {
        // Outer shell
        cylinder(r = cap_outer_r, h = cap_height);

        // Inner bore (where the bottle neck / threads go)
        translate([0, 0, -0.01])
            cylinder(r = thread_r + thread_tolerance, h = cap_height - cap_top + 0.01);
    }
}

// Knurled texture: small grooves cut into the outer surface
module knurling() {
    if (knurl_enable) {
        knurl_height = cap_height - 2;  // Leave a small rim at top and bottom

        for (i = [0 : knurl_count - 1]) {
            angle = i * (360 / knurl_count);
            rotate([0, 0, angle])
                translate([cap_outer_r - knurl_depth, -knurl_width / 2, 1])
                    cube([knurl_depth + 0.5, knurl_width, knurl_height]);
        }
    }
}

// Top grip texture: radial lines on the cap top for grip when twisting
module top_grip() {
    num_lines = 12;
    line_width = 0.8;
    line_depth = 0.4;

    for (i = [0 : num_lines - 1]) {
        angle = i * (360 / num_lines);
        rotate([0, 0, angle])
            translate([-line_width / 2, 0, cap_height - line_depth])
                cube([line_width, cap_outer_r - 2, line_depth + 0.01]);
    }
}

// ─── Assembly ────────────────────────────────────────────────────────────────

module threaded_cap() {
    difference() {
        union() {
            cap_body();
            internal_threads();
        }
        knurling();
        top_grip();
    }
}

// ─── Render ──────────────────────────────────────────────────────────────────

color("DarkGoldenrod")
    threaded_cap();

// ─── Notes ───────────────────────────────────────────────────────────────────
// To create the matching bottle neck / male thread:
//   1. Use the same thread_outer_diameter, thread_pitch, and thread_starts
//   2. Create an outer cylinder at thread_r - thread_tolerance
//   3. Add external thread teeth (same profile, on the outside)
//   4. Test fit and adjust thread_tolerance as needed
// =============================================================================
