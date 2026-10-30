# Architecture — offline MVP 0.2

## Product invariants

1. **出現箇所が生成単位。** Unicode文字の一致で字形の一致を強制しない。
2. **Style DNAが共通の美意識を制約。** 同じpalette、比率と変形上限、ストローク幅・終端規則を共有する。制約内の変化を許す。
3. **必要な文字だけ。** inventoryは一覧・頻度・計画用。生成数の制限ではない。
4. **Windows / Linuxで同じ資産。** 形は閉じたパスとして確定し、再生にフォントも生成環境も要求しない。
5. **領域を分離。** Glyphが造形、playerが配置・アニメーション・描画、生成基盤がAI実行を所有する。

## Implemented data flow

- `lyrics.py` → cue sequence + visible occurrences
- `style.py` → validated Style DNA + seed-derived bounded parameters
- `geometry.py` → source outlines + continuous coordinate deformation
- `bundle.py` → closed-path SVG + schema 2 manifest + integrity checks
- `cli.py` → inventory / generate / validate / preview

Core has no network, UI, service configuration, model host, subprocess, or platform graphics API.
The only runtime dependency is fontTools. Its documented TTFont / Pen interfaces supply outline decomposition and SVG path operations:
[TTFont](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html),
[SVGPathPen](https://fonttools.readthedocs.io/en/latest/pens/svgPathPen.html).

### Cue / occurrence identity

- Cue ID derives from physical text line number or SRT block order, not the optional SRT sequence label.
- Each non-space visible NFC codepoint gets a cue-scoped occurrence ID and 1-based line/column.
- Source line breaks and spaces remain in cue text for downstream layout.
- SRT start/end are cue-level milliseconds; overlaps and source order are preserved.
- Optional title text is appended as one untimed cue after lyrics.
- IDs are deterministic for unchanged input, not durable text-edit tracking identities.

### Sources and actual geometry

**Static TTF/OTF:** Resolve Unicode through the font cmap. Decompose contours/components through fontTools; flip Y, center and uniformly fit the outline into a common design box. Keep contour holes and advance metadata. Apply bounded width/height/shear/bend to actual path coordinates. This is an outline deformation MVP, not AI-designed new stroke grammar. Font stroke order and semantics are unknown. No character-specific hardcoded font is installed or selected.

**Authored skeleton JSON:** Each stroke has a line/quadratic numeric centerline and explicit tome/hane/harai tag. Sample the centerline, compute variable-width normals, add a controlled up-left hook for hane, taper hane/harai, and close a polygon outline. IDs remain associated with individual SVG paths. Hooks currently use one experimental direction; no automatic calligraphic classification is claimed. Fine joins/intersections and complex brushes remain a design limitation.

**Deformation:** One smooth coordinate map per character acts on every stroke/contour, avoiding unrelated distortions between components. SHA-256-derived parameter samples are stable across processes. Inputs/geometry are bounded; generated coordinates are checked against the canvas. The current limits preserve broad structure, but human readability approval is still required.

### Style and reuse

`StyleDNA` is immutable and strictly validates its supported fields. Unknown options fail rather than silently pretending to implement materials, textures, or ornaments.

Character reuse selects the same variant deliberately; occurrence mode keeps instances individually addressable. Zero variation disables shape and palette sampling. Variant identity includes source provenance, style, seed, key, and generator version. SVG content gets a separate SHA-256. Dependency version is recorded; byte reproducibility requires the same generator/dependency versions. Output has no timestamps or machine paths.

## Publication and reader boundary

Generate and validate in memory, write into a temporary sibling, validate complete files, then rename into a new output directory. Never merge into an existing bundle. Missing glyphs fail before publishing an incomplete song.

Reader validation checks format version, cue/occurrence relationships, glyph identity links, parameters, palette, metrics, stroke IDs, relative paths, file hashes and the closed path-only SVG subset. Symlink assets/directories, path escapes, XML declarations/entities, external resources, active SVG content, open/out-of-bounds paths and unknown schema versions are rejected. Hashes detect inconsistency, not authorship/authenticity.

CLI input limits: 2 MB text/style/skeleton JSON, 50 MB font. Bundle bounds: 5,000 visible occurrences, 64 strokes per glyph, 2 MB per SVG, 64 MB SVG total, 20 MB manifest. Preview is limited to 96 occurrences. This is a local trusted-workstation tool, not a sandbox for hostile font parsing.

## Integration direction

Existing ecosystem sources inspected:
- Organization map: `flamoris-jp/.github/profile/README.md`
- Commons: README and desktop ecosystem map
- MCP Core: current README / shared authority boundary

Commons does not currently provide a Python glyph engine. MCP Core is a .NET host/transport package and does not belong in the geometry core. No infrastructure is copied into this repository. When an MCP surface is added it must call this Python API through an explicit host boundary or an appropriate shared adapter, preserving the same validation and asset authority.

Future player flow:
1. Validate and import one immutable bundle.
2. Resolve occurrence → variant → SVG through relative paths.
3. Use cue time / source line / column for initial placement and timing policy.
4. Animate whole glyph or authored stroke element IDs in the player's existing project/history.
5. Keep Glyph's shape data and the player's motion data independent.

No KineticTypo/Kachinco repository is modified by this MVP. Both Windows and future Linux players must validate the same artifact; the existing players are not claimed to understand it yet.

## Next phases (not implemented)

1. Windows player import + explicit fixture acceptance; future Linux renderer uses same fixture.
2. Designer-approved style reference glyphs, per-occurrence intensity/section controls, manual variant assignment.
3. Optional AI style proposal/source adapter; host jobs/models in the existing generation authority.
4. Better brush joins, directional terminal grammar, radical structure and richer stroke controls.
5. Grapheme/shaping/vertical-layout support after defining a versioned contract.

## Verification

Cross-platform Python 3.11 / 3.12 CI runs the full unit/integration suite and a font-free demo generation/validation. Original synthetic font fixtures exercise font extraction and composite outlines without redistributing a third-party font. A fixed asset hash fixture checks portable skeleton SVG output. Player round trips and aesthetic evaluation remain separate acceptance work.

