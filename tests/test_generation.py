from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from flamoris_glyph import (FontSource, SkeletonSource, StyleDNA, compile_bundle,
                            parse_cues, validate_bundle, write_bundle)
from flamoris_glyph.bundle import validate_svg
from flamoris_glyph.cli import main

ROOT = Path(__file__).resolve().parents[1]


def sample_source():
    return SkeletonSource(json.loads((ROOT / "examples/skeletons.json").read_text(encoding="utf-8")))


def test_font(path):
    """Original synthetic geometry for testing font extraction, never production art."""
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A", "B", "acute", "composite"])
    glyphs = {}
    for name in [".notdef", "A", "B", "acute"]:
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0))
        pen.lineTo((500, 0))
        pen.lineTo((500, 700))
        pen.qCurveTo((200, 800), (100, 700))
        pen.closePath()
        glyphs[name] = pen.glyph()
    pen = TTGlyphPen(glyphs)
    pen.addComponent("A", (1, 0, 0, 1, 0, 0))
    pen.addComponent("acute", (0.2, 0, 0, 0.2, 200, 730))
    glyphs["composite"] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in glyphs})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupCharacterMap({65: "A", 66: "B", 0x00C1: "composite"})
    builder.setupNameTable({"familyName": "Original Glyph Test", "styleName": "Regular"})
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=1000, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.source = sample_source()

    def compile(self, text="赤い靴\n赤い靴", **kwargs):
        return compile_bundle(parse_cues(text), self.source, song="test", **kwargs)

    def test_occurrence_geometry_changes_with_coherent_palette(self):
        manifest, assets = self.compile()
        self.assertEqual(len(manifest["glyphs"]), 6)
        a, b = manifest["glyphs"][0], manifest["glyphs"][3]
        self.assertNotEqual(a["variant_id"], b["variant_id"])
        paths = lambda g: [p.attrib["d"] for p in ET.fromstring(assets[g["asset"]])]
        self.assertNotEqual(paths(a), paths(b))
        for g in manifest["glyphs"]:
            self.assertIn(g["parameters"]["fill"], manifest["style"]["palette"])
            self.assertEqual(g["stroke_model"], "authored")
            for stroke in g["strokes"]:
                self.assertIn(stroke["terminal"], {"tome", "hane", "harai"})

    def test_byte_reproducibility_and_seed_changes_geometry(self):
        first = self.compile(seed=42)
        self.assertEqual(first, self.compile(seed=42))
        self.assertNotEqual(first[1], self.compile(seed=43)[1])

    def test_cross_platform_asset_golden(self):
        style = StyleDNA.from_dict(json.loads((ROOT / "examples/tango.style.json").read_text(encoding="utf-8")))
        _, assets = compile_bundle(parse_cues((ROOT / "examples/demo.srt").read_text(encoding="utf-8"), srt=True),
                                   self.source, song="Red Shoes experiment", style=style, seed=42)
        hashes = {p: hashlib.sha256(svg.encode("utf-8")).hexdigest() for p, svg in assets.items()}
        expected = json.loads((ROOT / "tests/golden/skeleton-assets.json").read_text(encoding="utf-8"))
        self.assertEqual(hashes, expected)

    def test_malformed_manifest_and_timing_are_rejected(self):
        for change in ("missing", "timing", "parameters", "seed"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                m, a = self.compile()
                out = Path(tmp) / "bundle"
                write_bundle(out, m, a)
                if change == "missing": del m["glyphs"]
                if change == "timing": m["cues"][0]["start_ms"] = -1; m["cues"][0]["end_ms"] = 1000
                if change == "parameters": m["glyphs"][0]["parameters"]["bend"] = 99
                if change == "seed": m["seed"] = True
                (out / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
                with self.assertRaises(ValueError):
                    validate_bundle(out)

    def test_character_reuse_is_explicit(self):
        m, a = self.compile(reuse="character")
        self.assertEqual(len(a), 3)
        self.assertEqual(m["occurrences"][0]["glyph_variant_id"], m["occurrences"][3]["glyph_variant_id"])

    def test_zero_variation_has_identical_svg_for_repeated_character(self):
        m, a = self.compile("赤赤", style=StyleDNA(variation=0))
        self.assertEqual(len(a), 2)  # Separate instances still remain addressable.
        self.assertEqual(*a.values())

    def test_only_used_characters_and_optional_title_are_generated(self):
        m, a = self.compile("赤", title="靴")
        self.assertEqual([g["character"] for g in m["glyphs"]], ["赤", "靴"])
        self.assertIsNone(m["cues"][-1]["start_ms"])
        self.assertEqual(m["inventory"][-1]["count"], 0)

    def test_no_fallback_for_missing_glyph(self):
        with self.assertRaisesRegex(ValueError, "No authored skeleton"):
            self.compile("愛")

    def test_terminal_parameters_change_actual_paths(self):
        _, a = self.compile("永", style=StyleDNA(hane_length=10, harai_taper=0.03))
        _, b = self.compile("永", style=StyleDNA(hane_length=80, harai_taper=0.5))
        self.assertNotEqual(next(iter(a.values())), next(iter(b.values())))

    def test_extreme_allowed_style_fits_canvas(self):
        for slant in (-0.1, 0.1):
            for seed in (0, 2, 50):
                self.compile("赤い靴永", style=StyleDNA(variation=1, width=1.05, height=1.05,
                             slant=slant, stroke_width=80, hane_length=80), seed=seed)

    def test_style_rejects_ignored_or_unsafe_options(self):
        for data in ({"schema_version": 2}, {"schema_version": True},
                     {"schema_version": 1, "texture": "metal"},
                     {"schema_version": 1, "variation": float("nan")},
                     {"schema_version": 1, "variation": True},
                     {"schema_version": 1, "palette": ["url(secret)"]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                StyleDNA.from_dict(data)

    def test_skeleton_validation(self):
        base = {"schema_version": 1, "license_note": "original", "glyphs": {"赤": [
            {"id": "s1", "terminal": "tome", "points": [[200, 200], [800, 800]]}]}}
        for field, value in (("terminal", "magic"), ("points", [[0, 0], [800, 800]]),
                             ("points", [[200, 200], [200, 200]]), ("id", "../bad")):
            data = copy.deepcopy(base)
            data["glyphs"]["赤"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                SkeletonSource(data)

    def test_font_source_outlines_and_composites_without_text_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original.ttf"
            test_font(path)
            source = FontSource(path, license_note="Original test data, Apache-2.0")
            try:
                m, a = compile_bundle(parse_cues("AÁA"), source, song="test")
                self.assertEqual(len(a), 3)
                for svg in a.values():
                    self.assertNotIn("<text", svg)
                    self.assertNotIn("href", svg)
                    validate_svg(svg)
                self.assertEqual(m["glyphs"][0]["stroke_model"], "outline")
                self.assertIsNone(m["glyphs"][0]["strokes"][0]["terminal"])
                with self.assertRaisesRegex(ValueError, "no outline"):
                    compile_bundle(parse_cues("靴"), source, song="test")
            finally:
                source.close()

    def test_roundtrip_and_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "Japanese 空間" / "bundle"
            m, a = self.compile()
            write_bundle(output, m, a)
            self.assertEqual(validate_bundle(output), m)
            self.assertTrue(all("\\" not in g["asset"] for g in m["glyphs"]))
            with self.assertRaisesRegex(ValueError, "already exists"):
                write_bundle(output, m, a)

    def test_tamper_and_path_escape_rejected(self):
        for change in ("hash", "path", "character", "mapping", "metrics", "palette", "stroke"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "bundle"
                m, a = self.compile()
                write_bundle(output, m, a)
                if change == "hash":
                    asset = output / m["glyphs"][0]["asset"]
                    asset.write_bytes(asset.read_bytes() + b" ")
                else:
                    if change == "path": m["glyphs"][0]["asset"] = "../secret.svg"
                    if change == "character": m["glyphs"][0]["character"] = "愛"
                    if change == "mapping": m["occurrences"].pop()
                    if change == "metrics": m["glyphs"][0]["metrics"]["bounds"] = [0, 0, 2, 2]
                    if change == "palette": m["style"]["palette"] = ["#000001"]
                    if change == "stroke": m["glyphs"][0]["strokes"][0]["element_id"] = "bad"
                    (output / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
                with self.assertRaises(ValueError):
                    validate_bundle(output)

    def test_invalid_assets_leave_no_partial_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "bundle"
            m, a = self.compile()
            a[next(iter(a))] = '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'
            with self.assertRaises(ValueError):
                write_bundle(output, m, a)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_unsafe_svg_subset_rejected(self):
        for inner in ('<text>赤</text>', '<image href="file:///secret"/>', '<script/>',
                      '<path id="stroke001" fill="#000000" d="M1 1 L3 3"/>',
                      '<path id="stroke001" fill="#000000" d="M-10 1 L3 3 L4 1Z"/>'):
            with self.subTest(inner=inner), self.assertRaises(ValueError):
                validate_svg(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">{inner}</svg>')

    def test_cli_end_to_end_and_legacy_inventory(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            out = Path(tmp) / "bundle"
            main(["generate", str(ROOT / "examples/demo.srt"), "--song", "test", "--skeletons",
                  str(ROOT / "examples/skeletons.json"), "--out", str(out)])
            main(["validate", str(out)])
            preview = Path(tmp) / "preview.svg"
            main(["preview", str(out), "--out", str(preview)])
            self.assertEqual(len(ET.fromstring(preview.read_text(encoding="utf-8"))), 10)
            self.assertEqual(len(validate_bundle(out)["glyphs"]), 9)
            inventory = Path(tmp) / "inventory.json"
            main([str(ROOT / "examples/demo.srt"), "--song", "test", "--out", str(inventory)])
            self.assertEqual(json.loads(inventory.read_text(encoding="utf-8"))["schema_version"], 1)

    def test_cli_error_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()) as err:
            lyric = Path(tmp) / "lyrics.txt"
            lyric.write_text("愛", encoding="utf-8")
            with self.assertRaises(SystemExit) as raised:
                main(["generate", str(lyric), "--song", "test", "--skeletons",
                      str(ROOT / "examples/skeletons.json"), "--out", str(Path(tmp) / "bundle")])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("No authored skeleton", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())
