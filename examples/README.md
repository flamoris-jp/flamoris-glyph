# Offline design experiment

`demo.srt` is a synthetic timing fixture, **not** the real song or its lyrics/timing.
`skeletons.json` contains original, simplified experimental centerline drawings
for 赤・い・靴・永, authored for this repository under Apache-2.0. They are
demonstration lettering, not a font, a comprehensive dataset, or a reference for
correct stroke order. Review readability before using in a production MV.

```bash
flamoris-glyph generate examples/demo.srt --song "Red Shoes experiment" --skeletons examples/skeletons.json --style examples/tango.style.json --seed 42 --out output-demo
flamoris-glyph validate output-demo
flamoris-glyph preview output-demo --out demo-preview.svg
```

Compare the three instances of 赤 in their individual SVGs. They share palette,
stroke grammar and variation limits but have different outline coordinates.
Use `--reuse character` to intentionally reuse the same character's variant.
Set `variation` to `0` to disable occurrence-dependent variation including color.

For arbitrary Japanese text use a static Japanese TTF/OTF you are allowed to
convert to outlined artwork. No third-party font or stroke dataset is bundled.
