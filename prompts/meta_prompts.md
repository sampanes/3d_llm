# Meta-Prompts for 3D LLM Workflows

Reusable prompt templates for common multi-turn workflows: fixing errors, iterating designs, converting between tools, and self-evaluating printability.

---

## 1. Refining a Failed Generation (Error Recovery)

Use when OpenSCAD or CadQuery produces an error on the LLM's output.

### Template

```
The following {openscad|python/cadquery} code was generated but produced an error.

## Code
```
{paste the full generated code here}
```

## Error Output
```
{paste the exact error message or traceback here}
```

## Instructions
Fix the code to resolve this error. Follow these rules:
1. Output ONLY the complete, corrected code — no explanations, no markdown fences.
2. Preserve the existing parametric variable structure and naming.
3. Do NOT remove features — only fix the error.
4. If the error is geometric (non-manifold, kernel failure), simplify the problematic operation while keeping the design intent.
5. Add a comment `// FIX: [description]` next to each line you changed.
```

### Variant: Multiple Errors

```
The code below has multiple issues. The error log shows:
{paste errors}

Fix ALL errors in a single pass. Output the complete corrected file.
```

### Variant: Render Warning (not a hard error)

```
The code renders but OpenSCAD shows this warning:
{paste warning}

This warning indicates geometry problems that may cause issues during 3D printing.
Fix the underlying geometry issue. The most common cause is coincident faces in boolean operations — ensure all difference() cuts extend 0.01mm beyond the target surface.
```

---

## 2. Iterating on a Design (Modification Requests)

Use when you have working code and want to add, remove, or modify features.

### Template: Add a Feature

```
Here is working {openscad|cadquery} code for a {model description}:

```
{paste the working code}
```

Modify this code to add the following feature:
- {describe the new feature, with dimensions if known}

Rules:
1. Output the COMPLETE modified file, not just a diff.
2. Keep all existing parametric variables. Add new variables for the new feature at the top.
3. Maintain the same code style (modules/functions, naming, comments).
4. Ensure the new feature is FDM printable (min 1.2mm walls, no overhangs > 45°).
5. Do not break any existing geometry.
```

### Template: Change Dimensions

```
Here is working code:

```
{paste code}
```

Make these changes:
- Change {variable_name} from {old_value} to {new_value}
- {additional dimension changes}

Verify that the geometry is still valid after these changes (no intersecting walls, adequate thickness, etc.). If any dimension change would create invalid geometry, adjust related dimensions to compensate and add a comment explaining why.
```

### Template: Simplify / Reduce Complexity

```
The following code is too complex and slow to render:

```
{paste code}
```

Simplify it while preserving the overall shape and function:
- Reduce polygon count (lower $fn where appropriate)
- Replace minkowski() with hull() or manual geometry where possible
- Combine redundant boolean operations
- Remove purely decorative features that don't affect function
```

---

## 3. Converting Between OpenSCAD and CadQuery

### OpenSCAD → CadQuery

```
Convert the following OpenSCAD code to CadQuery (Python).

## OpenSCAD Code
```
{paste openscad code}
```

## Conversion Rules
1. Output ONLY valid Python with `import cadquery as cq`.
2. Map OpenSCAD constructs to CadQuery equivalents:
   - cube() → .box()
   - cylinder() → .cylinder() or .circle().extrude()
   - sphere() → .sphere() (via revolve or OCCT primitive)
   - difference() → .cut()
   - union() → .union()
   - intersection() → .intersect()
   - translate() → .translate() or workplane offset
   - rotate() → .rotate() or .transformed()
   - minkowski() → no direct equivalent; use .fillet() or manual construction
   - hull() → no direct equivalent; use .loft() or manual construction
   - linear_extrude() → .extrude()
   - rotate_extrude() → .revolve()
3. Preserve all parametric variables with the same names.
4. Use CadQuery's strengths: replace manual fillets with .fillet(), use selectors for edge operations.
5. End with `cq.exporters.export(result, 'output.stl')`.
6. Add comments noting where the translation required design changes.
```

### CadQuery → OpenSCAD

```
Convert the following CadQuery Python code to OpenSCAD.

## CadQuery Code
```
{paste cadquery code}
```

## Conversion Rules
1. Output ONLY valid OpenSCAD code.
2. Map CadQuery constructs to OpenSCAD equivalents:
   - .box() → cube()
   - .circle().extrude() → cylinder()
   - .cut() → difference()
   - .union() → union()
   - .fillet() → minkowski() with sphere() or manual chamfer geometry
   - .shell() → difference() with offset inner shape
   - .revolve() → rotate_extrude()
   - Workplane offsets → translate()
   - Selectors → manual positioning
3. Preserve all parametric variables with the same names.
4. Set $fn = 64 globally.
5. Use modules for CadQuery functions.
6. Note: CadQuery .fillet() has no direct OpenSCAD equivalent — approximate with minkowski() or document the limitation.
```

---

## 4. Self-Evaluation of Printability

Use as a follow-up prompt after code generation to have the LLM review its own output.

### Template: Full Printability Review

```
Review the following {openscad|cadquery} code for FDM 3D printability issues.

```
{paste code}
```

Check for ALL of the following and report issues found:

## Geometry Checks
- [ ] All geometry is manifold (watertight solid)
- [ ] No zero-thickness walls or features
- [ ] Boolean operations have epsilon overlap (0.01mm)
- [ ] No self-intersecting geometry

## Printability Checks
- [ ] Minimum wall thickness ≥ 1.2mm everywhere
- [ ] Minimum feature size ≥ 0.8mm
- [ ] No unsupported overhangs > 45° from vertical
- [ ] Flat bottom surface for bed adhesion
- [ ] No bridging spans > 30mm without support
- [ ] Mating surfaces have ≥ 0.2mm tolerance

## Code Quality Checks
- [ ] All dimensions defined as variables at top
- [ ] Descriptive variable names
- [ ] Comment header with print settings
- [ ] Print orientation documented
- [ ] Code compiles without errors

For each issue found, describe the problem and provide the specific code fix.
Output the corrected code at the end if any changes are needed.
```

### Template: Quick Check

```
Is this code FDM printable without supports? If not, what specific geometry needs to change?

```
{paste code}
```

Reply with either "PRINTABLE" or a bullet list of issues with line numbers and fixes.
```

### Template: Material-Specific Review

```
Review this model for printing in {PLA|PETG|ABS|TPU}:

```
{paste code}
```

Consider material-specific constraints:
- PLA: brittle, low heat resistance, good detail
- PETG: more flexible, better layer adhesion, stringing issues
- ABS: warping concerns, needs enclosure, good for snap fits
- TPU: flexible, snap-fits work differently, minimum 2mm walls

Suggest any design changes needed for this specific material.
```

---

## 5. Multi-Step Complex Model Workflow

For complex models, break generation into stages.

### Stage 1: Design Plan

```
I need a {model description} for 3D printing. Before writing any code, create a design plan:

1. List all major components/features
2. Define the parametric variables needed (with suggested default values in mm)
3. Describe the build order (what to create first, boolean operation sequence)
4. Note any printability concerns and how you'll address them
5. Specify the print orientation

Output the plan as numbered steps. Do NOT write code yet.
```

### Stage 2: Generate from Plan

```
Based on this design plan, now write the complete {OpenSCAD|CadQuery} code:

{paste the plan from Stage 1}

Follow all standard rules (parametric variables, manifold geometry, FDM printable, etc.).
```

### Stage 3: Review and Refine

```
Review and refine this code. Apply the printability checklist, then make these specific changes:
- {list changes}

Output the final complete code.
```

---

## Usage Tips

- **Copy-paste ready**: Each template has `{placeholders}` — replace them with actual content
- **Chain prompts**: Use Stage 1 → 2 → 3 for complex models; use Error Recovery when any stage fails
- **Model choice**: GPT-4 and Claude handle multi-turn refinement well; smaller models may lose context
- **Keep conversation short**: After 3–4 refinement rounds, start fresh with accumulated learnings baked into the prompt
