# FLAMORIS Glyph

Song-specific vector glyph preparation for KineticTypo.

**Status:** development (bootstrap, not a production glyph generator)

## Repository identity / 何者か

FLAMORIS Glyph extracts the distinct characters needed for a song from lyric text or SRT and prepares a deterministic manifest for a future style-driven vector glyph pipeline.

### Owns / 責任範囲
- Lyrics/SRT ingestion and unique character inventory
- Song-scoped glyph manifest and stable character IDs
- Future stroke skeleton, vector glyph generation, and export contracts

### Does not own / 対象外
- KineticTypo animation timelines and video rendering
- AI model hosting, runtime lifecycle, or deployment (handled by existing FLAMORIS services)

## Quick start

Requires Python 3.11+; runtime uses only the standard library, but the package must be installed first.

```bash
python -m pip install -e .
python -m flamoris_glyph.cli lyrics.srt --song "Red Shoes Tango" --out manifest.json
python -m unittest discover -s tests -v
```

The manifest contains per-character IDs, frequency counts, and source metadata. **No actual SVG artwork is generated yet.** The next milestone will build vector strokes and style-preserving glyph exports.

## Design rules

1. Generate only characters present in a song's lyrics by default. Optional title text is explicitly included with `--title`.
2. Deduplicate by Unicode character, preserving first-seen order. Keep usage frequency.
3. Keep lyrics, glyph identity, style profile, and animation timing separate.
4. Produce deterministic, tool-friendly JSON for future MCP and KineticTypo adapters.
5. Do not require proprietary font files to be distributed.

## Architecture

```text
Lyrics / SRT -> Unicode inventory -> Song manifest
                                       |
                            future stroke skeleton
                                       |
                            future style / SVG export
                                       |
                           future KineticTypo adapter
```

The SVG glyph and MCP endpoints are **planned**, not part of this bootstrap.

## FLAMORIS

FLAMORIS is open-source software for creative work and AI-native production. Commercial use is welcome. See [LICENSE](LICENSE) for code licensing and applicable separate licenses for media/models.
