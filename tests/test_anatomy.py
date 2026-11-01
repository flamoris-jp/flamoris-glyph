from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from flamoris_glyph.anatomy import AnatomyDNA, BoneRule, InkRule, design_glyph
from flamoris_glyph.anatomy_lab import ablations, run_study
from flamoris_glyph.bundle import validate_svg
from flamoris_glyph.pattern import path_geometry
from flamoris_glyph.structure import AuthoredStructureSource, ROLES

ROOT = Path(__file__).resolve().parents[1]


class AnatomyTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/"examples/aka-structure.json").read_text(encoding="utf-8"))
        self.dna = AnatomyDNA.from_dict(json.loads((ROOT/"examples/anatomy-dna/elastic-retro.json").read_text(encoding="utf-8")))

    def render(self, dna=None, family="gothic"):
        return design_glyph(AuthoredStructureSource(self.data, family), dna or self.dna)

    def test_bone_and_ink_ablations_are_independent(self):
        source, bones, ink, full = [self.render(d) for d in ablations(self.dna)]
        self.assertEqual(source[1]["landmarks"], ink[1]["landmarks"])
        self.assertEqual(bones[1]["landmarks"], full[1]["landmarks"])
        self.assertEqual(source[1]["width_stations"], bones[1]["width_stations"])
        self.assertEqual(ink[1]["width_stations"], full[1]["width_stations"])
        self.assertNotEqual(source[1]["landmarks"], bones[1]["landmarks"])
        self.assertEqual(len({s for s, _ in (source, bones, ink, full)}), 4)
        bar = full[1]["landmarks"]["top-bar"]
        old = source[1]["landmarks"]["top-bar"]
        self.assertLess(bar[-1][1], bar[0][1])  # explicit slope
        self.assertNotAlmostEqual(bar[-1][0]-bar[0][0], old[-1][0]-old[0][0])

    def test_junctions_follow_the_redesigned_bar(self):
        _, qa = self.render()
        main = qa["landmarks"]["main-bar"]
        for role, index in (("top-stem", 3), ("inner-left", 0), ("inner-right", 0)):
            x, y = qa["landmarks"][role][index]
            # These authored bars are collinear, including after length/angle.
            expected = main[0][1]+(x-main[0][0])*(main[-1][1]-main[0][1])/(main[-1][0]-main[0][0])
            self.assertAlmostEqual(y, expected, places=3)

    def test_bulge_location_and_terminal_direction_are_independent_controls(self):
        original = self.render()
        ink = list(self.dna.ink)
        ink[0] = replace(ink[0], stations=(0, .1, .6, .9, 1))
        moved = self.render(replace(self.dna, ink=tuple(ink)))
        self.assertEqual(original[1]["landmarks"], moved[1]["landmarks"])
        self.assertNotEqual(original[0], moved[0])
        bones = list(self.dna.bones)
        bones[3] = replace(bones[3], end_turn=0)
        turned = self.render(replace(self.dna, bones=tuple(bones)))
        a, b = original[1]["landmarks"]["inner-left"], turned[1]["landmarks"]["inner-left"]
        self.assertEqual(a[-1], b[-1])
        self.assertNotEqual(a[-2], b[-2])
        self.assertEqual(original[1]["width_stations"], turned[1]["width_stations"])

    def test_filled_outlines_stay_separate_and_preserve_role_identity(self):
        for family in ("gothic", "mincho"):
            for dna in ablations(self.dna):
                svg, qa = self.render(dna, family)
                validate_svg(svg)
                paths = list(ET.fromstring(svg))
                self.assertEqual(len(paths), 7)
                self.assertEqual(qa["semantic_roles"], list(ROLES))
                for path in paths:
                    geom = path_geometry(path.attrib["d"])
                    self.assertEqual(geom.geom_type, "Polygon")
                    self.assertTrue(geom.is_valid)
                    self.assertFalse(geom.interiors)
                self.assertEqual(qa["silhouettes"], 3)
                self.assertGreaterEqual(min(qa["clearances"].values()), dna.minimum_gap)
                if dna.ink == AnatomyDNA().ink:
                    self.assertGreater(qa["width_stations"]["inner-left"][-1], 0)
                else:
                    self.assertEqual(qa["width_stations"]["inner-left"][-1], 0)

    def test_inheritance_changes_ink_without_moving_bones(self):
        for family in ("gothic", "mincho"):
            zero = self.render(replace(self.dna, source_width_mix=0, source_taper_mix=0), family)
            one = self.render(replace(self.dna, source_width_mix=1, source_taper_mix=1), family)
            self.assertEqual(zero[1]["landmarks"], one[1]["landmarks"])
            self.assertNotEqual(zero[1]["width_stations"], one[1]["width_stations"])
            self.assertNotEqual(zero[0], one[0])
        self.assertNotEqual(self.render()[0], self.render(family="mincho")[0])

    def test_clearance_and_topology_fail_instead_of_silently_repairing(self):
        with self.assertRaisesRegex(ValueError, "clearance"):
            self.render(replace(self.dna, minimum_gap=35), "mincho")
        bones = list(self.dna.bones)
        bones[5] = replace(bones[5], dx=100)
        with self.assertRaises(ValueError):
            self.render(replace(self.dna, bones=tuple(bones)))
        with self.assertRaises(ValueError):
            design_glyph(AuthoredStructureSource(self.data, "gothic"), self.dna, "靴")

    def test_exact_schema_and_immutable_rules(self):
        self.assertEqual(self.dna, AnatomyDNA.from_dict(self.dna.to_dict()))
        for key, value in (("schema_version", True), ("kind", "future"), ("weight", float("nan")),
                           ("source_width_mix", True), ("extra", 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                AnatomyDNA.from_dict({**self.dna.to_dict(), key: value})
        with self.assertRaises(ValueError):
            InkRule(stations=(0, .5, .4, .8, 1))
        with self.assertRaises(ValueError):
            InkRule(widths=(1, 1, 1, 1, 0))
        with self.assertRaises(ValueError):
            BoneRule(angle=90)
        with self.assertRaises(ValueError):
            AnatomyDNA(bones=())

    def test_study_reproduces_and_failed_run_is_atomic(self):
        self.assertEqual(self.render(), self.render())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"study"
            report = run_study(self.data, self.dna, out)
            self.assertEqual(len(report["cells"]), 8)
            self.assertEqual(len(report["inheritance"]), 6)
            with self.assertRaises(ValueError):
                run_study(self.data, self.dna, out)
            bad = Path(tmp)/"failed"
            with self.assertRaises(ValueError):
                run_study(self.data, replace(self.dna, minimum_gap=35), bad)
            self.assertFalse(bad.exists())
            self.assertFalse(list(Path(tmp).glob(".anatomy-study-*")))


if __name__ == "__main__":
    unittest.main()
