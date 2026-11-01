from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest

from flamoris_glyph.anatomy import InkRule
from flamoris_glyph.bundle import validate_svg
from flamoris_glyph.calligraphy import CalligraphyTool, LetterDNA, SkeletonPlan, draw_glyph, sample_stroke, sweep_stroke
from flamoris_glyph.calligraphy_lab import parse_study, run_study
from flamoris_glyph.structure import AuthoredStructureSource
from flamoris_glyph.style import digest

ROOT = Path(__file__).resolve().parents[1]


class CalligraphyTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT/"examples/aka-structure.json").read_text(encoding="utf-8"))
        self.data = json.loads((ROOT/"examples/calligraphy-study.json").read_text(encoding="utf-8"))
        self.skeletons, self.dnas, self.tools = parse_study(self.data)
        self.plan = SkeletonPlan.from_source(AuthoredStructureSource(self.source, "gothic"), self.skeletons[0]["dna"].bones)

    def test_broad_nib_direction_changes_actual_swept_width(self):
        ink = InkRule(start_cap="round", end_cap="round")
        horizontal = ((200, 500), (400, 500), (600, 500), (800, 500))
        vertical = ((500, 200), (500, 400), (500, 600), (500, 800))
        tool = CalligraphyTool("broad", angle=0, aspect=.18)
        h, hqa = sweep_stroke(horizontal, ink, 100, 1, 0, tool)
        v, vqa = sweep_stroke(vertical, ink, 100, 1, 0, tool)
        self.assertAlmostEqual(h.bounds[3]-h.bounds[1], 18, places=5)
        self.assertAlmostEqual(v.bounds[2]-v.bounds[0], 100, places=5)
        self.assertEqual(hqa["projected_width"], [18]*5)
        self.assertEqual(vqa["projected_width"], [100]*5)

    def test_round_nib_is_direction_independent_with_constant_intent(self):
        ink = InkRule(start_cap="round", end_cap="round")
        for end in ((800, 500), (500, 800), (750, 750)):
            start = (200, 200)
            points = tuple(tuple(start[a]+(end[a]-start[a])*i/3 for a in (0, 1)) for i in range(4))
            _, qa = sweep_stroke(points, ink, 60, 1, 0, CalligraphyTool.preset("round"))
            self.assertEqual(qa["desired_width"], [60]*5)
            self.assertEqual(qa["projected_width"], [60]*5)

    def test_brush_pressure_is_applied_along_arc_length(self):
        # Uneven cubic parameter speed on a straight line.
        points = ((100, 500), (101, 500), (102, 500), (900, 500))
        samples, tangents = sample_stroke(points)
        distances = [math.dist(a, b) for a, b in zip(samples, samples[1:])]
        self.assertLess(max(distances)-min(distances), .01)
        _, qa = sweep_stroke(points, InkRule(start_cap="round", end_cap="round"), 60, 1, 0,
                             CalligraphyTool.preset("brush"))
        self.assertEqual(qa["desired_width"], [60]*5)
        self.assertEqual(qa["pressure"], [.35, .85, 1.05, 1.15, .25])
        self.assertEqual(qa["projected_width"], [21, 51, 63, 69, 15])

    def test_three_inputs_roundtrip_and_no_bones_or_tool_in_letter_dna(self):
        for item in self.dnas:
            dna = item["dna"]
            self.assertEqual(dna, LetterDNA.from_dict(dna.to_dict()))
            self.assertNotIn("bones", dna.to_dict())
            self.assertNotIn("tool", dna.to_dict())
        for item in self.tools:
            tool = item["tool"]
            self.assertEqual(tool, CalligraphyTool.from_dict(tool.to_dict()))
        source = AuthoredStructureSource(self.source, "gothic")
        plan = SkeletonPlan.from_source(source, self.skeletons[0]["dna"].bones)
        self.assertEqual(self.plan, plan)
        with self.assertRaises(ValueError):
            draw_glyph(plan, self.skeletons[0]["dna"], CalligraphyTool.preset("round"))

    def test_schema_rejects_unknown_nonfinite_or_unused_tool_fields(self):
        for field, value in (("schema_version", True), ("kind", "future"), ("weight", float("nan")), ("tool", {})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                LetterDNA.from_dict({**self.dnas[0]["dna"].to_dict(), field: value})
        for tool in ({"mode": "unknown"}, {"mode": "round", "aspect": .5},
                     {"mode": "brush", "angle": 10}, {"mode": "broad", "pressure": (.5, 1, 1, 1, 1)},
                     {"mode": "broad", "angle": True}):
            with self.subTest(tool=tool), self.assertRaises(ValueError): CalligraphyTool(**tool)
        bad = deepcopy(self.data); bad["tools"][0]["id"] = "../escape"
        with self.assertRaises(ValueError): parse_study(bad)
        bad = deepcopy(self.data); bad["dnas"][1]["id"] = bad["dnas"][0]["id"]
        with self.assertRaises(ValueError): parse_study(bad)

    def test_full_matrix_has_independent_identities_and_valid_distinct_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"study"
            report = run_study(self.source, self.data, out)
            self.assertEqual(len(report["cells"]), 12)
            for skeleton in self.skeletons:
                cells = [c for c in report["cells"] if c["skeleton"] == skeleton["id"]]
                self.assertEqual(len({c["qa"]["plan_sha256"] for c in cells}), 1)
                self.assertEqual(len({digest(c["qa"]["landmarks"]) for c in cells}), 1)
                self.assertEqual(len({(out/c["asset"]).read_text() for c in cells}), 6)
                for dna in self.dnas:
                    row = [c for c in cells if c["dna"] == dna["id"]]
                    self.assertEqual(len({c["qa"]["dna_sha256"] for c in row}), 1)
                    self.assertEqual(len({digest({r: q["desired_width"] for r, q in c["qa"]["stroke_diagnostics"].items()}) for c in row}), 1)
                for cell in cells:
                    validate_svg((out/cell["asset"]).read_text())
                    self.assertEqual(cell["qa"]["silhouettes"], 3)
                    self.assertGreaterEqual(min(cell["qa"]["clearances"].values()), 6)

    def test_clearance_violations_reject_without_changing_bone_or_dna(self):
        plan = SkeletonPlan.from_source(AuthoredStructureSource(self.source, "gothic"), self.skeletons[1]["dna"].bones)
        dna = replace(self.dnas[0]["dna"], minimum_gap=35)
        before = digest(plan.to_dict()), digest(dna.to_dict())
        with self.assertRaisesRegex(ValueError, "clearance"):
            draw_glyph(plan, dna, CalligraphyTool.preset("round"))
        self.assertEqual(before, (digest(plan.to_dict()), digest(dna.to_dict())))

    def test_reproduction_existing_output_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/"a", Path(tmp)/"b"
            first = run_study(self.source, self.data, a)
            self.assertEqual(first, run_study(self.source, self.data, b))
            for path in a.rglob("*"):
                if path.is_file(): self.assertEqual(path.read_bytes(), (b/path.relative_to(a)).read_bytes())
            with self.assertRaises(ValueError): run_study(self.source, self.data, a)
            bad = deepcopy(self.data)
            for dna in bad["dnas"]: dna["dna"]["minimum_gap"] = 35
            failed = Path(tmp)/"failed"
            with self.assertRaises(ValueError): run_study(self.source, bad, failed)
            self.assertFalse(failed.exists())
            self.assertFalse(list(Path(tmp).glob(".calligraphy-study-*")))


if __name__ == "__main__": unittest.main()
