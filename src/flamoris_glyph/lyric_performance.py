"""A finite lyric artwork: skeleton + DNA (including writing style) + expression.

This combines explicit centerlines with a geometric nib sweep. It neither
extracts skeletons from fonts nor trains a writer. Output is static artwork;
layout/timing belong to the consumer. Japanese-derived artwork is CC BY-SA 3.0.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

from fontTools.pens.basePen import BasePen
from fontTools.svgLib.path import parse_path

from .bundle import SVG_NS, _svg, validate_svg
from .lyrics import parse_cues, occurrences
from .style import digest

ENGINE = "lyric-performance-1"


@dataclass(frozen=True)
class Skeleton:
    width: float
    height: float


@dataclass(frozen=True)
class DNA:
    """Shared construction and writing-style tendencies, including the nib."""
    width: float
    aspect: float
    angle: float
    entry: float
    finish: float
    swell: float


@dataclass(frozen=True)
class Stroke:
    """Expression changes centerlines as well as width, not a fourth tool layer."""
    lean: float
    bow: float
    extend: float
    roundness: int
    pulse: float
    bounce: float


SKELETONS = {"open": Skeleton(1.04, .97), "tall": Skeleton(.95, 1.03),
             "compact": Skeleton(1.01, .90)}
DNAS = {"ribbon": DNA(74, .52, 35, .72, .28, .22),
        "soft": DNA(51, 1, 0, .90, .78, .06)}
STROKES = {"gentle": Stroke(.015, .008, 0, 1, .025, 0),
           "energetic": Stroke(.12, .055, 27, 0, .16, 0),
           "cute": Stroke(-.018, .018, 0, 5, .07, 6)}


class _SamplePen(BasePen):
    def __init__(self):
        super().__init__(None)
        self.points = []
        self.contours = 0

    def _moveTo(self, p):
        self.contours += 1
        if self.contours > 1:
            raise ValueError("One source stroke must have one contour")
        self.points.append(p)

    def _lineTo(self, p):
        self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        for i in range(1, 33):
            t, r = i/32, 1-i/32
            self.points.append(tuple(r**3*p0[a]+3*r*r*t*p1[a]+3*r*t*t*p2[a]+t**3*p3[a] for a in (0, 1)))

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        for i in range(1, 33):
            t, r = i/32, 1-i/32
            self.points.append(tuple(r*r*p0[a]+2*r*t*p1[a]+t*t*p2[a] for a in (0, 1)))

    def _endPath(self):
        pass

    def _closePath(self):
        self.points.append(self.points[0])


@lru_cache(maxsize=512)
def sample_centerline(path, japanese=False):
    if (not isinstance(path, str) or len(path) > 20_000
            or not re.fullmatch(r"[MLCQHVZSTmlcqh vzst0-9eE+.,\s-]+", path)):
        raise ValueError("Expected a bounded numeric centerline")
    pen = _SamplePen()
    parse_path(path, pen)
    points = []
    for p in pen.points:
        p = tuple(130+6.8*v for v in p) if japanese else p
        if not all(math.isfinite(v) and 0 <= v <= 1000 for v in p):
            raise ValueError("Source centerline outside design box")
        if not points or math.dist(p, points[-1]) > 1e-7:
            points.append(p)
    if len(points) < 2:
        raise ValueError("Empty source stroke")
    distances = [0.0]
    for a, b in zip(points, points[1:]):
        distances.append(distances[-1]+math.dist(a, b))
    length, result, j = distances[-1], [], 1
    for i in range(81):
        target = length*i/80
        while j < len(points)-1 and distances[j] < target:
            j += 1
        fraction = (target-distances[j-1])/(distances[j]-distances[j-1])
        result.append(tuple(points[j-1][a]*(1-fraction)+points[j][a]*fraction for a in (0, 1)))
    return tuple(result)


def express_centerline(points, skeleton, stroke, phase=0):
    points = [(500+(x-500)*skeleton.width, 500+(y-500)*skeleton.height) for x, y in points]
    for _ in range(stroke.roundness):
        points = [points[0], *[tuple(.22*a[k]+.56*b[k]+.22*c[k] for k in (0, 1))
                              for a, b, c in zip(points, points[1:], points[2:])], points[-1]]
    x0, y0 = points[0]
    dx, dy = points[-1][0]-x0, points[-1][1]-y0
    chord = math.hypot(dx, dy)
    nx, ny = (-dy/chord, dx/chord) if chord > 1 else (0, 0)
    length = math.fsum(math.dist(a, b) for a, b in zip(points, points[1:]))
    tx, ty = points[-1][0]-points[-3][0], points[-1][1]-points[-3][1]
    tangent = math.hypot(tx, ty) or 1
    result = []
    for i, (x, y) in enumerate(points):
        u = i/(len(points)-1)
        bow = stroke.bow*min(length, 700)*math.sin(math.pi*u)**1.4
        extend = min(stroke.extend, length*.12)*u**7
        result.append((x+stroke.lean*(600-y)+nx*bow+tx/tangent*extend,
                       y+ny*bow+ty/tangent*extend+stroke.bounce*math.sin(phase)))
    return tuple(result)


def _outline(points, dna, stroke, phase):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from shapely.geometry.polygon import orient
    footprints = []
    theta = math.radians(dna.angle)
    c, s = math.cos(theta), math.sin(theta)
    for i, (x, y) in enumerate(points):
        u = i/(len(points)-1)
        entry = min(1, u/.10)
        finish = min(1, (1-u)/.19)
        pressure = ((dna.entry+(1-dna.entry)*entry)
                    * (dna.finish+(1-dna.finish)*finish)
                    * (1+dna.swell*math.sin(math.pi*u))
                    * (1+stroke.pulse*math.sin(math.pi*u+phase)))
        radius = dna.width*pressure/2
        footprints.append(Polygon([
            (x+radius*(c*math.cos(a)-s*dna.aspect*math.sin(a)),
             y+radius*(s*math.cos(a)+c*dna.aspect*math.sin(a)))
            for a in (2*math.pi*j/20 for j in range(20))]))
    polygon = unary_union([a.union(b).convex_hull for a, b in zip(footprints, footprints[1:])])
    if polygon.is_empty or not polygon.is_valid or polygon.geom_type != "Polygon":
        raise ValueError("Invalid swept stroke")
    # Source loops, e.g. o and あ, intentionally retain their holes. No repair.
    polygon = orient(polygon, sign=1)
    contours = [polygon.exterior, *polygon.interiors]
    parts = []
    for contour in contours:
        coords = list(contour.coords)[:-1]
        parts.append("M "+" L ".join(f"{x:.3f} {y:.3f}" for x, y in coords)+" Z")
    return " ".join(parts)


class PerformanceSource:
    def __init__(self, japanese, latin, *, skeleton="open", dna="ribbon", stroke="gentle"):
        if skeleton not in SKELETONS or dna not in DNAS or stroke not in STROKES:
            raise ValueError("Unknown skeleton, DNA or stroke expression")
        if (japanese.get("kind") != "lyric-stroke-sources-1" or japanese.get("license") != "CC-BY-SA-3.0"
                or latin.get("kind") != "original-latin-centerlines-1"):
            raise ValueError("Expected explicit licensed lyric centerline sources")
        self.japanese, self.latin = japanese["glyphs"], latin["glyphs"]
        if len(self.japanese)+len(self.latin) > 128:
            raise ValueError("Lyric experiment supports at most 128 source glyphs")
        self.skeleton, self.dna, self.stroke = SKELETONS[skeleton], DNAS[dna], STROKES[stroke]
        self.identity = {"engine": ENGINE, "skeleton": {"id": skeleton, **asdict(self.skeleton)},
                         "dna": {"id": dna, **asdict(self.dna)}, "stroke": {"id": stroke, **asdict(self.stroke)},
                         "source_sha256": digest({"japanese": japanese, "latin": latin})}
        self.cache = {}

    def draw(self, char):
        if char in self.cache:
            return self.cache[char]
        if char in self.japanese:
            paths = [p["path"] for p in self.japanese[char]["strokes"]]
            japanese = True
        elif char in self.latin:
            paths, japanese = self.latin[char], False
        else:
            raise ValueError(f"No explicit lyric skeleton for {char!r}")
        if not 1 <= len(paths) <= 64:
            raise ValueError("Expected 1..64 strokes per glyph")
        shapes, bones = [], []
        for index, path in enumerate(paths):
            phase = int(hashlib.sha256(f"{char}/{index}".encode()).hexdigest()[:4], 16)/65535*math.tau
            points = express_centerline(sample_centerline(path, japanese), self.skeleton, self.stroke, phase)
            shapes.append({"d": _outline(points, self.dna, self.stroke, phase)})
            bones.append(points)
        svg = _svg({"paths": shapes}, {"fill": "#222222"})
        validate_svg(svg)
        # Advance is fixed by the neutral skeleton, so expression cannot cause
        # text to reflow. Centerlines, not contours, establish Latin spacing.
        if japanese:
            advance, origin = 1000, 0
        else:
            xs = [x for path in paths for x, _ in sample_centerline(path)]
            advance, origin = max(225, max(xs)-min(xs)+145), min(xs)-72.5
        result = {"svg": svg, "bones": bones, "advance": advance, "origin": origin}
        self.cache[char] = result
        return result


def _text(root, text, x, y, size=20, fill="#222222", **attrs):
    ET.SubElement(root, "text", {"x": str(x), "y": str(y), "font-family": "sans-serif",
                               "font-size": str(size), "fill": fill, **attrs}).text = text


def line_width(text, source):
    return math.fsum(370 if c.isspace() and c != "　" else 480 if c == "　" else source.draw(c)["advance"] for c in text)


def place_line(root, text, source, *, x, y, size, japanese_fill, latin_fill, bones=False):
    scale, cursor, layout = size/1000, x, []
    for char in text:
        if char.isspace():
            cursor += (480 if char == "　" else 370)*scale
            continue
        shape = source.draw(char)
        tx = cursor-shape["origin"]*scale
        group = ET.SubElement(root, "g", {"transform": f"translate({tx:.4f} {y:.4f}) scale({scale:.6f})"})
        if bones:
            for points in shape["bones"]:
                ET.SubElement(group, "path", {"d": "M "+" L ".join(f"{a:.2f} {b:.2f}" for a, b in points),
                                             "stroke": japanese_fill, "stroke-width": "8", "fill": "none"})
        else:
            for path in ET.fromstring(shape["svg"]):
                ET.SubElement(group, "path", {"d": path.attrib["d"], "fill": japanese_fill if ord(char) > 0x3000 else latin_fill})
        layout.append({"character": char, "x": round(tx, 4), "y": y, "scale": scale})
        cursor += shape["advance"]*scale
    return layout


def poster(lines, source, performance, *, bones=False):
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": "0 0 1200 1700"})
    bg, ink, accent = (performance[k] for k in ("background", "ink", "accent"))
    ET.SubElement(root, "rect", {"width": "1200", "height": "1700", "fill": bg})
    ET.SubElement(root, "path", {"d": "M85 93 H1115", "stroke": accent, "stroke-width": "2"})
    _text(root, "FLAMORIS / GLYPH SESSION 01", 85, 70, 19, ink, **{"letter-spacing": "3"})
    _text(root, performance["title"], 85, 162, 38, ink, **{"letter-spacing": "4"})
    _text(root, f"{performance['skeleton']} / {performance['dna']} / {performance['stroke']}", 85, 205, 18, accent)
    # One size for every line; mixed scripts share a baseline and remain inline.
    size = min(87, 1030/max(line_width(line, source) for line in lines)*1000)
    y, row, layouts = 278, 0, []
    for line in lines:
        if not line:
            y += 34
            continue
        row += 1
        _text(root, f"{row:02}", 55, y+size*.62, 13, accent)
        layouts.append(place_line(root, line, source, x=85, y=y, size=size, japanese_fill=ink,
                                  latin_fill=accent, bones=bones))
        y += 112
    _text(root, "SAME WORDS / DIFFERENT FEELINGS", 85, 1563, 19, ink, **{"letter-spacing": "3"})
    _text(root, "Japanese skeletons: KanjiVG / Ulrich Apel / CC BY-SA 3.0", 85, 1610, 14, ink)
    _text(root, "https://kanjivg.tagaini.net/  |  Original Latin skeletons: FLAMORIS", 85, 1636, 14, ink)
    return ET.tostring(root, encoding="unicode")+"\n", layouts


def stroke_strip(japanese, latin):
    """One DNA and skeleton, three expressions: shapes, not colour, differ."""
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": "0 0 1600 880"})
    ET.SubElement(root, "rect", {"width": "1600", "height": "880", "fill": "#F4EDE0"})
    _text(root, "ONE SKELETON + ONE DNA / THREE EXPRESSIONS", 65, 65, 26)
    for i, (stroke, label) in enumerate((("gentle", "GENTLE"), ("energetic", "ENERGETIC"), ("cute", "CUTE"))):
        source = PerformanceSource(japanese, latin, skeleton="open", dna="ribbon", stroke=stroke)
        y = 110+i*230
        _text(root, label, 65, y+30, 18, "#8C6554")
        place_line(root, "もういいよ　It’s all right", source, x=65, y=y+48, size=108,
                   japanese_fill="#294E49", latin_fill="#294E49")
    _text(root, "KanjiVG / Ulrich Apel / CC BY-SA 3.0 | Original Latin: FLAMORIS", 65, 841, 16)
    return ET.tostring(root, encoding="unicode")+"\n"


def run_performance(inputs, output):
    if output.exists() or output.is_symlink():
        raise ValueError("Performance output already exists; choose a new directory")
    def read(name):
        p = inputs/name
        if p.stat().st_size > 2_000_000:
            raise ValueError("Lyric input exceeds 2 MB")
        return p.read_text(encoding="utf-8")
    japanese, latin = json.loads(read("kanjivg-subset.json")), json.loads(read("latin-skeletons.json"))
    data, lyrics = json.loads(read("performances.json")), read("lyrics.txt")
    if (set(data) != {"schema_version", "kind", "performances"} or data["schema_version"] != 1
            or data["kind"] != "lyric-performances-1" or len(data["performances"]) != 3):
        raise ValueError("Expected the three lyric performances")
    cues, lines = parse_cues(lyrics), lyrics.splitlines()
    instances = occurrences(cues)
    if len(cues) != 10 or len(instances) > 500:
        raise ValueError("This artwork supports the ten-line lyric, up to 500 occurrences")
    seen = set()
    for p in data["performances"]:
        if (set(p) != {"id", "title", "skeleton", "dna", "stroke", "background", "ink", "accent"}
                or not re.fullmatch(r"[a-z]{1,20}", p["id"]) or p["id"] in seen
                or not isinstance(p["title"], str) or not 1 <= len(p["title"]) <= 40):
            raise ValueError("Invalid performance labels")
        seen.add(p["id"])
        for k in ("background", "ink", "accent"):
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", p[k]):
                raise ValueError("Performance colours must be six-digit hex")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".lyric-performance-", dir=output.parent))
    records, columns = [], []
    try:
        for performance in data["performances"]:
            source = PerformanceSource(japanese, latin, **{k: performance[k] for k in ("skeleton", "dna", "stroke")})
            name = performance["id"]
            dest = stage/name
            (dest/"glyphs").mkdir(parents=True)
            mapping, assets = [], {}
            for occurrence in instances:
                char = occurrence.character
                shape = source.draw(char)
                asset = f"glyphs/u{ord(char):05x}.svg"
                assets[asset] = shape["svg"]
                mapping.append({**asdict(occurrence), "asset": asset})
            for asset, svg in assets.items():
                (dest/asset).write_text(svg, encoding="utf-8")
            svg, layouts = poster(lines, source, performance)
            (stage/(name+".svg")).write_text(svg, encoding="utf-8")
            bone_svg, _ = poster(lines, source, performance, bones=True)
            (stage/(name+"-bones.svg")).write_text(bone_svg, encoding="utf-8")
            manifest = {"schema_version": 1, "kind": ENGINE, "inputs": source.identity,
                        "artwork_license": "CC-BY-SA-3.0", "japanese_source": {k:v for k,v in japanese.items() if k != "glyphs"},
                        "latin_source": {k:v for k,v in latin.items() if k != "glyphs"},
                        "cues": [asdict(c) for c in cues], "occurrences": mapping, "poster_layout": layouts,
                        "assets": {a: {"sha256": hashlib.sha256(v.encode()).hexdigest()} for a,v in assets.items()},
                        "timing": "not supplied; no singing times inferred", "reuse": "character within performance",
                        "format_note": "Experimental artwork package; not the production bundle-v2/player contract"}
            (dest/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            records.append({"id": name, "inputs": source.identity, "glyphs": len(assets), "occurrences": len(mapping)})
            columns.append(ET.fromstring(svg))
        root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": "0 0 3600 1700"})
        for i, column in enumerate(columns):
            group = ET.SubElement(root, "g", {"transform": f"translate({i*1200} 0)"})
            group.extend(list(column))
        (stage/"comparison.svg").write_text(ET.tostring(root, encoding="unicode")+"\n", encoding="utf-8")
        (stage/"same-dna-strokes.svg").write_text(stroke_strip(japanese, latin), encoding="utf-8")
        report = {"engine": ENGINE, "performances": records, "japanese_characters": len(japanese["glyphs"]),
                  "latin_characters": len(latin["glyphs"]), "lyrics_sha256": hashlib.sha256(lyrics.encode()).hexdigest(),
                  "limits": ["Finite explicit lyric skeletons, no font decomposition or trained handwriting.",
                             "Nib and entry/finish tendencies are inside DNA; expression modifies the centerline.",
                             "No physical brush simulation, expert calligraphy claim or automatic beauty score.",
                             "Each artwork changes three choices together; the separate strip fixes skeleton and DNA.",
                             "Stroke order is sourced, not a measured singing timeline; no music supplied.",
                             "Latin skeletons are original informal lettering, not a shaping/kerning engine."]}
        (stage/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        for filename in ("lyrics.txt", "kanjivg-subset.json", "latin-skeletons.json", "performances.json", "ATTRIBUTION.md"):
            shutil.copyfile(inputs/filename, stage/filename)
        stage.rename(output)
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_performance(args.inputs, args.out)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        parser.error(str(error))
    print(f"Wrote {len(report['performances'])} bilingual lyric artworks and explicit glyph paths")


if __name__ == "__main__":
    main()
