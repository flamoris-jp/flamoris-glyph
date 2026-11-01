from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from flamoris_glyph import FontSource, SkeletonSource, StyleDNA, compile_bundle, parse_cues, validate_bundle, write_bundle
from flamoris_glyph.cli import main
from flamoris_glyph.lyrics import occurrences
from flamoris_glyph.pattern import PatternDNA, PRESETS, geometry_path, path_geometry, topology, transform_shape
from flamoris_glyph.pattern_lab import run_lab

ROOT = Path(__file__).resolve().parents[1]
NEUTRAL = StyleDNA(name="neutral",palette=("#222222",),variation=0,stroke_width=28)


def synthetic_coverage_font(path, chars):
    """Explicit cmap to ORIGINAL TEST SHAPES, never Japanese legibility evidence.

    Every character is intentionally mapped to the synthetic diagnostic glyph.
    Curves, a counter, small disconnected mark and a composite are exercised.
    No third-party font or silently selected fallback is used.
    """
    builder = FontBuilder(1000,isTTF=True)
    order = [".notdef","diagnostic","mark","composite"]
    builder.setupGlyphOrder(order)
    glyphs = {}
    pen = TTGlyphPen(None)
    pen.moveTo((100,100));pen.lineTo((700,100));pen.lineTo((700,800))
    pen.qCurveTo((400,900),(100,800));pen.closePath()
    # Opposite winding => counter.
    pen.moveTo((200,230));pen.lineTo((200,680));pen.lineTo((570,680));pen.lineTo((570,230));pen.closePath()
    glyphs["diagnostic"] = pen.glyph()
    glyphs[".notdef"] = TTGlyphPen(None).glyph()
    pen = TTGlyphPen(None)
    pen.moveTo((760,700));pen.lineTo((800,700));pen.lineTo((800,770));pen.lineTo((760,770));pen.closePath()
    glyphs["mark"] = pen.glyph()
    pen = TTGlyphPen(glyphs)
    pen.addComponent("diagnostic",(1,0,0,1,0,0));pen.addComponent("mark",(1,0,0,1,0,0))
    glyphs["composite"] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({n:(900,0) for n in order})
    builder.setupHorizontalHeader(ascent=1000,descent=-200)
    builder.setupCharacterMap({ord(c):"composite" for c in sorted(chars)})
    builder.setupNameTable({"familyName":"Original Pattern QA Fixture","styleName":"Diagnostic"})
    builder.setupOS2(sTypoAscender=1000,sTypoDescender=-200,usWinAscent=1000,usWinDescent=200)
    builder.setupPost();builder.setupMaxp()
    builder.font["head"].created = builder.font["head"].modified = 3400000000
    builder.font.recalcTimestamp = False
    builder.save(path)


class PatternTests(unittest.TestCase):
    def source(self):
        return SkeletonSource(json.loads((ROOT/"examples/pattern-lab-skeletons.json").read_text(encoding="utf-8")))

    def test_schema_is_strict_bounded_and_versioned(self):
        p = PatternDNA.preset("heavy-condensed-headline")
        self.assertEqual(p,PatternDNA.from_dict(p.to_dict()))
        for key,value in (("schema_version",True),("profile","unknown"),("width",float("nan")),
                          ("variation",True),("offset_x",500),("font_product","anything")):
            d=p.to_dict();d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):PatternDNA.from_dict(d)
        d=p.to_dict();del d["offset_y"]
        with self.assertRaises(ValueError):PatternDNA.from_dict(d)

    def test_determinism_seed_variation_zero_and_reuse(self):
        def generate(pattern,seed=42,reuse="occurrence"):
            return compile_bundle(parse_cues("赤赤"),self.source(),song="test",style=NEUTRAL,
                                  pattern=pattern,seed=seed,reuse=reuse)
        for profile in PRESETS:
            p=PatternDNA.preset(profile)
            m,a=generate(p)
            self.assertEqual((m,a),generate(p))
            self.assertNotEqual(list(a.values()),list(generate(p,43)[1].values()))
            self.assertNotEqual(*a.values())
            self.assertEqual(*generate(replace(p,variation=0))[1].values())
            self.assertEqual(len(generate(p,reuse="character")[1]),1)
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/"bundle";write_bundle(out,m,a)
                self.assertEqual(validate_bundle(out),m)

    def test_nonzero_fill_holes_winding_and_self_intersection(self):
        # Same winding nested contour remains filled; opposite winding is a hole.
        outer="M100 100L900 100L900 900L100 900Z"
        hole="M300 300L300 700L700 700L700 300Z"
        same="M300 300L700 300L700 700L300 700Z"
        self.assertEqual(topology(path_geometry(outer+hole)),(1,1))
        self.assertEqual(topology(path_geometry(outer+same)),(1,0))
        g=path_geometry(outer+hole)
        self.assertEqual(topology(path_geometry(geometry_path(g))),(1,1))
        with self.assertRaisesRegex(ValueError,"self-intersecting"):
            path_geometry("M100 100L900 900L100 900L900 100Z")

    def test_contrast_and_rounding_go_beyond_scaling(self):
        # Authored block structure with horizontal/vertical bars, a hole and
        # right-angle corners. Directional offsets change actual stroke ratios.
        d="M200 200L800 200L800 800L200 800Z M260 260L260 740L740 740L740 260Z"
        shape={"paths":[{"id":"outline","d":d,"terminal":None}],"stroke_model":"outline","advance":1000}
        original=path_geometry(d)
        for profile in PRESETS:
            result,qa=transform_shape(shape,PatternDNA.preset(profile),"fixture",42)
            g=path_geometry(result["paths"][0]["d"])
            self.assertEqual(topology(g),topology(original))
            self.assertGreater(qa["applied_strength"],0)
            # Filled area / bounding-box area is invariant under global scaling.
            ratio=lambda p:p.area/((p.bounds[2]-p.bounds[0])*(p.bounds[3]-p.bounds[1]))
            self.assertGreater(abs(ratio(g)-ratio(original)),0.0001)
        p=PatternDNA.preset("elegant-high-contrast-editorial")
        r,_=transform_shape(shape,p,"fixture",42)
        g=path_geometry(r["paths"][0]["d"])
        hole=list(g.interiors)[0].bounds
        vertical=(hole[0]-g.bounds[0])/(g.bounds[2]-g.bounds[0])
        horizontal=(hole[1]-g.bounds[1])/(g.bounds[3]-g.bounds[1])
        self.assertGreater(vertical,horizontal)

    def test_complex_counter_protection_reports_reduced_strength(self):
        d="M200 200L800 200L800 800L200 800Z M494 450L494 550L506 550L506 450Z"
        shape={"paths":[{"id":"outline","d":d,"terminal":None}],"advance":1000,"stroke_model":"outline"}
        r,qa=transform_shape(shape,PatternDNA.preset("heavy-condensed-headline"),"small-hole",42)
        self.assertEqual(topology(path_geometry(r["paths"][0]["d"])),(1,1))
        self.assertLess(qa["applied_strength"],1)
        self.assertTrue(qa["warnings"])
        self.assertTrue(qa["review_required"])

    def test_unrecoverable_counter_retains_original_with_rejection(self):
        d="M200 200L800 200L800 800L200 800Z M499.999 450L499.999 550L500.001 550L500.001 450Z"
        shape={"paths":[{"id":"outline","d":d,"terminal":None}],"advance":1000,"stroke_model":"outline"}
        result,qa=transform_shape(shape,PatternDNA.preset("heavy-condensed-headline"),"tiny-hole",42)
        self.assertEqual(result,shape)
        self.assertEqual(qa["applied_strength"],0)
        self.assertIn("pattern-rejected-original-retained",qa["warnings"])

    def test_reader_does_not_require_optional_geometry_dependency(self):
        m,a=compile_bundle(parse_cues("赤"),self.source(),song="test",style=NEUTRAL,
                           pattern=PatternDNA.preset("elegant-high-contrast-editorial"))
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"bundle";write_bundle(out,m,a)
            original_import=__import__
            def no_shapely(name,*args,**kwargs):
                if name.startswith("shapely"):raise ImportError("optional dependency unavailable")
                return original_import(name,*args,**kwargs)
            with patch("builtins.__import__",side_effect=no_shapely):
                self.assertEqual(validate_bundle(out),m)

    def test_failed_matrix_leaves_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,"No authored skeleton"):
                run_lab(parse_cues("赤 無"),self.source(),root/"lab")
            self.assertEqual(list(root.iterdir()),[])

    def test_full_lyric_synthetic_coverage_matrix_and_cli(self):
        cues=parse_cues((ROOT/"examples/glyph-pattern-lab.srt").read_text(encoding="utf-8"),srt=True)
        self.assertEqual((len(cues),len(occurrences(cues)),cues[-1].end_ms),(10,88,35000))
        # Add punctuation explicitly: it is absent from the provided lyric.
        chars={o.character for o in occurrences(cues)}|set("。、!?（）")
        with tempfile.TemporaryDirectory() as tmp,redirect_stdout(io.StringIO()):
            path=Path(tmp)/"synthetic.ttf";synthetic_coverage_font(path,chars)
            source=FontSource(path,license_note="Original synthetic diagnostic geometry, Apache-2.0; NOT legibility evidence")
            try:
                report=run_lab(cues,source,Path(tmp)/"lab")
                self.assertTrue(report["fixed_seed_reproduction"])
                self.assertEqual(len(report["matrix"]),8)
                self.assertTrue(all(r["occurrences"]==88 for r in report["matrix"]))
                m,a=compile_bundle(parse_cues("。、!?（）"),source,song="punctuation",style=NEUTRAL,
                                   pattern=PatternDNA.preset("showa-retro-signboard"))
                self.assertEqual(len(a),6)
                with self.assertRaisesRegex(ValueError,"no outline"):
                    compile_bundle(parse_cues("無"),source,song="missing",pattern=PatternDNA.preset("showa-retro-signboard"))
                hashes={p:hashlib.sha256(svg.encode()).hexdigest() for p,svg in a.items()}
                expected=json.loads((ROOT/"tests/golden/pattern-assets.json").read_text())
                self.assertEqual(hashes,expected)
            finally:source.close()
            out=Path(tmp)/"cli"
            main(["generate",str(ROOT/"examples/glyph-pattern-lab.srt"),"--font",str(path),
                  "--source-license","Original QA fixture","--song","lab","--pattern","heavy-condensed-headline","--out",str(out)])
            self.assertEqual(len(validate_bundle(out)["occurrences"]),88)

    def test_pattern_metadata_tamper_rejected(self):
        for field in ("schema","engine","parameters","strength","identity"):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                m,a=compile_bundle(parse_cues("赤"),self.source(),song="test",style=NEUTRAL,
                                   pattern=PatternDNA.preset("elegant-high-contrast-editorial"))
                out=Path(tmp)/"bundle";write_bundle(out,m,a)
                if field=="schema":m["pattern"]["schema_version"]=2
                if field=="engine":del m["pattern_engine"]
                if field=="parameters":m["glyphs"][0]["pattern_qa"]["parameters"]["offset_x"]=0
                if field=="strength":m["glyphs"][0]["pattern_qa"]["applied_strength"]=True
                if field=="identity":m["pattern"]["width"]=0.9
                (out/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
                with self.assertRaises(ValueError):validate_bundle(out)


if __name__=="__main__":unittest.main()
