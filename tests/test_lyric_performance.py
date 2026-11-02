import json
from pathlib import Path
import tempfile
import unittest

from flamoris_glyph.bundle import validate_svg
from flamoris_glyph.lyric_performance import (
    SKELETONS, STROKES, PerformanceSource, express_centerline,
    run_performance, sample_centerline,
)
from flamoris_glyph.pattern import path_geometry

INPUTS = Path(__file__).resolve().parents[1]/"examples"/"mou-iiyo"


def read(name):
    return json.loads((INPUTS/name).read_text(encoding="utf-8"))


class LyricPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.jp, self.latin = read("kanjivg-subset.json"), read("latin-skeletons.json")

    def test_expression_changes_route_with_same_skeleton_and_dna(self):
        line = sample_centerline("M250 500 L750 500")
        gentle = express_centerline(line, SKELETONS["open"], STROKES["gentle"])
        energetic = express_centerline(line, SKELETONS["open"], STROKES["energetic"])
        self.assertGreater(abs(energetic[40][1]-gentle[40][1]), 15)
        a = PerformanceSource(self.jp, self.latin, stroke="gentle")
        b = PerformanceSource(self.jp, self.latin, stroke="energetic")
        self.assertEqual(a.identity["dna"], b.identity["dna"])
        self.assertEqual(a.identity["skeleton"], b.identity["skeleton"])
        self.assertNotEqual(a.draw("も")["svg"], b.draw("も")["svg"])
        self.assertEqual(a.draw("も")["advance"], b.draw("も")["advance"])

    def test_closed_source_loop_keeps_counter_and_missing_glyph_rejects(self):
        import xml.etree.ElementTree as ET
        source = PerformanceSource(self.jp, self.latin)
        svg = source.draw("o")["svg"]
        validate_svg(svg)
        geometry = path_geometry(ET.fromstring(svg)[0].attrib["d"])
        self.assertEqual(len(geometry.interiors), 1)
        with self.assertRaisesRegex(ValueError, "No explicit"):
            source.draw("猫")
        for path in ("M0 0", "M0 0 L2000 0", "M0 0 L1 0 M2 0 L3 0"):
            with self.assertRaises(ValueError):
                sample_centerline(path)

    def test_full_lyric_exports_mapping_licenses_and_fontless_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"artwork"
            report = run_performance(INPUTS, out)
            self.assertEqual(len(report["performances"]), 3)
            for p in report["performances"]:
                manifest = json.loads((out/p["id"]/"manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(len(manifest["cues"]), 10)
                self.assertTrue(all(c["start_ms"] is None for c in manifest["cues"]))
                self.assertTrue(all("　" in c["text"] for c in manifest["cues"]))
                self.assertEqual(manifest["artwork_license"], "CC-BY-SA-3.0")
                self.assertEqual(len(manifest["occurrences"]), p["occurrences"])
                for name in manifest["assets"]:
                    validate_svg((out/p["id"]/name).read_text(encoding="utf-8"))
                self.assertEqual({o["asset"] for o in manifest["occurrences"]}, set(manifest["assets"]))
            self.assertEqual((out/"lyrics.txt").read_bytes(), (INPUTS/"lyrics.txt").read_bytes())
            self.assertTrue((out/"ATTRIBUTION.md").is_file())
            with self.assertRaisesRegex(ValueError, "already exists"):
                run_performance(INPUTS, out)

    def test_failed_coverage_does_not_publish_partial_artwork(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            inputs, out = Path(tmp)/"input", Path(tmp)/"output"
            shutil.copytree(INPUTS, inputs)
            text = (inputs/"lyrics.txt").read_text(encoding="utf-8")
            (inputs/"lyrics.txt").write_text(text.replace("顔", "猫"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No explicit"):
                run_performance(inputs, out)
            self.assertFalse(out.exists())
            self.assertFalse(list(Path(tmp).glob(".lyric-performance-*")))


if __name__ == "__main__":
    unittest.main()
