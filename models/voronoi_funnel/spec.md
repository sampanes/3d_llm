# voronoi_funnel — twisted open-cell Voronoi vase

## What was asked

Recreate the structure in the user's print photo (`refs/print_photo.png`):
a twisted funnel/vase whose entire surface is an **open Voronoi lattice** —
irregular polygonal cells with round struts along the cell edges, no solid
skin anywhere. The form rises from a thin printed base disk as a rounded
bulb, narrows through a waist, then flares wide to an open mouth, with the
cell pattern visibly spiraling (twisted) as it climbs.

This is what the user means by "skeleton" frameworks (vs. branching coral):
a **surface decomposed into cells**, not branched tubes.

## Dimensions (estimated from the photo — no hard numbers were given)

| Feature | Value | Tolerance |
|---|---|---|
| Total height | 160 mm | ±1 mm (geometric: rim torus top = height) |
| Mouth outer Ø | ~151 mm | ±3 mm (warp wobbles the outermost struts) |
| Base disk Ø × thickness | 112 × 2.4 mm | ±0.5 mm |
| Bulb max Ø / waist Ø | ~95 / ~69 mm | look reference |
| Strut Ø | ~3.2 mm | printability floor, junctions thicker |
| Cell count | ~190 (≈170 on the visible body) | look reference |
| Twist | 80° total, counterclockwise looking down | look reference |

All dimensions parametric in `params.json`; the profile is a list of
(radius, z) control points smoothed with Catmull-Rom.

## Look references

- `refs/print_photo.png` — the user's own print (gold filament, Prusa).
  Key traits to match: cell size relative to the form (~15–22 mm openings),
  round struts, fat 3-way junctions, gently *wavy* cell edges (not
  CAD-straight), smooth continuous rim band at the mouth, lattice growing
  straight out of a thin disk.

## Construction

`og.surface_points` scatters relaxed seeds on the revolved profile sheet →
`og.voronoi_lattice` turns the cell boundaries into round struts →
`sk.warp` makes the edges organically wavy → clip to [0, H−rim] → union a
rim torus (smooth mouth) + base disk → `sk.twist` the whole thing
(disk and rim are rotationally invariant, so only the cell pattern twists).

## Print notes

- Print as modeled (disk on bed). The disk is the brim — no extra adhesion
  needed.
- Lots of short bridges and steep strut overhangs: print slow with full
  part cooling, like the reference print. No supports — supports inside a
  lattice are not removable.
- Material in the photo is a gold/silk PLA; any PLA works.
