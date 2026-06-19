# Organ-Pipe Coral Growth

## Request (plain language)

An "organ skeleton / coral growth" sculpture: a cluster of organic
vertical pipes (like *Tubipora musica*, organ pipe coral, crossed with
church-organ pipes) rising from a solid shared base. The overall
silhouette must hit **exact dimensions**: a specific base diameter that
narrows into a specific top diameter at a specific height, following a
concave taper. Interior growth is organic/random but reproducible.

## Hard dimensional requirements

| Dimension | Value | Where enforced |
|---|---|---|
| Base diameter | 90.0 mm | revolved envelope at z=0 (base rim) |
| Total height | 140.0 mm | tallest pipes trimmed flat by the envelope top |
| Top diameter | 36.0 mm | envelope radius at z=140 |
| Silhouette curve | concave, `profile_curve = 1.2` | `taper_profile()` |

Everything outside the envelope is shaved off, so these numbers are
exact regardless of the random growth inside.

## Look & feel

- ~38 pipes, thicker near the center, thinner at the rim
- Taller pipes in the middle, shorter at the edges (organ look)
- Pipes wander slightly (~2 mm) as they rise; blended where they touch
- **Open mouths** at every pipe tip (carved in ~1.6 mm walls)
- Gentle noise displacement so surfaces read as grown, not machined
- Solid 9 mm base disk fusing all pipes together

## Print notes

- Print as oriented (flat base on bed). Pipes are near-vertical; only
  mouth rims overhang and they are small. Tree supports optional.
- PLA, 0.2 mm layers, 2–3 perimeters, 10–15% infill.

## Reproduce / vary

```
.venv\Scripts\python -m scripts.build_model models\organ_coral
```

Change `params.json` (different seed = different growth, same
dimensions) and rebuild. Dimensions only move if you change the
envelope numbers.
