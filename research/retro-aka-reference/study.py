"""Reproduce a reference-led shape study. Scores describe geometry, not beauty.

Uses checked-in masks/vectors. It does not trace new images or infer strokes.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import cairosvg
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent
NS = "http://www.w3.org/2000/svg"


def raster(svg, size=1000):
    data = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size,
                           background_color="#ffffff")
    return np.asarray(Image.open(io.BytesIO(data)).convert("L")) < 128


def load_mask():
    data = json.loads((ROOT/"reference-mask.json").read_text())
    a = np.zeros((data["height"], data["width"]), dtype=bool)
    for y, runs in enumerate(data["runs"]):
        for x0, x1 in runs:
            a[y, x0:x1] = True
    return a


def iou(a, b):
    return float((a & b).sum()/(a | b).sum())


def bounds(a):
    y, x = np.where(a)
    return [int(x.min()), int(y.min()), int(x.max()+1), int(y.max()+1)]


def runs(a):
    edges = np.flatnonzero(np.diff(np.r_[False, a, False].astype(int)))
    return [(int(edges[i]), int(edges[i+1])) for i in range(0, len(edges), 2)]


def metrics(a):
    x0, y0, x1, y1 = bounds(a)
    w, h = x1-x0, y1-y0
    labels, count = ndi.label(a, structure=np.ones((3, 3)))
    areas = sorted(np.bincount(labels.ravel())[1:].tolist(), reverse=True)
    # These sections were explicitly selected for THIS glyph. They are not
    # automatic semantic stroke recognition and must not be generalized blindly.
    section = {}
    for name, xf in (("left_end", .22), ("left_neck", .40), ("gap_probe", .30)):
        x = x0+round(w*xf)
        scan = a[y0+round(h*.12):y0+round(h*.56), x]
        found = runs(scan)
        section[name] = {"x_fraction": xf, "runs_height_fraction": [
            [(lo+round(h*.12))/h, (hi+round(h*.12))/h] for lo, hi in found]}
    first = lambda name: (section[name]["runs_height_fraction"][0][1]
                          - section[name]["runs_height_fraction"][0][0])
    gap_runs = section["gap_probe"]["runs_height_fraction"]
    return {"bounds": [x0, y0, x1, y1], "aspect": w/h,
            "ink_fraction_in_bbox": float(a.sum()/(w*h)), "components": int(count),
            "component_ink_fractions": [v/int(a.sum()) for v in areas],
            "top_bar_end_neck_ratio": first("left_end")/first("left_neck"),
            "upper_bar_gap_height_fraction": gap_runs[1][0]-gap_runs[0][1] if len(gap_runs)>=2 else None,
            "manual_sections": section}


def native_trace_iou(svg, mask):
    # Inverse of the recorded isotropic reference normalization.
    y, x = np.where(mask)
    box = [x.min(), y.min(), x.max()+1, y.max()+1]
    s = 820/(box[3]-box[1])
    tx, ty = 500-s*(box[0]+box[2])/2, 500-s*(box[1]+box[3])/2
    root = ET.Element("svg", {"xmlns": NS, "viewBox": f"0 0 {mask.shape[1]} {mask.shape[0]}"})
    group = ET.SubElement(root, "g", {"transform": f"matrix({1/s} 0 0 {1/s} {-tx/s} {-ty/s})"})
    for p in ET.fromstring(svg):
        group.append(copy.deepcopy(p))
    raw = cairosvg.svg2png(bytestring=ET.tostring(root), background_color="#ffffff",
                          output_width=mask.shape[1], output_height=mask.shape[0])
    traced = np.asarray(Image.open(io.BytesIO(raw)).convert("L")) < 128
    return iou(mask, traced), int(ndi.label(traced, structure=np.ones((3,3)))[1])


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    svg = {name:(ROOT/(name+".svg")).read_text() for name in ("reference-trace", "previous", "weight-only")}
    masks = {name:raster(value) for name,value in svg.items()}
    pixelmask = load_mask()
    fidelity, trace_components = native_trace_iou(svg["reference-trace"], pixelmask)
    stats = {name:metrics(a) for name,a in masks.items()}
    ref = masks["reference-trace"]
    similarities = {name:iou(ref, a) for name,a in masks.items()}
    # Artifact checks, not aesthetic acceptance tests.
    assert fidelity >= .985, "Reference trace lost too much of the supplied mask"
    assert trace_components == 3, "Reference trace lost a disconnected silhouette"
    assert stats["reference-trace"]["components"] == 3
    assert stats["previous"]["components"] == 3
    assert stats["weight-only"]["components"] == 1, "The one-parameter control is an explicit failed separation case"
    report = {"schema_version":1, "kind":"reference-led-shape-research", "normalization":
              "Same height 820 and bbox center [500,500], isotropic only; no per-part fitting",
              "native_reference_trace_iou":fidelity, "reference_trace_components":trace_components,
              "metrics":stats, "iou_to_traced_reference":similarities,
              "not_a_beauty_score":True, "manual_semantics":True,
              "observations":[
                  "The old model is similar in global aspect but much lighter in filled area.",
                  "The reference upper bar is fuller near its left end than near the neck; the previous model reverses that relation at the selected probes.",
                  "The reference has less upper-bar white gap at the selected probe.",
                  "Weight alone raises geometric similarity but merges three separated silhouettes into one.",
                  "Reference left lower sweep ends in a point while other terminals remain full and round; uniform rounding loses that contrast."],
              "hypotheses_not_conclusions":[
                  "A fuller end plus a narrower neck can create a soft elastic rhythm.",
                  "Round weight contrasted with a pointed sweeping terminal can supply motion without random distortion.",
                  "Region-specific white gaps may need independent constraints instead of a single global weight."],
              "limits":["One manually cropped AI reference and one character; no general style-learning result.",
                        "Tracing is silhouette reconstruction, not reusable DNA or stroke decomposition.",
                        "Measurements are study-specific probes, not universal typographic landmarks.",
                        "Similarity to this reference does not measure beauty, legibility or generalization."]}
    (output/"shape-report.json").write_text(json.dumps(report, indent=2)+"\n")
    fig, axes = plt.subplots(2,3,figsize=(18,13), facecolor="white")
    for ax in axes.ravel():
        ax.set_xlim(0,1000);ax.set_ylim(1000,0);ax.set_aspect("equal");ax.axis("off")
    def show(ax, a, title, subtitle):
        ax.imshow(np.where(a,0,255),cmap="gray",vmin=0,vmax=255,extent=(0,1000,1000,0),interpolation="nearest")
        ax.set_title(title,loc="left",fontsize=18,pad=30,fontweight="bold")
        ax.text(0,-.025,subtitle,transform=ax.transAxes,fontsize=11,color="#5c6266",va="top")
    # Source mask is displayed at the same isotropic height, preserving pixels.
    ref_native = np.full((1000,1000),255,dtype=np.uint8)
    y,x=np.where(pixelmask);box=[x.min(),y.min(),x.max()+1,y.max()+1]
    cropped=Image.fromarray(np.where(pixelmask[box[1]:box[3],box[0]:box[2]],0,255).astype(np.uint8))
    w=round(820*cropped.width/cropped.height)
    resized=np.asarray(cropped.resize((w,820),Image.Resampling.NEAREST))
    ref_native[90:910,(1000-w)//2:(1000-w)//2+w]=resized
    show(axes[0,0],ref_native<128,"1 / REFERENCE MASK","The approved AI image, thresholded at 128")
    show(axes[0,1],masks["previous"],"2 / PREVIOUS MODEL",f"Ink / bbox {stats['previous']['ink_fraction_in_bbox']:.1%}; 3 separate silhouettes")
    show(axes[0,2],ref,"3 / RECONSTRUCTED SVG",f"Native mask overlap: {fidelity:.1%}; contour reconstruction only")
    control=json.loads((ROOT/"weight-only-control.json").read_text())
    show(axes[1,0],masks["weight-only"],"4 / WEIGHT-ONLY CONTROL",f"Weight {control['best']['weight']:.2f}; higher overlap but 3 silhouettes merge into 1")
    axes[1,0].text(.02,.92,"SEPARATION LOST",color="#B44A31",fontsize=13,fontweight="bold",transform=axes[1,0].transAxes)
    a=masks["previous"];colors=np.ones((1000,1000,3))
    colors[ref & ~a]=[.10,.62,.64];colors[a & ~ref]=[.93,.42,.26];colors[a & ref]=[.12,.16,.20]
    axes[1,1].imshow(colors,extent=(0,1000,1000,0),interpolation="nearest")
    axes[1,1].set_title("5 / SHAPE DIFFERENCE",loc="left",fontsize=18,pad=30,fontweight="bold")
    axes[1,1].text(0,-.025,"Teal: reference only / coral: previous only / dark: shared",transform=axes[1,1].transAxes,fontsize=11,color="#5c6266",va="top")
    show(axes[1,2],ref,"6 / WHAT TO STUDY","A waist / B gap / C pointed sweep\nD droplet / E inner space")
    b=stats["reference-trace"]["bounds"];bw,bh=b[2]-b[0],b[3]-b[1]
    for label,(xf,yf),(dx,dy) in [
        ("A",(.38,.24),(-100,-75)),("B",(.28,.34),(-100,-30)),
        ("C",(.10,.95),(-15,-95)),("D",(.12,.70),(-50,-85)),("E",(.50,.65),(90,-50))]:
        xx,yy=b[0]+xf*bw,b[1]+yf*bh
        axes[1,2].annotate(label,(xx,yy),(xx+dx,yy+dy),fontsize=17,fontweight="bold",color="#05777C",
                           arrowprops={"arrowstyle":"->","color":"#05777C","lw":1.5},
                           bbox={"boxstyle":"circle,pad=.15","fc":"white","ec":"#05777C","lw":1})
    fig.suptitle("GLYPH / FROM A REFERENCE TO OBSERVABLE SHAPE",x=.04,y=.96,va="top",ha="left",fontsize=23,fontweight="bold")
    fig.text(.04,.022,"Geometry measurements describe this reference. They do not rank beauty. No reusable style rule is proven yet.",fontsize=12,color="#5c6266")
    fig.subplots_adjust(left=.035,right=.985,top=.86,bottom=.09,wspace=.10,hspace=.29)
    fig.savefig(output/"retro-shape-research.png",dpi=110)
    fig.savefig(output/"retro-shape-research.svg")
    plt.close(fig)
    return report


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    result=generate(args.out)
    print(json.dumps({"trace_iou":result["native_reference_trace_iou"],
                      "comparisons":result["iou_to_traced_reference"]},indent=2))
