# CadQuery LLM Generation Tips

Practical advice for getting better CadQuery output from LLMs — common pitfalls, API gotchas, and debugging strategies.

---

## Common LLM Mistakes and Prompt Fixes

### 1. Using CadQuery 1.x syntax

**Problem**: LLMs trained on older data generate deprecated `CQ()`, `Workplane.make()`, or `exportShape()` calls.

**Fix**: Add to your prompt:
```
Use CadQuery 2.x syntax ONLY. Use cq.Workplane(), not CQ().
Export with cq.exporters.export(result, 'output.stl').
```

### 2. Forgetting the export line

**Problem**: LLM builds the model but never exports it, so running the script produces no file.

**Fix**:
```
The script must end with: cq.exporters.export(result, 'output.stl')
```

### 3. Broken chaining — calling methods on the wrong type

**Problem**: LLM calls a Workplane method on a Shape object or vice versa, producing `AttributeError`.

**Fix**: Add to your prompt:
```
Keep the CadQuery workplane chain intact. Do not break the chain by calling .val() mid-build.
Only call .val() at the very end if needed.
```

### 4. Fillet / chamfer kernel errors

**Problem**: `fillet()` or `chamfer()` crashes with `StdFail_NotDone` when the radius is too large for the edge or creates conflicting geometry.

**Fix**:
```
Use conservative fillet radii (no more than half the smallest adjacent face dimension).
Wrap .fillet() in try/except during development. Apply fillets LAST in the build chain.
```

### 5. Incorrect selector strings

**Problem**: LLMs invent selector syntax like `edges("top")` or `faces("front")` which don't exist.

**Fix**: Include a cheat sheet in the prompt:
```
CadQuery selector syntax:
  Axis parallel:  "|X", "|Y", "|Z"
  Axis normal:    "#X", "#Y", "#Z"  
  Direction max:  ">X", ">Y", ">Z"
  Direction min:  "<X", "<Y", "<Z"
  Combine with .filter() or use NearestToPointSelector for complex selections.
```

### 6. Non-solid geometry (shells, surfaces, wires)

**Problem**: The LLM creates 2D sketches or wire frames but forgets to extrude them into solids.

**Fix**:
```
Every sketch must be extruded (.extrude()), lofted (.loft()), or revolved (.revolve()) into a solid.
The final result must be a solid body, not a wire or face.
```

---

## CadQuery Selector Cheat Sheet

### Axis Selectors
| Selector | Meaning                           | Example Use                    |
| -------- | --------------------------------- | ------------------------------ |
| `">Z"`   | Face/edge with highest Z          | Top face                       |
| `"<Z"`   | Face/edge with lowest Z           | Bottom face                    |
| `"|Z"`   | Edges parallel to Z axis          | Vertical edges for filleting   |
| `"#Z"`   | Faces with normal along Z         | Horizontal faces               |
| `">X"`   | Rightmost face (max X)            | Side face selection             |

### Combining Selectors
```python
# Select top edges only
.edges(">Z")

# Select vertical edges on the top face
.faces(">Z").edges("|Z")

# Select all edges except bottom
.edges("not <Z")
```

### Tag and Select Pattern
For complex models, tag intermediate states:
```python
result = (
    cq.Workplane("XY")
    .box(10, 10, 10)
    .tag("base_box")
    .faces(">Z")
    .circle(3)
    .extrude(5)
    # Now go back to base_box edges
    .workplaneFromTagged("base_box")
    .edges("|Z")
    .fillet(1)
)
```

---

## Fillet and Chamfer Strategies

### Apply Fillets Last
Fillets can fail if subsequent operations invalidate the geometry. Apply them as the final step:

```python
# GOOD: build geometry, then fillet
result = (
    cq.Workplane("XY")
    .box(40, 30, 20)
    .faces(">Z").circle(5).cutThruAll()
    .edges("|Z").fillet(2)  # last operation
)

# BAD: fillet then cut — may produce invalid geometry
result = (
    cq.Workplane("XY")
    .box(40, 30, 20)
    .edges("|Z").fillet(2)
    .faces(">Z").circle(5).cutThruAll()  # may crash
)
```

### Safe Fillet Pattern
```python
try:
    result = result.edges("|Z").fillet(radius)
except Exception:
    # Fall back to smaller radius or skip
    try:
        result = result.edges("|Z").fillet(radius * 0.5)
    except Exception:
        pass  # Skip filleting
```

### Chamfer Instead of Fillet
When fillets cause kernel errors, chamfers are more reliable:
```python
result = result.edges("|Z").chamfer(1.0)  # usually more stable than fillet
```

---

## Shell() Tips

### Basic Shelling
```python
# Shell with uniform wall thickness, opening on top
result = (
    cq.Workplane("XY")
    .box(60, 40, 30)
    .faces(">Z")
    .shell(-2.0)  # negative = inward, 2mm wall
)
```

### Shell with Multiple Openings
```python
# Open on top and one side
result = (
    cq.Workplane("XY")
    .box(60, 40, 30)
    .faces(">Z or >X")
    .shell(-2.0)
)
```

### Shell Pitfalls
- Shell with fillets: fillet the **outside** before shelling, not after
- Shell thickness must be less than half the smallest dimension
- Complex geometry may cause shell failures — simplify first

---

## Performance Considerations

### OCCT Kernel is Single-Threaded
CadQuery uses the OpenCASCADE kernel, which is single-threaded. Complex operations on high-resolution geometry can be slow.

### Tips for Faster Scripts
1. **Minimize boolean operations**: Union/cut operations are expensive. Combine geometry with `.extrude(combine=True)` where possible.
2. **Avoid unnecessary fillets on hidden edges**: Only fillet edges that matter functionally or aesthetically.
3. **Use `.cutThruAll()` instead of `.cutBlind(huge_number)`**: The kernel optimizes through-cuts.
4. **Batch features with `.pushPoints()`**: More efficient than individual loops.

---

## Debugging Workflow

### 1. Run and Check Errors
```bash
python model.py
# Check for Python tracebacks
```

### 2. Visualize Intermediate Steps
```python
# Export intermediate result for debugging
cq.exporters.export(intermediate_result, 'debug_step.stl')
```

### 3. Common Error Messages

| Error                                    | Likely Cause                          | Fix                                    |
| ---------------------------------------- | ------------------------------------- | -------------------------------------- |
| `StdFail_NotDone`                        | Fillet/chamfer radius too large       | Reduce radius or skip                 |
| `BRepAlgoAPI_... not done`               | Boolean op on invalid geometry        | Check for zero-thickness or open shells |
| `AttributeError: 'Workplane' has no...`  | Wrong method for object type          | Check CadQuery 2.x API docs           |
| `Wire is not closed`                     | Sketch has gaps                       | Ensure sketch is a closed profile      |
| `Compound object has no solid`           | Extrude/loft produced surface not solid | Check sketch is closed and planar     |

### 4. Feed Errors Back to LLM
```
The following CadQuery code produced this error:

[paste full traceback]

Fix the code to resolve this error. Output only the corrected Python code.
Keep the same parametric structure and variable names.
```
