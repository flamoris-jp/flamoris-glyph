"""Factorial study: two authored skeletons × two DNA intents × three tools."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

from .anatomy import AnatomyDNA
from .bundle import SVG_NS
from .calligraphy import ENGINE, CalligraphyTool, LetterDNA, SkeletonPlan, draw_glyph
from .cli import read_text
from .skeleton_lab import parse_patterns
from .structure import AuthoredStructureSource
from .style import digest

KIND = "calligraphy-study-1"


def parse_study(data):
    if (not isinstance(data, dict) or set(data) != {"schema_version", "kind", "family", "skeletons", "dnas", "tools"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or data["kind"] != KIND or data["family"] not in {"gothic", "mincho"}
            or not isinstance(data["skeletons"], list) or not 1 <= len(data["skeletons"]) <= 4):
        raise ValueError("Expected exact calligraphy study schema 1")
    skeletons = parse_patterns({"schema_version": 1, "kind": "authored-skeleton-patterns-1",
                               "patterns": data["skeletons"]}, AnatomyDNA())
    axes = []
    for field, limit, key, cls in (("dnas", 4, "dna", LetterDNA), ("tools", 3, "tool", CalligraphyTool)):
        entries = data[field]
        if not isinstance(entries, list) or not 1 <= len(entries) <= limit:
            raise ValueError(f"Expected 1..{limit} {field}")
        seen, result = set(), []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"id", "title", key}:
                raise ValueError(f"Expected id, title and {key}")
            name, title = entry["id"], entry["title"]
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", name) or name in seen:
                raise ValueError("Axis IDs must be unique and path-safe")
            if not isinstance(title, str) or not 1 <= len(title) <= 32 or not title.isprintable():
                raise ValueError("Axis title must be a short printable string")
            seen.add(name)
            result.append({"id": name, "title": title, key: cls.from_dict(entry[key])})
        axes.append(result)
    return skeletons, axes[0], axes[1]


def comparison_sheet(skeleton, dnas, tools, cells, guides=False):
    width, height = 450*len(tools), 200+480*len(dnas)
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": f"0 0 {width} {height}"})
    ET.SubElement(root, "rect", {"width": str(width), "height": str(height), "fill": "#FAF7F1"})

    def text(value, x, y, size=20, color="#34312D"):
        ET.SubElement(root, "text", {"x": str(x), "y": str(y), "font-family": "sans-serif",
                                    "font-size": str(size), "fill": color}).text = value

    text("GLYPH / SKELETON + DNA + CALLIGRAPHY", 32, 45, 29)
    text(f"Skeleton: {skeleton['id'].upper()} / each row shares one DNA / each column changes the drawing tool", 32, 82, 18)
    text("Teal: identical centerlines in every cell" if guides else
         "Round nib: direction independent / broad nib: fixed angle / brush: stylized pressure", 32, 113, 17, "#756D61")
    for col, tool in enumerate(tools): text(tool["title"], col*450+25, 157, 21)
    for row, dna in enumerate(dnas):
        y = 185+480*row
        text(dna["title"], 26, y, 17, "#756D61")
        for col, tool in enumerate(tools):
            cell = cells[dna["id"], tool["id"]]
            group = ET.SubElement(root, "g", {"transform": f"translate({col*450+15} {y+8}) scale(.42)"})
            for path in ET.fromstring(cell["svg"]):
                attrs = {k: v for k, v in path.attrib.items() if k != "id"}
                if guides: attrs["fill"] = "#D6D0C5"
                ET.SubElement(group, "path", attrs)
            if guides:
                for points in cell["qa"]["landmarks"].values():
                    d = "M "+" ".join(map(str, points[0]))+" C "+" ".join(str(v) for p in points[1:] for v in p)
                    ET.SubElement(group, "path", {"d": d, "fill": "none", "stroke": "#168D92", "stroke-width": "4"})
    text("Virtual geometric tools, not a physical brush or a traditional calligraphy reproduction. Only authored maps for this character.",
         32, height-26, 16, "#756D61")
    return ET.tostring(root, encoding="unicode")+"\n"


def run_study(source_data, data, output):
    skeletons, dnas, tools = parse_study(data)
    source = AuthoredStructureSource(source_data, data["family"])
    if output.exists() or output.is_symlink():
        raise ValueError("Calligraphy study output already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".calligraphy-study-", dir=output.parent))
    records, plans = [], {}
    try:
        for folder in ("plans", "dnas", "tools", "glyphs"): (stage/folder).mkdir()
        for axis, entries, key in (("dnas", dnas, "dna"), ("tools", tools, "tool")):
            for item in entries:
                (stage/axis/(item["id"]+".json")).write_text(json.dumps(item[key].to_dict(), indent=2)+"\n", encoding="utf-8")
        for skeleton in skeletons:
            plan = SkeletonPlan.from_source(source, skeleton["dna"].bones)
            plans[skeleton["id"]] = digest(plan.to_dict())
            (stage/"plans"/(skeleton["id"]+".json")).write_text(json.dumps(plan.to_dict(), indent=2)+"\n", encoding="utf-8")
            cells = {}
            for dna in dnas:
                for tool in tools:
                    svg, qa = draw_glyph(plan, dna["dna"], tool["tool"])
                    if (svg, qa) != draw_glyph(plan, dna["dna"], tool["tool"]):
                        raise ValueError("Calligraphy fixed-input reproduction failed")
                    if (qa["plan_sha256"] != plans[skeleton["id"]] or qa["dna_sha256"] != digest(dna["dna"].to_dict())
                            or qa["tool_sha256"] != digest(tool["tool"].to_dict())):
                        raise ValueError("Independent input identity mismatch")
                    relative = Path("glyphs")/skeleton["id"]/dna["id"]/(tool["id"]+".svg")
                    (stage/relative).parent.mkdir(parents=True, exist_ok=True)
                    (stage/relative).write_text(svg, encoding="utf-8")
                    cells[dna["id"], tool["id"]] = {"svg": svg, "qa": qa}
                    records.append({"skeleton": skeleton["id"], "dna": dna["id"], "tool": tool["id"],
                                    "asset": relative.as_posix(), "qa": qa})
            for guides in (False, True):
                name = f"{skeleton['id']}-{'bones' if guides else 'comparison'}.svg"
                (stage/name).write_text(comparison_sheet(skeleton, dnas, tools, cells, guides), encoding="utf-8")
        report = {"schema_version": 1, "kind": KIND, "engine": ENGINE, "source_sha256": digest(source_data),
                  "study_sha256": digest(data), "plans": plans, "cells": records,
                  "fixed_input_reproduction": True, "three_independent_inputs": True, "visual_review": "required",
                  "limits": ["Only authored 赤; no automatic font/raster decomposition.",
                             "Elliptical geometric footprints, not physical brush/hair/ink simulation.",
                             "Pressure is hand-assigned over normalized arc length; speed and stroke order are not inferred.",
                             "Tool changes alter projected widths and clearances even with identical design intent.",
                             "No optical spacing correction, traditional calligraphy fidelity or aesthetic acceptance claim."]}
        for name, value in (("source.json", source_data), ("study.json", data), ("report.json", report)):
            (stage/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        stage.rename(output)
        return report
    finally:
        if stage.exists(): shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("study", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_study(json.loads(read_text(args.source)), json.loads(read_text(args.study)), args.out)
        print(f"Wrote {len(report['cells'])} skeleton/DNA/tool combinations and four review sheets")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__": main()
