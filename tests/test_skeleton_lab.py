from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from flamoris_glyph.anatomy import AnatomyDNA
from flamoris_glyph.bundle import validate_svg
from flamoris_glyph.skeleton_lab import ink_identity, parse_patterns, run_study

ROOT = Path(__file__).resolve().parents[1]


class SkeletonLabTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT/"examples/aka-structure.json").read_text(encoding="utf-8"))
        self.shared = AnatomyDNA.from_dict(json.loads((ROOT/"examples/anatomy-dna/elastic-retro.json").read_text(encoding="utf-8")))
        self.patterns = json.loads((ROOT/"examples/skeleton-patterns.json").read_text(encoding="utf-8"))

    def test_patterns_change_only_bones_and_preserve_resolved_dna(self):
        rules = parse_patterns(self.patterns, self.shared)
        self.assertEqual(len(rules), 6)
        self.assertEqual(len({p["dna"].bones for p in rules}), 6)
        for p in rules:
            dna = p["dna"]
            self.assertEqual(ink_identity(dna), ink_identity(self.shared))
            self.assertEqual(dna.ink, self.shared.ink)
            self.assertEqual(dna, AnatomyDNA.from_dict(dna.to_dict()))

    def test_strict_path_safe_pattern_schema(self):
        for mutation in ("version", "duplicate", "traversal", "extra", "missing-role", "missing-field", "nan", "empty"):
            data = deepcopy(self.patterns)
            if mutation == "version": data["schema_version"] = True
            if mutation == "duplicate": data["patterns"][1]["id"] = data["patterns"][0]["id"]
            if mutation == "traversal": data["patterns"][0]["id"] = "../escape"
            if mutation == "extra": data["patterns"][0]["ink"] = {}
            if mutation == "missing-role": del data["patterns"][0]["bones"]["outer-left"]
            if mutation == "missing-field": del data["patterns"][0]["bones"]["top-bar"]["angle"]
            if mutation == "nan": data["patterns"][0]["bones"]["top-bar"]["angle"] = float("nan")
            if mutation == "empty": data["patterns"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                parse_patterns(data, self.shared)

    def test_twelve_valid_distinct_designs_with_identical_local_widths(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"matrix"
            report = run_study(self.source, self.shared, self.patterns, out)
            self.assertEqual(len(report["cells"]), 12)
            for family in ("gothic", "mincho"):
                cells = {c["pattern"]: c for c in report["cells"] if c["family"] == family}
                self.assertEqual(len({(out/c["asset"]).read_text() for c in cells.values()}), 6)
                baseline = cells["upright"]["qa"]["width_stations"]
                for cell in cells.values():
                    validate_svg((out/cell["asset"]).read_text())
                    self.assertEqual(cell["qa"]["width_stations"], baseline)
                    self.assertEqual(cell["qa"]["silhouettes"], 3)
                    self.assertGreaterEqual(min(cell["qa"]["clearances"].values()), self.shared.minimum_gap)
                def bar_delta(pattern, axis, role="main-bar"):
                    p = cells[pattern]["qa"]["landmarks"][role]
                    return p[-1][axis]-p[0][axis]
                self.assertEqual(bar_delta("upright", 1), 0)
                self.assertLess(bar_delta("rising", 1), 0)
                self.assertGreater(bar_delta("falling", 1), 0)
                self.assertLess(bar_delta("compact", 0), bar_delta("upright", 0))
                self.assertLess(bar_delta("offset", 1, "top-bar"), 0)
                self.assertGreater(bar_delta("offset", 1), 0)

    def test_reproduction_existing_output_and_atomic_clearance_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/"a", Path(tmp)/"b"
            first = run_study(self.source, self.shared, self.patterns, a)
            self.assertEqual(first, run_study(self.source, self.shared, self.patterns, b))
            for p in a.rglob("*"):
                if p.is_file(): self.assertEqual(p.read_bytes(), (b/p.relative_to(a)).read_bytes())
            with self.assertRaises(ValueError): run_study(self.source, self.shared, self.patterns, a)
            failed = Path(tmp)/"failed"
            with self.assertRaisesRegex(ValueError, "clearance"):
                run_study(self.source, replace(self.shared, minimum_gap=35), self.patterns, failed)
            self.assertFalse(failed.exists())
            self.assertFalse(list(Path(tmp).glob(".skeleton-study-*")))


if __name__ == "__main__":
    unittest.main()
