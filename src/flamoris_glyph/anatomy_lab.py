"""Reproducible bone/ink ablation study on the two explicit authored 赤 maps."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

from .anatomy import AnatomyDNA, ENGINE, design_glyph
from .bundle import SVG_NS
from .cli import read_text
from .structure import AuthoredStructureSource, ROLES
from .style import digest

STAGES = ("source", "bones", "ink", "full")


def ablations(dna):
    neutral = AnatomyDNA(minimum_gap=dna.minimum_gap)
    return (neutral, replace(neutral, bones=dna.bones), replace(dna, bones=neutral.bones), dna)


def comparison_sheet(cells, guides=False):
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": "0 0 1800 1220"})
    ET.SubElement(root, "rect", {"width": "1800", "height": "1220", "fill": "#FAF7F1"})

    def text(value, x, y, size=20, color="#34312D"):
        ET.SubElement(root, "text", {"x": str(x), "y": str(y), "font-family": "sans-serif",
                                    "font-size": str(size), "fill": color}).text = value

    text("GLYPH / DESIGN THE BONES, THEN GROW THE INK", 40, 54, 32)
    text("One shared DNA / two original authored sources / fixed canvas and color", 40, 91, 20)
    text("Teal: redesigned centerlines; junctions attach to the main bar" if guides else
         "Read left to right: source grammar, bone rules, ink rules, combined design", 40, 126, 18, "#756D61")
    for col, title in enumerate(("00 / SOURCE GRAMMAR", "01 / BONES ONLY", "02 / INK ONLY", "03 / BONES + INK")):
        text(title, 28+col*450, 185, 20)
    for row, family in enumerate(("gothic", "mincho")):
        y = 222+row*460
        text(f"{family.upper()}-LIKE / original authored map", 34, y, 18, "#756D61")
        for col, stage in enumerate(STAGES):
            cell = cells[family, stage]
            group = ET.SubElement(root, "g", {"transform": f"translate({col*450+15} {y+4}) scale(.42)"})
            for path in ET.fromstring(cell["svg"]):
                attrs = {k: v for k, v in path.attrib.items() if k != "id"}
                if guides:
                    attrs["fill"] = "#D6D0C5"
                ET.SubElement(group, "path", attrs)
            if guides:
                for role in ROLES:
                    points = cell["qa"]["landmarks"][role]
                    p = "M "+" ".join(map(str, points[0]))+" C "+" ".join(str(v) for xy in points[1:] for v in xy)
                    ET.SubElement(group, "path", {"d": p, "fill": "none", "stroke": "#168D92", "stroke-width": "4"})
                    for x, yy in (points[0], points[-1]):
                        ET.SubElement(group, "circle", {"cx": str(x), "cy": str(yy), "r": "6", "fill": "#168D92"})
            qa = cell["qa"]
            gap = min(qa["clearances"][r] for r in ("outer-left", "outer-right"))
            text(f"3 silhouettes / outer clearance {gap:.1f}", col*450+28, y+430, 16, "#756D61")
    text("Bone rules: angle, length, bend, position. Ink rules: width distribution, bulge position, side bias, caps.", 40, 1160, 18)
    text("Only explicit maps for this character. Width/taper inheritance is adjustable; source serifs and arbitrary fonts are not reproduced.", 40, 1194, 16, "#756D61")
    return ET.tostring(root, encoding="unicode")+"\n"


def run_study(data, dna, output):
    if output.exists() or output.is_symlink():
        raise ValueError("Anatomy study output already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=".anatomy-study-", dir=output.parent))
    cells, records = {}, []
    try:
        for family in ("gothic", "mincho"):
            source = AuthoredStructureSource(data, family)
            for stage, rules in zip(STAGES, ablations(dna)):
                svg, qa = design_glyph(source, rules)
                if (svg, qa) != design_glyph(source, rules):
                    raise ValueError("Anatomy study reproduction failed")
                cells[family, stage] = {"svg": svg, "qa": qa}
                filename = f"{family}-{stage}.svg"
                (stage_dir/filename).write_text(svg, encoding="utf-8")
                records.append({"family": family, "stage": stage, "asset": filename,
                                "dna": rules.to_dict(), "qa": qa})
        # A second controlled experiment: same bones/ink, only source width
        # and taper inheritance changes. Geometry remains source-dependent.
        inheritance = []
        for mix in (0, .5, 1):
            rules = replace(dna, source_width_mix=mix, source_taper_mix=mix)
            for family in ("gothic", "mincho"):
                svg, qa = design_glyph(AuthoredStructureSource(data, family), rules)
                filename = f"{family}-inherit-{mix:g}.svg"
                (stage_dir/filename).write_text(svg, encoding="utf-8")
                inheritance.append({"family": family, "mix": mix, "asset": filename, "qa": qa})
        report = {"schema_version": 1, "kind": ENGINE, "source_sha256": digest(data),
                  "dna": dna.to_dict(), "cells": records, "inheritance": inheritance,
                  "fixed_input_reproduction": True, "review_status": "pending-human-visual-review",
                  "limits": ["Only authored 赤; no automatic font/raster decomposition.",
                             "No image-fitting objective or proof of beauty/style generalization.",
                             "Explicit junction attachment; clearance violations reject rather than auto-correct.",
                             "Standalone SVG study; not a new occurrence bundle format.",
                             "Source serifs are not reproduced; width/taper inheritance only."]}
        (stage_dir/"comparison.svg").write_text(comparison_sheet(cells), encoding="utf-8")
        (stage_dir/"bones.svg").write_text(comparison_sheet(cells, guides=True), encoding="utf-8")
        (stage_dir/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        stage_dir.rename(output)
        return report
    finally:
        if stage_dir.exists():
            shutil.rmtree(stage_dir)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("dna", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_study(json.loads(read_text(args.source)), AnatomyDNA.from_dict(json.loads(read_text(args.dna))), args.out)
        print(f"Wrote {len(report['cells'])} ablations and {len(report['inheritance'])} inheritance controls; visual review pending")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
