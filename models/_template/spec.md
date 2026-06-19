# <Model name>

## Request (plain language)

<What was asked for, in the user's words. Link reference images in refs/ if any.>

## Hard dimensional requirements

| Dimension | Value | Tolerance | Where enforced |
|---|---|---|---|
| Width (X) | 40.0 mm | ±0.5 | rounded_box size |
| Depth (Y) | 30.0 mm | ±0.5 | rounded_box size |
| Height (Z) | 20.0 mm | ±0.5 | rounded_box size |

## Look & feel

- <Bullet list of the qualitative goals — what should the preview look like?>

## Print notes

- Orientation: flat base on bed. Material: PLA. Supports: none expected.

## Reproduce / vary

```
.venv\Scripts\python -m scripts.build_model models\<name>
```

Change `params.json` and rebuild; same seed + params = same STL.
