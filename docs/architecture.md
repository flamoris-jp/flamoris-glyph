# Glyph pipeline (design draft)

## Current
Lyrics text or SRT -> unique Unicode characters -> deterministic song manifest (v1).

## Planned
1. Glyph skeleton and stroke metadata (tome / hane / harai / intersection).
2. Song-level style profile (e.g., showa-retro, cosmic) + controlled variations.
3. Vector outlines and SVG files with predictable viewBox and transparent background.
4. Optional AI-assisted design references; validate glyph legibility and path quality.
5. KineticTypo integration using stable glyph IDs and separate motion timelines.

## Export contract (future)
- Per-character vector files indexed by codepoint and variant.
- Manifest includes canonical character, style profile, output paths, version, and optional stroke groups.
- Rendering and animation remain the responsibility of KineticTypo.
- Fallback behavior must be explicit for missing/unsupported glyphs.

Do not treat planned endpoints as implemented APIs.
