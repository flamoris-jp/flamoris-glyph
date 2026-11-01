"""Compare authored skeleton patterns while holding all ink DNA fields fixed."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

from .anatomy import AnatomyDNA, BoneRule, ENGINE, design_glyph
from .bundle import SVG_NS
from .cli import read_text
from .structure import AuthoredStructureSource, ROLES
from .style import digest

KIND = "authored-skeleton-patterns-1"


def parse_patterns(data, shared_dna):
    if (not isinstance(data, dict) or set(data) != {"schema_version", "kind", "patterns"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["kind"] != KIND
            or not isinstance(data["patterns"], list) or not 1 <= len(data["patterns"]) <= 9):
        raise ValueError("Expected skeleton pattern schema 1, with 1..9 patterns")
    if type(shared_dna) is not AnatomyDNA:
        raise ValueError("Expected shared AnatomyDNA")
    seen, result = set(), []
    for entry in data["patterns"]:
        if not isinstance(entry, dict) or set(entry) != {"id", "title", "note", "bones"}:
            raise ValueError("Each pattern requires id, title, note and bones")
        key = entry["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", key) or key in seen:
            raise ValueError("Pattern IDs must be unique lowercase path-safe names")
        seen.add(key)
        for field, limit in (("title", 32), ("note", 54)):
            value = entry[field]
            if not isinstance(value, str) or not 1 <= len(value) <= limit or not value.isprintable():
                raise ValueError("Pattern labels must be short printable strings")
        bones = entry["bones"]
        if not isinstance(bones, dict) or set(bones) != set(ROLES):
            raise ValueError("Pattern requires all seven explicit bone roles")
        for rule in bones.values():
            if not isinstance(rule, dict) or set(rule) != set(BoneRule.__dataclass_fields__):
                raise ValueError("Pattern bone fields must be complete and exact")
        dna = replace(shared_dna, bones=tuple(BoneRule(**bones[r]) for r in ROLES))
        result.append({"id": key, "title": entry["title"], "note": entry["note"], "dna": dna})
    return result


def ink_identity(dna):
    data = dna.to_dict()
    data["roles"] = {r: value["ink"] for r, value in data["roles"].items()}
    return digest(data)


def comparison_sheet(cells, family, guides=False):
    rows = (len(cells)+2)//3
    height = 210+rows*480
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": f"0 0 1350 {height}"})
    ET.SubElement(root, "rect", {"width": "1350", "height": str(height), "fill": "#FAF7F1"})

    def text(value, x, y, size=20, color="#34312D"):
        ET.SubElement(root, "text", {"x": str(x), "y": str(y), "font-family": "sans-serif",
                                    "font-size": str(size), "fill": color}).text = value

    text("GLYPH / SKELETON VARIATIONS", 34, 48, 32)
    text(f"{family.upper()}-LIKE authored source / same ink DNA, weight and canvas", 34, 85, 20)
    text("Teal: centerlines and endpoints" if guides else
         "Only bone rules change: angle, length, bend, position and terminal direction", 34, 116, 18, "#756D61")
    for i, cell in enumerate(cells):
        x, y = (i%3)*450, 150+(i//3)*480
        text(cell["title"], x+28, y+28, 23)
        text(cell["note"], x+28, y+56, 15, "#756D61")
        group = ET.SubElement(root, "g", {"transform": f"translate({x+15} {y+65}) scale(.42)"})
        for path in ET.fromstring(cell["svg"]):
            attrs = {k: v for k, v in path.attrib.items() if k != "id"}
            if guides:
                attrs["fill"] = "#D6D0C5"
            ET.SubElement(group, "path", attrs)
        if guides:
            for role in ROLES:
                points = cell["qa"]["landmarks"][role]
                d = "M "+" ".join(map(str, points[0]))+" C "+" ".join(str(v) for p in points[1:] for v in p)
                ET.SubElement(group, "path", {"d": d, "fill": "none", "stroke": "#168D92", "stroke-width": "4"})
                for xx, yy in (points[0], points[-1]):
                    ET.SubElement(group, "circle", {"cx": str(xx), "cy": str(yy), "r": "6", "fill": "#168D92"})
    text("All designs retain the body and two detached marks. No per-cell resizing or optical auto-correction.", 34, height-28, 17, "#756D61")
    return ET.tostring(root, encoding="unicode")+"\n"


def run_study(source_data, shared_dna, pattern_data, output):
    patterns = parse_patterns(pattern_data, shared_dna)
    if output.exists() or output.is_symlink():
        raise ValueError("Skeleton study output already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".skeleton-study-", dir=output.parent))
    records, sheets = [], {}
    shared_ink = ink_identity(shared_dna)
    try:
        (stage/"dna").mkdir()
        for pattern in patterns:
            (stage/"dna"/(pattern["id"]+".json")).write_text(
                json.dumps(pattern["dna"].to_dict(), indent=2)+"\n", encoding="utf-8")
        for family in ("gothic", "mincho"):
            source = AuthoredStructureSource(source_data, family)
            cells, sampled_widths = [], None
            for pattern in patterns:
                dna = pattern["dna"]
                if ink_identity(dna) != shared_ink:
                    raise ValueError("Skeleton study changed an ink field")
                svg, qa = design_glyph(source, dna)
                if (svg, qa) != design_glyph(source, dna):
                    raise ValueError("Skeleton study fixed-input reproduction failed")
                if sampled_widths is not None and qa["width_stations"] != sampled_widths:
                    raise ValueError("Skeleton study changed sampled ink widths")
                sampled_widths = qa["width_stations"]
                filename = f"{family}-{pattern['id']}.svg"
                (stage/filename).write_text(svg, encoding="utf-8")
                cells.append({**pattern, "svg": svg, "qa": qa})
                records.append({"family": family, "pattern": pattern["id"], "asset": filename,
                                "dna_asset": f"dna/{pattern['id']}.json", "qa": qa})
            for guides in (False, True):
                filename = f"{family}-{'bones' if guides else 'comparison'}.svg"
                (stage/filename).write_text(comparison_sheet(cells, family, guides), encoding="utf-8")
            sheets[family] = [f"{family}-comparison.svg", f"{family}-bones.svg"]
        report = {"schema_version": 1, "kind": KIND, "engine": ENGINE,
                  "source_sha256": digest(source_data), "shared_dna_sha256": digest(shared_dna.to_dict()),
                  "pattern_sha256": digest(pattern_data), "fixed_ink_sha256": shared_ink,
                  "changed_layers": ["bones"], "fixed_input_reproduction": True,
                  "patterns": [{"id": p["id"], "title": p["title"], "note": p["note"]} for p in patterns],
                  "cells": records, "sheets": sheets, "visual_review": "required",
                  "limits": ["Only manually authored 赤 maps; no font decomposition or other-character coverage.",
                             "Several bone parameters change per pattern; not a single-variable causal experiment.",
                             "Ink settings and local width samples are fixed; occupied area and apparent weight can change.",
                             "Clearances reject invalid layouts; no optical automatic correction or aesthetic ranking."]}
        for filename, value in (("report.json", report), ("source.json", source_data),
                                ("shared-dna.json", shared_dna.to_dict()), ("patterns.json", pattern_data)):
            (stage/filename).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        stage.rename(output)
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("dna", type=Path)
    parser.add_argument("patterns", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_study(json.loads(read_text(args.source)), AnatomyDNA.from_dict(json.loads(read_text(args.dna))),
                           json.loads(read_text(args.patterns)), args.out)
        print(f"Wrote {len(report['cells'])} skeleton designs with fixed ink and four review sheets")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
