# Style DNA and skeleton inputs (schema 1)

## Style DNA

All supported fields are in `examples/tango.style.json`. `schema_version: 1` is required; fields otherwise default to `StyleDNA()`. Unknown fields and nonfinite numbers fail.

| Field | Range / meaning |
|---|---|
| name | 1..100 character label |
| palette | 1..8 colors, each #RRGGBB; only these colors may appear |
| variation | 0..1; maximum controlled variation, not an aesthetic score |
| width / height | 0.85..1.05 base scaling about [500,500] |
| slant | -0.1..0.1 base shear |
| stroke_width | 8..80 design units; authored skeleton source only |
| hane_length | 0..80 design units; authored hane only, currently up-left |
| harai_taper | 0.02..0.5 final/base radius ratio for hane/harai |

Occurrence variation adds ±7.5% width, ±5.5% height, ±0.055 shear, ±18 units sine bend, and ±12% skeleton width at maximum variation. Every term scales by `variation`; color is sampled only from the palette. The font backend changes outline coordinates, not stroke thickness or terminal semantics. Bounds validation rejects overflow rather than clipping.

## Explicit skeletons

```json
{
  "schema_version": 1,
  "license_note": "Original design, Apache-2.0",
  "glyphs": {
    "一": [
      {"id": "s1", "points": [[180, 500], [820, 500]], "terminal": "tome"}
    ]
  }
}
```

Coordinates are Y-down in a 1000×1000 design box; centerline coordinates are bounded to 120..880 to reserve room for outlines, terminals and variation.
Two points form a line; three form a quadratic (start, control, end). 1..64 strokes per single-codepoint glyph, up to 4096 source glyphs. Only needed glyphs are rendered. IDs are unique ASCII alphanumeric/hyphen tokens. Empty or degenerate strokes fail.

This format does not infer stroke type from arbitrary SVG/font contours. Semantic tags are authored information. The compiler produces one closed filled path per stroke and retains the authored ID and terminal in the manifest.

Licensing/provenance is required for both skeleton data and supplied fonts. It is recorded without an absolute filesystem path. The source itself is not copied into the bundle. Changes to source content change the variant identity.
