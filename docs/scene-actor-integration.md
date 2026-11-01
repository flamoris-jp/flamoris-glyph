# Glyph scene actor integration — scope and dependencies

Updated 2026-11-01 for [Glyph #3](https://github.com/flamoris-jp/flamoris-glyph/issues/3), [Kachinco #124](https://github.com/flamoris-jp/flamoris-kachinco/issues/124), and [CG #8](https://github.com/flamoris-jp/flamoris-CG/issues/8). Contract/design backlog only; no new adapter implementation or bundle version.

## Current basis and prior work

Glyph's [schema-2 bundle](bundle-v2.md) is the immutable shape authority. Its generation and validation do not depend on CG, a new engine or Cinema.

Cinema already implemented a read-only actor snapshot and tested a fixed 赤 fixture. Inspect [the historical contract and evidence](https://github.com/flamoris-jp/flamoris-cinema/blob/main/docs/glyph-actors.md) before designing another. Cinema is paused. Its consumer-specific asset and Scene/Take versions are not automatically Glyph's export contract or CG's format. No code or evidence moves in this reconciliation.

CG is a Blender laboratory; its Glyph ingestion is not implemented. KineticTypo bundle import is a separate consumer path; see [Kachinco's guide and acceptance limits](https://github.com/flamoris-jp/flamoris-kachinco/blob/main/docs/kinetai-linux-and-glyph.md). It does not depend on this actor integration.

## Responsibility and minimum contract

| Item | Glyph / asset-side basis | CG / consumer agreement |
| --- | --- | --- |
| Origin/anchor/pivot | viewBox 0..1000, Y-down, anchor [500,500], bounds and advance | Explicit axes/unit conversion, placement and chosen pivot; never infer a foot rig |
| Filled shape and holes | Restricted closed-path SVG and fill semantics; preserve visible geometry | Curve normalization/tessellation/depth; reject unsupported shapes instead of substitution |
| Stroke/occurrence identity | occurrence → variant → SVG, element IDs within bundle | Object/component mapping retains source IDs; runtime identity is separate |
| Integrity/provenance | Bundle validation, source/SVG checksum, license, generator version | Immutable snapshot/reference policy, converter version and transformed asset integrity |
| Timing | Cue milliseconds or untimed cue; no fabricated per-letter timing | Clip duration/placement and local motion clock, with explicit conversions |
| Collision simplification | Source outline remains unchanged | Optional derived proxy and accuracy limits are future CG physics research |
| Portability/bounds | Same validated local artifact on Windows/Linux | Versioned subset, bounded geometry and rejection behavior; hardware acceptance separate |

Glyph does not gain physics, camera/render control or project editing. Reuse Glyph's validation/shape API; do not fork its letterform algorithms.

## Replacing the old blanket blocker

The original #3 said “Blocked on scene schema agreement.” Separate this into:

1. **Can be specified from existing Glyph data:** read-only validation, identity, anchor/coordinates, fill/hole rules, checksums/provenance and portable fixture. No engine-wide schema is needed.
2. **Needs agreement with CG #8 before implementation:** consuming subset, coordinate/unit/pivot conversion, component/depth representation, timing/output boundary and rejection rules. Agree what one real actor needs. Collision proxies stay a later research item.

A universal scene schema, new repository and Cinema's future project schema are not dependencies. Do not silently feed Cinema Scene/Take into CG's Z-up, 1-based lab JSON.

## Acceptance still open

- [ ] Record the minimum versioned Glyph/CG contract and unsupported cases after comparing Cinema's existing adapter.
- [ ] Use a font-free original 赤 fixture with hashes, occurrence/stroke IDs, anchor/scale and hole/fill checks; this does not claim a CG fixture exists yet.
- [ ] Verify read-only behavior, invalid-input rejection and Windows/Linux portability without changing bundle schema 2 or existing CLI behavior.
- [ ] Record independent CG/Blender acceptance when implemented. Prior Cinema acceptance and Python CI do not satisfy it.
- [ ] Keep collision proxies/acting and full scene schemas outside this minimum contract.

See [CG's classification](https://github.com/flamoris-jp/flamoris-CG/blob/main/docs/scene-engine-scope.md) for retained research and removed prerequisites. #3 stays open; this update neither declares the old plan abandoned nor restarts Cinema.
