# FLAMORIS Glyph

AI-assisted song-specific expressive vector lettering for FLAMORIS.

**Status:** development. Current code only inventories characters from lyrics/SRT; vector generation and player integration are planned.

## Identity / 何者か

FLAMORIS Glyph creates expressive vector glyphs for particular **occurrences** of characters in a song. The same Unicode character may take a different shape each time it appears. A shared **Song Style DNA** provides visual consistency (palette, stroke grammar, materials, proportions) without demanding identical glyph shapes.

The inventory of unique characters is an optimization and planning input, **not** a rule that each character must have only one glyph.

## Responsibility
- Lyric / SRT parsing, character inventory, and future occurrence mapping
- Song style profiles and controlled glyph variation
- Future vector path generation, versioned portable export, and integration contracts

**Out of scope:** KineticTypo animation timeline and rendering; AI hosting and runtime management.

## Cross-platform requirement

**Linux and Windows are both first-class targets.** The core library and CLI must work on both without OS-specific path assumptions, Windows-only UI dependencies, or mandatory GPU availability. Future Windows KineticTypo and Linux KineticTypo/Kachinco CLI must consume the **same exported asset contract**.

- Python 3.11+ for initial core; use `pathlib`, UTF-8, portable dependencies.
- Versioned JSON manifests plus SVG vector assets; paths are relative and use forward slashes in manifests.
- Style and glyph generation must be independent of the renderer and animation timeline.
- AI/GPU backends are optional adapters, not required for reading or rendering previously generated assets.
- CI must test Windows and Linux; platform-specific integration tests to follow as adapters are implemented.

## Quick start

```bash
python -m pip install -e .
python -m flamoris_glyph.cli lyrics.srt --song "Red Shoes Tango" --out manifest.json
python -m unittest discover -s tests -v
```

The current CLI exports a character inventory, not SVG artwork or per-occurrence variants.

## Design principles

1. Only generate what the song actually uses; allow optional title characters.
2. Identical characters **may** have different shapes at different lyric occurrences.
3. Song Style DNA anchors coherent visual identity, with room for emotional and musical variation.
4. Keep character identity, occurrence identity, style, vector geometry, and timing separate.
5. Export deterministic, versioned, OS-neutral assets; no installed font should be required at playback.
6. KineticTypo owns motion and rendering; Glyph owns shape generation and assets.

See [architecture](docs/architecture.md).

## FLAMORIS

FLAMORIS is open-source creative software. Commercial use is welcome. See [LICENSE](LICENSE) for source licensing; models and media may have separate licenses.
