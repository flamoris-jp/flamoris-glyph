from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from flamoris_glyph.bundle import validate_svg
from flamoris_glyph.stroke_lab import parse_study, run_study
from flamoris_glyph.stroke_program import StrokePhase, StrokeProgram, paint_program, sample_program

ROOT = Path(__file__).resolve().parents[1]


class StrokeProgramTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/"examples/stroke-program-study.json").read_text(encoding="utf-8"))
        self.cases = {c["id"]: c for c in parse_study(self.data)}

    def test_bounded_exact_schema_and_continuous_states(self):
        original = self.cases["finish-stop"]["program"]
        self.assertEqual(original, StrokeProgram.from_dict(original.to_dict()))
        for mutation in ("version", "extra", "too-many", "unknown-action", "jump", "pressure-jump", "angle-jump", "bad-pressure", "moving-settle"):
            data = deepcopy(original.to_dict())
            if mutation == "version": data["schema_version"] = True
            if mutation == "extra": data["arbitrary"] = 1
            if mutation == "too-many": data["phases"] = data["phases"]*2
            if mutation == "unknown-action": data["phases"][0]["action"] = "magic"
            if mutation == "jump": data["phases"][1]["points"] = [[10, 10]]*4
            if mutation == "pressure-jump": data["phases"][1]["pressure"] = [.5, .95]
            if mutation == "angle-jump": data["phases"][1]["angle"] = [20, 35]
            if mutation == "bad-pressure": data["phases"][0]["pressure"] = [0, float("nan")]
            if mutation == "moving-settle": data["phases"][2]["points"] = [[500,650],[501,650],[502,650],[503,650]]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): StrokeProgram.from_dict(data)

    def test_duration_only_changes_time_not_static_ink(self):
        p = self.cases["finish-stop"]["program"]
        phases = list(p.phases); phases[2] = replace(phases[2], duration=1.4)
        slow = StrokeProgram(tuple(phases))
        a, qa = paint_program(p); b, qb = paint_program(slow)
        self.assertEqual(a, b)
        self.assertGreater(qb["duration"], qa["duration"])
        self.assertNotEqual(qb["program_sha256"], qa["program_sha256"])
        self.assertEqual([{k:v for k,v in s.items() if k != "time"} for s in qa["states"]],
                         [{k:v for k,v in s.items() if k != "time"} for s in qb["states"]])

    def test_press_and_rotation_change_ink_while_center_stays_still(self):
        p = self.cases["finish-stop"]["program"]
        phases = list(p.phases)
        phases[2] = replace(phases[2], pressure=(.95, .95), angle=(35,35))
        phases[3] = replace(phases[3], pressure=(.95, .55), angle=(35,35))
        simple = StrokeProgram(tuple(phases))
        a, qa = paint_program(p); b, qb = paint_program(simple)
        self.assertNotEqual(a, b)
        self.assertGreater(qa["ink_area"], qb["ink_area"])
        self.assertEqual(qa["duration"], qb["duration"])
        settle = [s for s in qa["states"] if s["action"] == "settle"]
        self.assertEqual(len({(s["x"],s["y"]) for s in settle}), 1)
        self.assertGreater(settle[-1]["pressure"], settle[0]["pressure"])
        self.assertNotEqual(settle[-1]["angle"], settle[0]["angle"])

    def test_hook_moves_then_lifts_instead_of_only_changing_cap(self):
        hook = self.cases["finish-hook"]["program"]
        states = sample_program(hook)
        flick = [s for s in states if s["action"] == "flick"]
        self.assertLess(flick[-1]["x"], flick[0]["x"])
        self.assertLess(flick[-1]["y"], flick[0]["y"])
        self.assertEqual(flick[-1]["pressure"], 0)
        self.assertEqual(states, sorted(states, key=lambda s:s["time"]))
        self.assertNotEqual(paint_program(hook)[0], paint_program(self.cases["finish-sweep"]["program"])[0])

    def test_air_only_and_second_stroke_or_outside_ink_are_rejected(self):
        pt = ((500,500),)*4
        with self.assertRaises(ValueError): StrokeProgram((StrokePhase("enter",pt,(0,0),(35,35),.2),))
        p = self.cases["entry-direct"]["program"]
        with self.assertRaises(ValueError): StrokeProgram(p.phases+p.phases)
        edge = ((0,0),)*4
        outside = StrokeProgram((StrokePhase("enter",edge,(0,1),(35,35),.2), StrokePhase("lift",edge,(1,0),(35,35),.2)))
        with self.assertRaises(ValueError): paint_program(outside)

    def test_research_exports_controls_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"study"
            report = run_study(self.data, out)
            self.assertEqual(len(report["cells"]), 9)
            self.assertTrue(report["controls"]["duration_only_same_svg"])
            self.assertTrue(report["controls"]["press_turn_changes_svg"])
            self.assertEqual((out/"entry-direct.svg").read_bytes(), (out/"travel-straight.svg").read_bytes())
            for cell in report["cells"]: validate_svg((out/cell["asset"]).read_text())
            with self.assertRaises(ValueError): run_study(self.data, out)
            bad = deepcopy(self.data)
            for phase in bad["cases"][-1]["program"]["phases"]:
                phase["points"] = [[x+480,y] for x,y in phase["points"]]
            failed = Path(tmp)/"failed"
            with self.assertRaises(ValueError): run_study(bad, failed)
            self.assertFalse(failed.exists())
            self.assertFalse(list(Path(tmp).glob(".stroke-study-*")))


if __name__ == "__main__": unittest.main()
