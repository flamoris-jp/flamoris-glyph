# FLAMORIS Glyph architecture (design draft)

## Current implementation

Python CLI parses plain lyric text or SRT and exports a deterministic Unicode character **inventory** JSON. This is groundwork only.

## Product invariants

- **Occurrence-driven:** each rendered lyric character instance may reference a unique glyph variant. Unicode identity does not dictate shape identity.
- **Song Style DNA:** shared palette, stroke grammar (tome/hane/harai), texture and proportions create minimum visual consistency while allowing variation.
- **Cross-platform:** core and CLI must run on Linux and Windows. Windows KineticTypo and eventual Linux KineticTypo via Kachinco CLI use the same export format.
- **Renderer independent:** Glyph produces vector data; KineticTypo drives animations and frames.
- **Optional AI:** generating with an AI backend may require a remote runtime, but offline inventory and reading already exported vectors must not.

## Planned pipeline

1. Lyrics/SRT -> occurrence sequence (including cue/time linkage) + deduplicated character inventory for caching.
2. Song Style DNA -> reference glyphs and shared design constraints.
3. Each occurrence -> glyph instance/variant, optionally reusing a previous design.
4. Stroke skeleton / designer controls / optional AI-assisted source -> outline creation.
5. SVG validation -> relative-path vector assets + versioned JSON manifest.
6. KineticTypo loaders on Windows and Linux consume the identical manifest and vector assets.

## Planned portable manifest sketch (NOT implemented)

```json
{
  "schema_version": 2,
  "song_id": "red-shoes-tango",
  "style_profile": "styles/song.json",
  "occurrences": [
    {
      "occurrence_id": "cue0001-char0001",
      "character": "赤",
      "glyph_variant_id": "u008D64-v01",
      "asset": "glyphs/u008D64-v01.svg",
      "cue_id": "cue0001"
    },
    {
      "occurrence_id": "cue0002-char0001",
      "character": "赤",
      "glyph_variant_id": "u008D64-v02",
      "asset": "glyphs/u008D64-v02.svg",
      "cue_id": "cue0002"
    }
  ]
}
```

**Contract rules:** UTF-8 JSON; POSIX-style relative asset paths regardless of host OS; explicit schema version; stable occurrence and variant IDs; normalized SVG coordinate/viewBox conventions; no host absolute paths, no required font installation or platform-specific graphics APIs in asset format.

## Validation and compatibility targets

- Unit tests on Windows and Linux for Unicode and SRT parsing, deterministic manifests, and path serialization.
- Golden-file tests for SVG and manifest compatibility once vector output exists.
- Round-trip validation in both KineticTypo adapters when built.
- Document limitations of complex Unicode grapheme clusters (combining marks, emoji) before claiming full coverage.

Do not describe planned formats, endpoints, MCP tools, or Linux rendering as shipped.
