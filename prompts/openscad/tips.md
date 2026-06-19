# OpenSCAD LLM Generation Tips

Practical advice for getting better OpenSCAD output from LLMs — common pitfalls, workarounds, and model-specific notes.

---

## Common LLM Mistakes and Prompt Fixes

### 1. Wrapping output in markdown fences

**Problem**: The LLM wraps code in ` ```openscad ... ``` ` blocks, which aren't valid OpenSCAD.

**Fix**: Add to your prompt:
```
Output ONLY raw OpenSCAD code. Do NOT wrap in markdown code fences.
```

### 2. Using undefined functions

**Problem**: LLMs hallucinate functions like `fillet()`, `round_edges()`, or `smooth()` that don't exist in OpenSCAD.

**Fix**: Add to your prompt:
```
Use ONLY built-in OpenSCAD functions and modules. There is no fillet() or chamfer() built-in.
To round edges, use minkowski() with sphere() or cylinder(), or hull() between offset shapes.
```

### 3. Non-manifold geometry

**Problem**: Boolean operations leave zero-thickness walls or coincident faces, causing OpenSCAD render warnings and broken STLs.

**Fix**: Always remind the LLM:
```
Add 0.01mm (epsilon) overlap on all boolean cutting geometry to prevent coincident faces.
```

### 4. Forgetting to call the top-level module

**Problem**: LLM defines all modules but never calls the final assembly, so nothing renders.

**Fix**:
```
After all module definitions, call the top-level assembly module as the last line of the file.
```

### 5. Incorrect use of `center = true`

**Problem**: Mixing centered and non-centered geometry leads to misaligned parts.

**Fix**:
```
Use center = true consistently for all primitives, or explicitly document when you don't.
```

### 6. Thin walls that won't print

**Problem**: LLMs generate walls of 0.5mm or 0.4mm — too thin for most FDM printers.

**Fix**:
```
Minimum wall thickness must be 1.2mm (3 perimeters × 0.4mm nozzle).
```

### 7. Impossible overhangs

**Problem**: Features like horizontal holes or flat bridges without support geometry.

**Fix**:
```
All overhangs must be ≤ 45° from vertical. For horizontal holes, use teardrop shapes.
```

---

## Boolean Operation Gotchas

### The Epsilon Rule
Always extend cutting geometry by `epsilon = 0.01` beyond the surface:

```openscad
// BAD — coincident face causes rendering artifacts
difference() {
    cube([10, 10, 10]);
    translate([2, 2, 0])
        cube([6, 6, 5]);  // bottom face is coincident with parent
}

// GOOD — cutting geometry extends through
difference() {
    cube([10, 10, 10]);
    translate([2, 2, -0.01])
        cube([6, 6, 5.02]);  // extends 0.01 past both faces
}
```

### Order Matters in `difference()`
The **first** child is the positive shape; all subsequent children are subtracted.

```openscad
// Correct: subtract cylinder from cube
difference() {
    cube([20, 20, 10], center = true);    // kept
    cylinder(d = 8, h = 11, center = true); // subtracted
}
```

### Nested Booleans
Complex models often need nested `union()` inside `difference()`:

```openscad
difference() {
    union() {
        // all the positive geometry
        part_a();
        part_b();
    }
    // all the cuts
    hole_a();
    hole_b();
}
```

### `minkowski()` Inflates Dimensions
`minkowski()` **adds** the dimensions of the second shape to the first. If you want the result to be a specific outer size, shrink the base shape accordingly:

```openscad
// Want a 40×30×20 box with 3mm radius corners
target_w = 40;
target_d = 30;
target_h = 20;
r = 3;

minkowski() {
    cube([target_w - 2*r, target_d - 2*r, target_h - r], center = true);
    sphere(r = r);
}
```

---

## Performance Tips ($fn Tuning)

| Feature Type           | Recommended `$fn` | Why                                    |
| ---------------------- | ------------------ | -------------------------------------- |
| Large cylinders/curves | 64                 | Good balance of quality vs. speed      |
| Small holes (< 5mm)    | 32                 | Fine detail isn't visible at this size |
| Precision threads      | 128                | Need smooth mating surfaces            |
| Preview during dev     | 24                 | Fast iteration, set globally           |
| Final render           | 64–128             | Production quality                     |

### Set `$fn` Per-Feature When Needed

```openscad
$fn = 64;  // global default

module precision_bore() {
    cylinder(d = 3, h = 10, $fn = 128);  // override for this feature
}
```

### Avoid `$fn` on `sphere()` inside `minkowski()`
High `$fn` on a `minkowski()` sphere causes exponential render time growth. Use `$fn = 24` or `$fn = 32` for the minkowski sphere and increase only for the final export.

---

## Multi-Part Assembly Tips

### Design for Separate Printing
Always design mating parts as separate modules, then combine in an assembly module for preview:

```openscad
module box() { /* ... */ }
module lid() { /* ... */ }

// Preview assembly
module assembly() {
    box();
    translate([0, 0, box_height + 5]) lid();
}

// For printing: render one at a time
// assembly();   // for preview
box();           // uncomment one for export
// lid();
```

### Registration / Alignment Features
Add alignment pins and sockets for multi-part assemblies:

```openscad
pin_diameter = 3;
pin_height   = 4;
pin_tolerance = 0.2;

module alignment_pin() {
    cylinder(d = pin_diameter, h = pin_height);
}

module alignment_socket() {
    translate([0, 0, -0.01])
        cylinder(d = pin_diameter + pin_tolerance, h = pin_height + 0.2);
}
```

### Tolerance Guidelines

| Joint Type          | Tolerance (per side) | Notes                        |
| ------------------- | -------------------- | ---------------------------- |
| Loose slip fit      | 0.3–0.4mm           | Parts slide together easily  |
| Snug fit            | 0.15–0.2mm          | Firm push fit                |
| Press / friction    | 0.05–0.1mm          | Requires force, may need PLA |
| Snap fit            | 0.2mm + flex design  | Depends on material          |

---

## LLM-Specific Behavioral Notes

### GPT-4 / GPT-4o
- **Strengths**: Good at complex geometry, understands spatial reasoning well, follows system prompts closely.
- **Weaknesses**: Tends to over-comment code. Sometimes adds `echo()` statements or `assert()` that aren't needed. May generate overly complex module hierarchies.
- **Tip**: Add `"Keep comments minimal — header and key decisions only."` to reduce verbosity.

### Claude (3.5 Sonnet / Opus)
- **Strengths**: Excellent at following formatting rules. Produces clean, well-structured code. Good parametric variable naming.
- **Weaknesses**: Can be overly cautious — adds unnecessary helper modules or validation. Sometimes uses `let()` syntax that older OpenSCAD versions don't support.
- **Tip**: Specify `"Target OpenSCAD 2021.01 or later."` for version compatibility. Add `"Be direct — don't add unnecessary abstractions."`.

### Gemini (1.5 Pro / Ultra)
- **Strengths**: Good at mathematical geometry. Handles trigonometric calculations well.
- **Weaknesses**: More likely to hallucinate non-existent OpenSCAD built-ins. May produce code that mixes OpenSCAD with other languages' syntax.
- **Tip**: Add explicit reminders about OpenSCAD-specific syntax: `"OpenSCAD is NOT Python. Use module/function syntax, not def/class."`.

### Smaller / Local Models (Llama, Mistral, etc.)
- **Strengths**: Fast iteration for simple models.
- **Weaknesses**: Struggle with complex boolean operations. Often produce non-manifold geometry. May not handle `minkowski()` or `hull()` correctly.
- **Tip**: Use the concise prompt variant. Keep requests simple — one feature at a time. Provide a full few-shot example.

---

## Debugging Workflow

1. **Paste LLM output into OpenSCAD**
2. **Press F5** (preview) — check for visual errors
3. **Press F6** (full render) — check console for manifold warnings
4. **If errors**: copy the error message and feed it back to the LLM:
   ```
   The following OpenSCAD code produced this error:
   [error message]

   Fix the code to resolve this error. Output only the corrected code.
   ```
5. **Export STL** and open in slicer to verify printability
