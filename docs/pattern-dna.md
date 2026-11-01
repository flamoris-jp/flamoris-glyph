# Pattern DNA 1 — bounded outline experiment

Status: experimental. Relates to Issue #6 and depends on PR #7's local font
input. This is outline morphology, not a finished lettering style generator.
No animation timeline, GPU renderer, material, AI model, automatic font download
or consumer repository is added.

## Run the comparison

```bash
python -m pip install -e ".[patterns]"
# Original four-character source; no third-party font:
python -m flamoris_glyph.pattern_lab examples/pattern-structure.srt --skeletons examples/pattern-lab-skeletons.json --out output-pattern-lab
# Full original lyric, after supplying a local static Japanese font + license:
python -m flamoris_glyph.pattern_lab examples/glyph-pattern-lab.srt --font-id noto-sans-jp --out output-pattern-lyrics
# Single bundle through the existing CLI:
python -m flamoris_glyph.cli generate examples/pattern-structure.srt --song "Pattern experiment" --skeletons examples/pattern-lab-skeletons.json --style examples/pattern-lab.style.json --pattern heavy-condensed-headline --seed 42 --out output-pattern-single
python -m flamoris_glyph.cli validate output-pattern-single
```

The full lyric is 10 cues / 35 seconds / 88 visible occurrences. The smaller
structure fixture uses the original simplified 赤・い・靴・永 shapes.
`pattern-lab-skeletons.json` explicitly replaces the original demo's hook/taper
terminal tags with flat terminals to isolate outline changes. The original
source and golden assets are unchanged. Its hook generator can produce
self-intersections, which the new pattern path rejects rather than repairing.

The lab writes eight validated schema-2 bundles (baseline + three profiles,
seeds 42/43), two four-column lyric sheets, four per-profile seed sheets, an
enlarged `detail.svg` and `report.json`. Every profile uses the same source and
neutral Style DNA; every result is independently compiled twice and compared.
The whole matrix publishes atomically into a new directory. The lab caps input
at 96 occurrences; ordinary generation retains its 5,000-occurrence limit.

Use `--pattern-file examples/patterns/<profile>.json` instead of `--pattern` to
edit bounded parameters. Python: pass `pattern=PatternDNA.preset(profile)` to
`compile_bundle`. With no pattern, legacy CLI/API behavior and golden hashes
remain unchanged. Style DNA controls source rendering and color; Pattern DNA
is a separate geometry pass.

## Declarative contract

Labels and settings describe visual properties without existing typeface
product names; source provenance stays separate and accurate. Complete JSON
requires `schema_version: 1`, `profile` and all numerical fields below. Unknown
fields/versions, booleans and nonfinite/out-of-range numbers fail.

| Parameter | Bounds | Implemented behavior |
|---|---|---|
| width | 0.65–1.08 | Horizontal affine compression about the common center |
| offset_x / offset_y | -5–14 each | Directional erosion/dilation in design units |
| corner_radius | 0–6 | Rounded morphological opening, with topology checks |
| irregularity | 0–4 | Small coherent sine deformation across the whole outline |
| variation | 0–1 | Bounded hash-derived per-occurrence variation |

| Profile | Prototype behavior | Still missing |
|---|---|---|
| heavy-condensed-headline | Narrow width and heavier strokes | Optical spacing and structural weight redistribution |
| elegant-high-contrast-editorial | Thicker vertical / thinner horizontal outline features | Semantic terminals, new serifs, optical fine-line correction |
| showa-retro-signboard | Mild weight, rounded edges and coherent irregularity | Distinctive sign-painter terminal grammar |

These are initial directions, not complete stylistic equivalence. An outline
does not identify a brush stroke, radical or meaningful terminal. Mixed offset
signs use successive near-one-axis morphology, with at most 0.03 units of
perpendicular numerical footprint per operation. No unimplemented mood fields
are silently accepted.

## Geometry and QA

- Adaptive curve flattening: tolerance 0.35 design units, depth 14, maximum
  16,000 points / 256 contours per path. Curves become polygons. Nonzero fill,
  winding and same-direction overlaps are respected.
- Self-intersecting/degenerate input contours fail. Missing glyphs fail without
  substitution. No implicit repair is applied.
- Candidates must be valid, nonempty, within 0..1000, and retain component/hole
  counts both per source path and over the filled union. Serialized
  four-decimal geometry is rechecked. Filled path area stays within 55–180% of
  the original. Original components/holes retain an overlapping region of at
  least 35% of their area after width normalization.
- On failure, halve morphology strength up to eight times. Width stays
  independent. Record actual strength and all rejection reasons. If no
  candidate passes, retain the original with an explicit rejection warning.
  Source path IDs and terminal metadata survive.
- Brown dots in review sheets mark warned variants. Reduced results are never
  represented as full-strength successes. All variants require visual review.

These checks **do not prove readability, minimum stroke width, near-touching
open-counter quality, or fine-line survival at 1080p**. Review the actual target
size, punctuation, mixed scripts and dense characters manually. As before,
glyphs are individually centered; this is not shaping/kerning. Review sheets
preserve cue columns/spaces. Advance hints are unchanged. Downstream layout and
animation remain consumer-owned.

## Reproducibility and portable boundary

`outline-pattern-1` uses optional Shapely 2.1.2 (BSD-3-Clause); NumPy and GEOS
retain their dependency licenses. The legacy path remains fontTools-only.
Shapely/GEOS versions and flattening tolerance are recorded. Reproduction needs
the same source hash, full Style/Pattern DNA, occurrence key, seed, engine and
dependency versions. Canonical ring ordering and four-decimal output remove
incidental polygon ordering. Windows/Linux CI checks synthetic golden assets
in addition to the untouched existing golden fixture.

Pattern bundles retain schema 2's static filled paths and add optional
`pattern`, `pattern_engine`, and per-glyph `pattern_qa`. Their generator version
is `0.2.0+pattern.1`; variant identity includes full pattern and engine metadata.
The updated reader validates this contract without Shapely at playback time.
The previous reader rejects their identity; consumers must update validation
before accepting this experimental extension. Legacy bundles have no new
fields or identity changes. No existing player compatibility is claimed.

Fonts, source license files, source paths and font bytes are not copied into
bundles. The existing source license note remains provenance. Transforming an
outline does not remove applicable source redistribution conditions.

## Remaining acceptance

See [first result](pattern-lab-report.md) and
[enlarged comparison](../examples/pattern-lab-detail.svg).

No local Japanese font binary was available during this experiment. CI runs
the complete lyric with an explicitly original synthetic diagnostic font:
curves, composites, disconnected marks, counters and separate punctuation.
**Its cmap intentionally maps characters to test shapes. This is structural
test data, never Japanese letterforms or legibility evidence.**

Full-lyric Japanese visual acceptance, 鏡/龍 readability, 1080p fine-line checks
and designed terminal treatments remain open. Supply a local static Japanese
font and its official license to run the full visual matrix. There is no
automatic download or silent substitution.
