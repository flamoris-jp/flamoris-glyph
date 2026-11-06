"""Static experiment matrix and review sheets, not an animation renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

from fontTools.ttLib import TTLibError

from .bundle import SVG_NS, compile_bundle, write_bundle
from .cli import read_text
from .font_library import resolve_local_font
from .geometry import FontSource, SkeletonSource
from .lyrics import parse_cues
from .pattern import PatternDNA, PRESETS, engine_metadata
from .style import StyleDNA


def _sheet(bundles, labels, *, max_items=96):
    # Each row is one physical cue. Source whitespace/columns survive; a wide
    # cue wraps only in the review sheet, never in the portable cue contract.
    manifests = [m for m, _ in bundles]
    first = manifests[0]
    rows = []
    for cue in first["cues"]:
        items = [o for o in first["occurrences"][:max_items] if o["cue_id"] == cue["id"]]
        for start in range(0, max((o["column"] for o in items), default=0), 12):
            rows.append([o for o in items if start < o["column"] <= start+12])
    width, row_height = 620, 104
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": f"0 0 {width*len(bundles)} {110+row_height*len(rows)}"})
    ET.SubElement(root, "rect", {"width": "100%", "height": "100%", "fill": "#F7F2E8"})
    for col, ((m, assets), label) in enumerate(zip(bundles, labels)):
        ET.SubElement(root, "text", {"x": str(col*width+24), "y": "34", "font-family": "sans-serif",
                                     "font-size": "17", "fill": "#252525"}).text = label
        ET.SubElement(root, "text", {"x": str(col*width+24), "y": "59", "font-family": "sans-serif",
                                     "font-size": "13", "fill": "#777777"}).text = "seed " + str(m["seed"]) + " / visual review required"
        mapping = {o["occurrence_id"]: o for o in m["occurrences"]}
        glyphs = {g["variant_id"]: g for g in m["glyphs"]}
        for row, items in enumerate(rows):
            if not items:
                continue
            start = ((items[0]["column"]-1)//12)*12
            for item in items:
                g = glyphs[mapping[item["occurrence_id"]]["glyph_variant_id"]]
                x = col*width + 10 + (item["column"]-start-1)*50
                group = ET.SubElement(root, "g", {"transform": f"translate({x} {84+row*row_height}) scale(0.05)"})
                for p in ET.fromstring(assets[g["asset"]]):
                    ET.SubElement(group, "path", {k:v for k,v in p.attrib.items() if k != "id"})
                qa = g.get("pattern_qa")
                if qa and qa["warnings"]:
                    ET.SubElement(root, "circle", {"cx": str(x+25), "cy": str(142+row*row_height), "r": "3", "fill": "#BC6338"})
    return ET.tostring(root, encoding="unicode") + "\n"


def _detail_sheet(results, seeds):
    """First six occurrences enlarged; columns compare seeds, rows compare DNA."""
    root=ET.Element("svg", {"xmlns":SVG_NS,"viewBox":"0 0 1300 900"})
    ET.SubElement(root,"rect",{"width":"100%","height":"100%","fill":"#F7F2E8"})
    for col,seed in enumerate(seeds):
        ET.SubElement(root,"text",{"x":str(col*650+24),"y":"36","font-family":"sans-serif",
                                   "font-size":"22","fill":"#252525"}).text=f"Pattern DNA / seed {seed}"
        for row,profile in enumerate(["baseline",*PRESETS]):
            y=72+row*205
            ET.SubElement(root,"text",{"x":str(col*650+24),"y":str(y+24),"font-family":"sans-serif",
                                       "font-size":"18","fill":"#555555"}).text=profile
            m,assets=results[profile,seed]
            glyphs={g["variant_id"]:g for g in m["glyphs"]}
            for i,item in enumerate(m["occurrences"][:6]):
                x=col*650+24+i*96
                g=glyphs[item["glyph_variant_id"]]
                group=ET.SubElement(root,"g",{"transform":f"translate({x} {y+44}) scale(0.096)"})
                for p in ET.fromstring(assets[g["asset"]]):
                    ET.SubElement(group,"path",{k:v for k,v in p.attrib.items() if k!="id"})
                if g.get("pattern_qa",{}).get("warnings"):
                    ET.SubElement(root,"circle",{"cx":str(x+48),"cy":str(y+155),"r":"4","fill":"#BC6338"})
    return ET.tostring(root,encoding="unicode")+"\n"


def run_lab(cues, source, output, *, seeds=(42, 43)):
    if output.exists() or output.is_symlink():
        raise ValueError("Lab output already exists; choose a new directory")
    if not 1 <= len(cues) <= 96:
        raise ValueError("Lab requires 1..96 cues")
    from .lyrics import occurrences
    if not 1 <= len(occurrences(cues)) <= 96:
        raise ValueError("Lab sheets support 1..96 visible occurrences; split larger inputs")
    if len(seeds) != 2 or seeds[0] == seeds[1]:
        raise ValueError("Lab needs two distinct seeds")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".pattern-lab-", dir=output.parent))
    try:
        results, summary = {}, []
        style = StyleDNA(name="pattern-lab-neutral", palette=("#222222",), variation=0, stroke_width=28)
        for seed in seeds:
            for profile in ["baseline", *PRESETS]:
                pattern = None if profile == "baseline" else PatternDNA.preset(profile)
                m, assets = compile_bundle(cues, source, song="Pattern DNA lab", style=style, seed=seed, pattern=pattern)
                # Independent compile comparison catches in-process state drift.
                if (m, assets) != compile_bundle(cues, source, song="Pattern DNA lab", style=style, seed=seed, pattern=pattern):
                    raise ValueError("Fixed seed reproduction failed")
                results[profile, seed] = (m, assets)
                write_bundle(stage / f"{profile}-{seed}", m, assets)
                summary.append({"profile":profile, "seed":seed, "occurrences":len(m["occurrences"]),
                                "asset_digest":hashlib.sha256(json.dumps(assets,sort_keys=True).encode()).hexdigest(),
                                "warnings":[{"variant_id":g["variant_id"],"character":g["character"],**g["pattern_qa"]}
                                            for g in m["glyphs"] if g.get("pattern_qa",{}).get("warnings")]})
        for seed in seeds:
            profiles = ["baseline", *PRESETS]
            (stage / f"comparison-{seed}.svg").write_text(_sheet([results[p,seed] for p in profiles],profiles),encoding="utf-8")
        for p in ["baseline", *PRESETS]:
            (stage / f"{p}-seeds.svg").write_text(_sheet([results[p,s] for s in seeds],[p,p]),encoding="utf-8")
        (stage / "detail.svg").write_text(_detail_sheet(results,seeds),encoding="utf-8")
        report = {"schema_version":1,"engine":engine_metadata(),"source":source.provenance,
                  "cue_count":len(cues),"input_sha256":hashlib.sha256(json.dumps([c.__dict__ for c in cues],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
                  "fixed_seed_reproduction":True,"matrix":summary,"visual_review":"required",
                  "limitations":["Outline morphology does not infer strokes, radicals or terminals; no new serifs.",
                                 "Topology checks do not prove legibility or fine-line survival at 1080p.",
                                 "Adaptive curve flattening tolerance is 0.35 design units; curves become polygons.",
                                 "A warning dot means strength was reduced or the pattern was rejected."]}
        (stage / "report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        stage.rename(output)
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lyrics", type=Path)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--font", type=Path)
    inputs.add_argument("--font-id")
    inputs.add_argument("--skeletons", type=Path)
    parser.add_argument("--font-library",type=Path,default=Path("lib/fonts"))
    parser.add_argument("--source-license")
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args(argv)
    source = None
    try:
        if args.skeletons:
            source = SkeletonSource(json.loads(read_text(args.skeletons)))
        else:
            if args.font_id:
                if args.source_license is not None:
                    raise ValueError("Use --source-license only with --font")
                font, note = resolve_local_font(args.font_id,args.font_library)
            else:
                font, note = args.font,args.source_license
            if font.stat().st_size > 50_000_000:
                raise ValueError("Font exceeds 50 MB limit")
            source = FontSource(font,license_note=note)
        report = run_lab(parse_cues(read_text(args.lyrics),srt=args.lyrics.suffix.lower()==".srt"),source,args.out)
        print(f"Wrote baseline + 3 DNA profiles, seeds 42/43; {report['cue_count']} cues; visual review required")
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError, TTLibError, NotImplementedError) as error:
        parser.error(str(error))
    finally:
        if source is not None:
            source.close()


if __name__ == "__main__":
    main()
