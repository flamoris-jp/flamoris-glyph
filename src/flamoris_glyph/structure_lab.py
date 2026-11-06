"""Static 2-base × 4-design × 2-seed authored 赤 experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

from .bundle import SVG_NS, compile_bundle, write_bundle
from .cli import read_text
from .lyrics import parse_cues
from .structure import AuthoredStructureSource, StructureDNA, PROFILES, ROLES, structure_engine
from .style import StyleDNA


def comparison_sheet(results, seed=42):
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": "0 0 1600 960"})
    ET.SubElement(root, "rect", {"width": "100%", "height": "100%", "fill": "#FAF7F1"})
    def label(text, x, y, size=20, fill="#34312D"):
        ET.SubElement(root, "text", {"x": str(x), "y": str(y), "font-family": "sans-serif",
                                     "font-size": str(size), "fill": fill}).text = text
    label("GLYPH / AUTHORED STRUCTURE STUDY", 36, 44, 29)
    label(f"Actual vector output / seed {seed} / manually authored bases / only one character", 36, 78, 17)
    titles = ["00  ORIGINAL BASE", "01  COMPRESSED IMPACT", "02  EDITORIAL CONTRAST", "03  RETRO SIGNBOARD"]
    for col, title in enumerate(titles):
        label(title, 28+col*400, 125, 18)
    for row, base in enumerate(("gothic", "mincho")):
        y = 152+row*365
        label(f"{base.upper()} / authored base", 32, y+24, 18, "#756D61")
        for col, profile in enumerate(PROFILES):
            m, assets = results[base, profile, seed]
            glyph = m["glyphs"][0]
            group = ET.SubElement(root, "g", {"transform": f"translate({col*400+16} {y+39}) scale(0.35)"})
            for path in ET.fromstring(assets[glyph["asset"]]):
                ET.SubElement(group, "path", {k: v for k, v in path.attrib.items() if k != "id"})
    label("Geometry changes: bar lengths / junction height / lower sweep / stroke contrast / terminals", 36, 914, 18)
    label("Authored experiment, not automatic font decomposition or an AI-image trace. Visual review required.", 36, 943, 15, "#756D61")
    return ET.tostring(root, encoding="unicode")+"\n"


def run_study(data, output):
    if output.exists() or output.is_symlink():
        raise ValueError("Structure study output already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".structure-study-", dir=output.parent))
    results, cells = {}, []
    style = StyleDNA(name="structure-study-neutral", palette=("#171512",), variation=0)
    try:
        for base in ("gothic", "mincho"):
            source = AuthoredStructureSource(data, base)
            for profile in PROFILES:
                for seed in (42, 43):
                    dna = StructureDNA.preset(profile)
                    result = compile_bundle(parse_cues("赤赤"), source, song="Authored structure study",
                                            style=style, structure=dna, seed=seed)
                    repeat = compile_bundle(parse_cues("赤赤"), source, song="Authored structure study",
                                            style=style, structure=dna, seed=seed)
                    if result != repeat:
                        raise ValueError("Structural fixed-seed reproduction failed")
                    m, assets = result
                    write_bundle(stage/f"{base}-{profile}-{seed}", m, assets)
                    results[base, profile, seed] = result
                    qa = m["glyphs"][0]["structure_qa"]
                    cells.append({"base": base, "profile": profile, "seed": seed,
                                  "source": m["source"], "dna": dna.to_dict(),
                                  "sha256": m["glyphs"][0]["sha256"],
                                  "metrics": m["glyphs"][0]["metrics"], "structure_qa": qa})
        for seed in (42, 43):
            (stage/f"comparison-{seed}.svg").write_text(comparison_sheet(results, seed), encoding="utf-8")
        comparisons = []
        for base in ("gothic", "mincho"):
            baseline = results[base, "baseline", 42][0]["glyphs"][0]["structure_qa"]
            for profile in PROFILES[1:]:
                qa = results[base, profile, 42][0]["glyphs"][0]["structure_qa"]
                changed_roles = [role for role in ROLES if qa["landmarks"][role] != baseline["landmarks"][role]]
                h, v = qa["stroke_widths"]["top-bar"][0], qa["stroke_widths"]["top-stem"][0]
                comparisons.append({"base": base, "profile": profile, "changed_centerline_roles": changed_roles,
                                    "horizontal_vertical_ratio": round(h/v, 6),
                                    "main_bar_y": qa["landmarks"]["main-bar"][0][1],
                                    "inner_left_terminal": qa["landmarks"]["inner-left"][-1]})
        report = {"schema_version": 1, "kind": "authored-aka-structure-study", "engine": structure_engine(),
                  "input_sha256": hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                  "fixed_seed_reproduction": True, "cells": cells, "comparisons": comparisons,
                  "visual_review": "required", "limitations": [
                      "Only manually authored seven-role maps for 赤; no automatic font decomposition.",
                      "Two bases model gothic/mincho traits; neither is an extracted existing font.",
                      "AI concept art guided author-chosen rules; no automatic raster tracing or style fitting.",
                      "No claim of complete concept-image matching, full-lyric coverage or target-size legibility."]}
        (stage/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        stage.rename(output)
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_study(json.loads(read_text(args.source)), args.out)
        print(f"Wrote {len(report['cells'])} authored study cells, two comparison sheets; visual review required")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
