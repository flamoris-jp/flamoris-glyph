"""Nine hand-authored single-stroke comparisons: entry, travel and finish."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

from .bundle import SVG_NS
from .cli import read_text
from .stroke_program import StrokeProgram, paint_program
from .style import digest, number

IDS = ("entry-direct", "entry-angled", "entry-return", "travel-straight", "travel-up", "travel-down",
       "finish-stop", "finish-sweep", "finish-hook")
COLORS = {"enter": "#168D92", "travel": "#545B62", "settle": "#BE8A24", "collect": "#BC5F78",
          "release": "#3F9767", "flick": "#8464B0", "lift": "#8A9196"}


def parse_study(data):
    if (not isinstance(data, dict) or set(data) != {"schema_version", "kind", "width", "aspect", "cases"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or data["kind"] != "stroke-program-study-1" or not isinstance(data["cases"], list) or len(data["cases"]) != 9):
        raise ValueError("Expected nine-case stroke-program study schema 1")
    number(data["width"], "width", 8, 120); number(data["aspect"], "aspect", .1, 1)
    cases = {}
    for case in data["cases"]:
        if not isinstance(case, dict) or set(case) != {"id", "title", "group", "program"}:
            raise ValueError("Expected id, title, group and program")
        key = case["id"]
        if not isinstance(key, str) or key not in IDS or key in cases or case["group"] != key.split("-")[0]:
            raise ValueError("Expected unique documented case IDs and matching groups")
        if not isinstance(case["title"], str) or not 1 <= len(case["title"]) <= 32 or not case["title"].isprintable():
            raise ValueError("Expected short printable case title")
        cases[key] = {**case, "program": StrokeProgram.from_dict(case["program"])}
    return [cases[key] for key in IDS]


def _root(width, height):
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": f"0 0 {width} {height}"})
    ET.SubElement(root, "rect", {"width": str(width), "height": str(height), "fill": "#FAF7F1"})
    return root


def _text(root, value, x, y, size=20, color="#34312D"):
    ET.SubElement(root, "text", {"x": str(x), "y": str(y), "font-family": "sans-serif",
                                "font-size": str(size), "fill": color}).text = value


def _glyph(root, svg, x, y, width, height, viewbox):
    nested = ET.SubElement(root, "svg", {"x": str(x), "y": str(y), "width": str(width), "height": str(height),
                                        "viewBox": viewbox, "overflow": "hidden"})
    for path in ET.fromstring(svg):
        ET.SubElement(nested, "path", {k: v for k, v in path.attrib.items() if k != "id"})
    return nested


def comparison_sheet(cells):
    root = _root(1350, 1130)
    _text(root, "GLYPH / THE ACTIONS INSIDE ONE STROKE", 32, 47, 31)
    _text(root, "Same nominal width and nib / hand-authored programs / phase-specific paths, pressure and angle", 32, 86, 18)
    for row, (label, note, box, height) in enumerate((
            ("ENTRY", "Same horizontal body; close-up of the entry", "180 420 200 160", 170),
            ("TRAVEL", "Same endpoints and width; change the bow", "180 390 640 220", 170),
            ("FINISH", "Same vertical body; change the finishing actions", "320 150 360 680", 290))):
        y = 130+row*280
        _text(root, f"{row+1} / {label}", 32, y+20, 24)
        _text(root, note, 255, y+20, 17, "#756D61")
        for col in range(3):
            cell = cells[IDS[row*3+col]]
            _text(root, cell["title"], col*450+26, y+62, 20)
            _glyph(root, cell["svg"], col*450+20, y+78, 410, height, box)
    _text(root, "Shared crop and scale within each row. Entry detail is enlarged; rows are not a size comparison.", 32, 1068, 17, "#756D61")
    _text(root, "Geometric motion hypotheses; no traditional-calligraphy accuracy or learned-model claim.", 32, 1100, 16, "#756D61")
    return ET.tostring(root, encoding="unicode")+"\n"


def process_sheet(cells):
    root = _root(1350, 920)
    _text(root, "GLYPH / FINISHING IS A SEQUENCE OF ACTIONS", 32, 47, 31)
    _text(root, "Top: contact-center path / bottom: pressure over arbitrary time units", 32, 86, 19)
    finish = [cells[key] for key in IDS[6:]]
    max_time = max(c["qa"]["duration"] for c in finish)
    for col, cell in enumerate(finish):
        x = col*450
        _text(root, cell["title"], x+27, 139, 21)
        viewport = _glyph(root, cell["svg"], x+24, 170, 400, 380, "320 150 360 680")
        for path in list(viewport): path.set("fill", "#D6D0C5")
        for index, phase in enumerate(cell["program"].phases):
            points = phase.points
            d = "M "+" ".join(map(str, points[0]))+" C "+" ".join(str(v) for p in points[1:] for v in p)
            ET.SubElement(viewport, "path", {"d": d, "fill": "none", "stroke": COLORS[phase.action], "stroke-width": "4"})
            xx, yy = points[-1]
            ET.SubElement(viewport, "circle", {"cx": str(xx), "cy": str(yy), "r": "5", "fill": COLORS[phase.action]})
        _text(root, "PRESSURE", x+38, 598, 16)
        chart_x, chart_y, chart_w, chart_h = x+55, 630, 340, 130
        ET.SubElement(root, "path", {"d": f"M {chart_x} {chart_y} V {chart_y+chart_h} H {chart_x+chart_w}",
                                    "fill": "none", "stroke": "#AAA69D", "stroke-width": "1"})
        _text(root, "1.5", chart_x-30, chart_y+6, 13, "#756D61")
        _text(root, "0", chart_x-17, chart_y+chart_h+5, 13, "#756D61")
        _text(root, "0", chart_x, chart_y+chart_h+27, 13, "#756D61")
        _text(root, "time", chart_x+chart_w/2-15, chart_y+chart_h+27, 13, "#756D61")
        _text(root, f"{max_time:g}", chart_x+chart_w-7, chart_y+chart_h+27, 13, "#756D61")
        for index, phase in enumerate(cell["program"].phases):
            states = [s for s in cell["qa"]["states"] if s["phase"] == index]
            points = " ".join(f"{chart_x+s['time']/max_time*chart_w:.3f},{chart_y+chart_h-s['pressure']/1.5*chart_h:.3f}" for s in states)
            ET.SubElement(root, "polyline", {"points": points, "fill": "none", "stroke": COLORS[phase.action], "stroke-width": "3"})
    for i, (action, color) in enumerate(COLORS.items()): _text(root, action, 35+i*184, 850, 18, color)
    _text(root, "Duration alone leaves static ink unchanged here. Pressing, turning and moving alter the footprint sequence.", 32, 894, 16, "#756D61")
    return ET.tostring(root, encoding="unicode")+"\n"


def run_study(data, output):
    cases = parse_study(data)
    if output.exists() or output.is_symlink(): raise ValueError("Stroke study output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stroke-study-", dir=output.parent))
    cells, records = {}, []
    try:
        (stage/"programs").mkdir()
        for case in cases:
            svg, qa = paint_program(case["program"], data["width"], data["aspect"])
            if (svg, qa) != paint_program(case["program"], data["width"], data["aspect"]):
                raise ValueError("Stroke program reproduction failed")
            (stage/(case["id"]+".svg")).write_text(svg, encoding="utf-8")
            (stage/"programs"/(case["id"]+".json")).write_text(json.dumps(case["program"].to_dict(), indent=2)+"\n", encoding="utf-8")
            cells[case["id"]] = {**case, "svg": svg, "qa": qa}
            records.append({"id": case["id"], "title": case["title"], "group": case["group"],
                            "ancestry_group": "vertical-spine" if case["group"] == "finish" else "horizontal-spine",
                            "asset": case["id"]+".svg", "qa": qa})
        stop = cells["finish-stop"]
        phases = list(stop["program"].phases)
        phases[2] = replace(phases[2], duration=phases[2].duration*4)
        slower = StrokeProgram(tuple(phases))
        slow_svg, slow_qa = paint_program(slower, data["width"], data["aspect"])
        if slow_svg != stop["svg"] or slow_qa["duration"] == stop["qa"]["duration"]:
            raise ValueError("Duration-only control did not isolate time from static ink")
        phases = list(stop["program"].phases)
        phases[2] = replace(phases[2], pressure=(.95, .95), angle=(35, 35))
        phases[3] = replace(phases[3], pressure=(.95, .55), angle=(35, 35))
        plain = StrokeProgram(tuple(phases))
        plain_svg, plain_qa = paint_program(plain, data["width"], data["aspect"])
        if plain_svg == stop["svg"]: raise ValueError("Press/turn control failed to change static ink")
        for name, program, svg in (("duration-only", slower, slow_svg), ("without-press-turn", plain, plain_svg)):
            (stage/(name+".svg")).write_text(svg, encoding="utf-8")
            (stage/"programs"/(name+".json")).write_text(json.dumps(program.to_dict(), indent=2)+"\n", encoding="utf-8")
        report = {"schema_version": 1, "kind": "stroke-program-study-1", "input_sha256": digest(data),
                  "width": data["width"], "aspect": data["aspect"], "cells": records,
                  "controls": {"duration_only_same_svg": True, "original_duration": stop["qa"]["duration"],
                               "longer_duration": slow_qa["duration"], "press_turn_changes_svg": True,
                               "with_press_turn_area": stop["qa"]["ink_area"], "without_press_turn_area": plain_qa["ink_area"]},
                  "fixed_input_reproduction": True, "teacher_labels": "not-established", "human_review": "pending",
                  "limits": ["Hand-authored hypotheses, not a learned model or canonical brush instruction.",
                             "Single-stroke dictionary; not integrated into the full-character renderer.",
                             "No viscosity, ink accumulation, hair deformation or speed-to-width physics.",
                             "Phase action labels annotate explicit motion templates; labels alone do not generate expert motions."]}
        (stage/"comparison.svg").write_text(comparison_sheet(cells), encoding="utf-8")
        (stage/"process.svg").write_text(process_sheet(cells), encoding="utf-8")
        (stage/"report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
        (stage/"input.json").write_text(json.dumps(data, indent=2)+"\n", encoding="utf-8")
        stage.rename(output)
        return report
    finally:
        if stage.exists(): shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path); parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_study(json.loads(read_text(args.study)), args.out)
        print(f"Wrote {len(report['cells'])} single-stroke cases and two explicit controls")
    except (ValueError, OSError, KeyError, TypeError) as error: parser.error(str(error))


if __name__ == "__main__": main()
