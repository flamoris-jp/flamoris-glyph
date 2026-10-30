# Portable bundle contract — schema 2

This is the **implemented offline export**, not a promise that existing players already support it.

## Files and coordinates

- `manifest.json`: UTF-8 JSON with LF; `schema_version: 2`, `kind: "flamoris-glyph-bundle"`.
- `glyphs/g<24 lowercase hex>.svg`: ASCII filename, forward-slash relative path.
- SVG `viewBox="0 0 1000 1000"`, Y-down. Only direct filled `path` children, each with ID `strokeNNN`.
- Each contour is closed. Allowed geometry is numeric M/L/Q/C/H/V/Z, with no transform, style, text, external links or effects.
- The center anchor is [500,500]. Bounds describe actual outline extents; advance is a layout hint, not kerning or a baseline guarantee.
- Each glyph is centered individually. Latin punctuation and mixed-script typographic spacing need player/designer review; this MVP is not a general text shaping engine.
- Unsupported versions or malformed/missing geometry must fail visibly. Never silently replace characters.

## Manifest fields

| Field | Contract |
|---|---|
| song / title | Work labels; title can be empty |
| generator | name, version, fonttools dependency version |
| seed / reuse | signed 64-bit integer; occurrence or character |
| style | Embedded schema 1 Style DNA; no remote reference |
| source | kind, SHA-256, license_note; no machine path or source font |
| cues | id, original normalized text, start_ms / end_ms (both null or nonnegative integer interval) |
| occurrences | occurrence_id, character, cue_id, line, column, glyph_variant_id |
| glyphs | Unique generated variants; every variant is referenced by an occurrence |
| inventory | Character frequency/title membership for planning; not playback authority |

Optional title text is appended as one untimed cue. Plain text also has untimed cues. Both null times mean placement/timing must be assigned by the player. SRT timings are cue-wide; this format does not fabricate per-letter phoneme timing.

Example occurrence:

```json
{
  "occurrence_id": "cue0001-char0001",
  "character": "赤",
  "cue_id": "cue0001",
  "line": 1,
  "column": 1,
  "glyph_variant_id": "g0123456789abcdef01234567"
}
```

Each variant contains:
- `variant_id`, `character`, `asset`, SVG `sha256`
- resolved `parameters` (scale_x, scale_y, slant, bend, stroke_width, fill)
- `metrics` (view_box, bounds [xmin,ymin,xmax,ymax], anchor, advance)
- `stroke_model`: authored or outline
- `strokes`: ordered element_id, source_id, terminal

Authored stroke terminals are tome/hane/harai. Font outline variants have one path with all contours and null terminal; contours are not falsely labeled as handwriting strokes. Whole-glyph transforms work for both; meaningful stroke animation is available only for authored stroke geometry.

## Consumer acceptance

Consumers should call the equivalent of `validate_bundle` before import: verify paths stay inside the bundle, reject symlinks/active XML, check SHA-256 and the restricted SVG subset, then check cue/occurrence/variant/stroke/metrics links. Limits are documented in [architecture](architecture.md). Paths are relative to the manifest, never the current working directory.

Read cue source text and 1-based line/column to preserve spaces and multiline structure. Do not pack visible glyphs together and lose lyric spacing. Original timing and IDs must survive the import.

Consumers own animation and project mutation, including undo. The bundle is an immutable shape asset. Regeneration should create a new directory and require explicit rebinding in the consumer.

Version 1 remains the old inventory-only CLI/API output. It is not a bundle and must not be interpreted as one. No automatic v1 geometry migration is possible.

## Cross-platform fixture

`examples/demo.srt` + `examples/skeletons.json` + `examples/tango.style.json`, seed 42, produce nine separate glyph assets in occurrence mode, three in character reuse mode. `tests/golden/skeleton-assets.json` records generated SVG hashes for exact cross-platform geometry checks. `examples/demo-preview.svg` is the generated visual review sheet.

The deterministic fixture uses original authored shapes, so it does not depend on system font availability or third-party font licensing. Actual Windows/Linux KineticTypo rendering acceptance will be recorded when their adapters exist.
