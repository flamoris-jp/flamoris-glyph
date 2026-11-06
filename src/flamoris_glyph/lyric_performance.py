"""A finite lyric artwork: skeleton + DNA (including writing style) + expression.

This combines explicit centerlines with a geometric nib sweep. It neither
extracts skeletons from fonts nor trains a writer. Output is static artwork;
layout/timing belong to the consumer. Japanese-derived artwork is CC BY-SA 3.0.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
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
    spread: float = 1
    squash: float = 1
    pressure: float = 1
    reach: float = .12


SKELETONS = {"open": Skeleton(1.04, .97), "tall": Skeleton(.95, 1.03),
             "compact": Skeleton(1.01, .90)}
DNAS = {"ribbon": DNA(74, .52, 35, .72, .28, .22),
        "soft": DNA(51, 1, 0, .90, .78, .06)}
STROKES = {"gentle": Stroke(.015, .008, 0, 1, .025, 0),
           "energetic": Stroke(.12, .055, 27, 0, .16, 0),
           "cute": Stroke(-.018, .018, 0, 5, .07, 6)}


def strengthen_stroke(name, intensity=1):
    """A bounded degree of the existing expression, not a fourth design layer."""
    if (isinstance(intensity, bool) or not isinstance(intensity, (int, float))
            or not math.isfinite(intensity) or not 1 <= intensity <= 4):
        raise ValueError("Stroke intensity must be a finite number from 1 to 4")
    base = STROKES[name]
    if intensity == 1:
        return base
    extra = intensity-1
    spread, squash, pressure = {"gentle": (.04, -.025, .12),
                                "energetic": (.02, -.035, .13),
                                "cute": (.055, -.055, .26)}[name]
    return replace(base, lean=math.copysign(min(.28, abs(base.lean)*intensity), base.lean),
                   bow=base.bow*intensity, extend=min(80, base.extend*intensity),
                   roundness=round(base.roundness*intensity**1.4),
                   pulse=base.pulse*intensity, bounce=base.bounce*intensity,
                   spread=1+spread*extra, squash=1+squash*extra, pressure=1+pressure*extra,
                   reach=.12+.04*extra)


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


def express_centerline(points, skeleton, stroke, phase=0, *, anchors=(), junction_strength=0):
    raw_points = points
    if junction_strength:
        def freedom(point):
            distance = min((math.dist(point, a) for a in anchors), default=1000)
            t = min(1, distance/95)
            return 1-junction_strength*(1-t*t*(3-2*t))
        freedoms = [freedom(p) for p in points]
    else:
        freedoms = [1]*len(points)
    points = [(500+(x-500)*skeleton.width, 500+(y-500)*skeleton.height) for x, y in points]
    if stroke.spread != 1 or stroke.squash != 1:
        points = [(500+(x-500)*stroke.spread, 500+(y-500)*stroke.squash) for x, y in points]
    unsmoothed = points[:]
    for _ in range(stroke.roundness):
        points = [points[0], *[tuple(.22*a[k]+.56*b[k]+.22*c[k] for k in (0, 1))
                              for a, b, c in zip(points, points[1:], points[2:])], points[-1]]
    if junction_strength:
        points = [tuple(a[k]+f*(b[k]-a[k]) for k in (0, 1))
                  for a, b, f in zip(unsmoothed, points, freedoms)]
    x0, y0 = points[0]
    dx, dy = points[-1][0]-x0, points[-1][1]-y0
    chord = math.hypot(dx, dy)
    nx, ny = (-dy/chord, dx/chord) if chord > 1 else (0, 0)
    length = math.fsum(math.dist(a, b) for a, b in zip(points, points[1:]))
    tx, ty = points[-1][0]-points[-3][0], points[-1][1]-points[-3][1]
    tangent = math.hypot(tx, ty) or 1
    result = []
    endpoint_freedom = freedoms[-1]
    if junction_strength and math.dist(raw_points[0], raw_points[-1]) < .001:
        endpoint_freedom *= 1-junction_strength
    for i, (x, y) in enumerate(points):
        u = i/(len(points)-1)
        bow = stroke.bow*min(length, 700)*math.sin(math.pi*u)**1.4*freedoms[i]
        extend = min(stroke.extend, length*stroke.reach)*u**7*endpoint_freedom*freedoms[i]
        result.append((x+stroke.lean*(600-y)+nx*bow+tx/tangent*extend,
                       y+ny*bow+ty/tangent*extend+stroke.bounce*math.sin(phase)*freedoms[i]))
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
        radius = dna.width*pressure*stroke.pressure/2
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
    def __init__(self, japanese, latin, *, skeleton="open", dna="ribbon", stroke="gentle", intensity=1):
        if skeleton not in SKELETONS or dna not in DNAS or stroke not in STROKES:
            raise ValueError("Unknown skeleton, DNA or stroke expression")
        if (japanese.get("kind") != "lyric-stroke-sources-1" or japanese.get("license") != "CC-BY-SA-3.0"
                or latin.get("kind") != "original-latin-centerlines-1"):
            raise ValueError("Expected explicit licensed lyric centerline sources")
        self.japanese, self.latin = japanese["glyphs"], latin["glyphs"]
        if len(self.japanese)+len(self.latin) > 128:
            raise ValueError("Lyric experiment supports at most 128 source glyphs")
        self.skeleton, self.dna, self.stroke = SKELETONS[skeleton], DNAS[dna], strengthen_stroke(stroke, intensity)
        self.intensity = intensity
        self.identity = {"engine": ENGINE, "skeleton": {"id": skeleton, **asdict(self.skeleton)},
                         "dna": {"id": dna, **asdict(self.dna)}, "stroke": {"id": stroke, "intensity": intensity, **asdict(self.stroke)},
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
        sampled = [sample_centerline(path, japanese) for path in paths]
        anchors = []
        if self.intensity > 1:
            from shapely.geometry import LineString
            def collect(geometry):
                if geometry.geom_type == "Point":
                    anchors.append(tuple(geometry.coords[0]))
                elif hasattr(geometry, "geoms"):
                    for part in geometry.geoms:
                        collect(part)
                elif geometry.geom_type == "LineString" and not geometry.is_empty:
                    anchors.extend((tuple(geometry.coords[0]), tuple(geometry.coords[-1])))
            for i, line in enumerate(sampled):
                for other in sampled[:i]:
                    collect(LineString(line).intersection(LineString(other)))
        for index, path in enumerate(paths):
            phase = int(hashlib.sha256(f"{char}/{index}".encode()).hexdigest()[:4], 16)/65535*math.tau
            points = express_centerline(sampled[index], self.skeleton, self.stroke, phase,
                                        anchors=anchors, junction_strength=min(1, self.intensity-1))
            ink_stroke = self.stroke
            if self.intensity > 1 and len(paths) >= 8:
                # Dense characters get the same route expression, with reduced
                # additional pressure so their small spaces are less overwhelmed.
                base_pulse = STROKES[self.identity["stroke"]["id"]].pulse
                ink_stroke = replace(self.stroke, pressure=1+(self.stroke.pressure-1)*.35,
                                     pulse=base_pulse+(self.stroke.pulse-base_pulse)*.35)
            shapes.append({"d": _outline(points, self.dna, ink_stroke, phase)})
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
    label = f"{performance['skeleton']} / {performance['dna']} / {performance['stroke']}"
    intensity = source.identity["stroke"]["intensity"]
    if intensity != 1:
        label += f" / intensity {intensity:g}"
    _text(root, label, 85, 205, 18, accent)
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


def stroke_strip(japanese, latin, *, intensity=1):
    """One DNA and skeleton, three expressions: shapes, not colour, differ."""
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": "0 0 1600 880"})
    ET.SubElement(root, "rect", {"width": "1600", "height": "880", "fill": "#F4EDE0"})
    title = "ONE SKELETON + ONE DNA / THREE EXPRESSIONS"
    if intensity != 1:
        title += f" / {intensity:g}"
    _text(root, title, 65, 65, 26)
    for i, (stroke, label) in enumerate((("gentle", "GENTLE"), ("energetic", "ENERGETIC"), ("cute", "CUTE"))):
        source = PerformanceSource(japanese, latin, skeleton="open", dna="ribbon", stroke=stroke, intensity=intensity)
        y = 110+i*230
        _text(root, label, 65, y+30, 18, "#8C6554")
        place_line(root, "もういいよ　It’s all right", source, x=65, y=y+48, size=108,
                   japanese_fill="#294E49", latin_fill="#294E49")
    _text(root, "KanjiVG / Ulrich Apel / CC BY-SA 3.0 | Original Latin: FLAMORIS", 65, 841, 16)
    return ET.tostring(root, encoding="unicode")+"\n"


def intensity_sheet(japanese, latin, performances, intensity):
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": "0 0 2400 1320"})
    phrases = ["もういいよ　It’s all right", "顔をあげて　Meet my eyes"]
    for row, performance in enumerate(performances):
        sources = [PerformanceSource(japanese, latin, intensity=level,
                                     **{k: performance[k] for k in ("skeleton", "dna", "stroke")})
                   for level in (1, intensity)]
        size = min(115, 1040/max(line_width(t, s) for t in phrases for s in sources)*1000)
        for col, (level, source) in enumerate(zip((1, intensity), sources)):
            x, y = col*1200, row*440
            ET.SubElement(root, "rect", {"x": str(x), "y": str(y), "width": "1200", "height": "440",
                                         "fill": performance["background"]})
            label = "ORIGINAL" if col == 0 else "EXPRESSIVE"
            _text(root, performance["title"]+" / "+label, x+65, y+58, 25, performance["ink"])
            _text(root, f"Stroke intensity {level:g} / same skeleton and DNA", x+65, y+94, 17, performance["accent"])
            for line, phrase in enumerate(phrases):
                place_line(root, phrase, source, x=x+65, y=y+125+line*126, size=size,
                           japanese_fill=performance["ink"], latin_fill=performance["accent"])
            _text(root, "KanjiVG / Ulrich Apel / CC BY-SA 3.0 | Latin: FLAMORIS", x+65, y+415, 13, performance["ink"])
    return ET.tostring(root, encoding="unicode")+"\n"


def run_performance(inputs, output, *, intensity=1):
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
            source = PerformanceSource(japanese, latin, intensity=intensity,
                                       **{k: performance[k] for k in ("skeleton", "dna", "stroke")})
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
        (stage/"same-dna-strokes.svg").write_text(stroke_strip(japanese, latin, intensity=intensity), encoding="utf-8")
        if intensity != 1:
            (stage/"before-after.svg").write_text(intensity_sheet(japanese, latin, data["performances"], intensity), encoding="utf-8")
        report = {"engine": ENGINE, "performances": records, "japanese_characters": len(japanese["glyphs"]),
                  "latin_characters": len(latin["glyphs"]), "lyrics_sha256": hashlib.sha256(lyrics.encode()).hexdigest(),
                  "limits": ["Finite explicit lyric skeletons, no font decomposition or trained handwriting.",
                             "Nib and entry/finish tendencies are inside DNA; expression modifies the centerline.",
                             "Intensity is an expression degree, not a measured emotion multiplier or a new layer.",
                             "Boosted routes attenuate local movement near source intersections; dense glyphs attenuate extra pressure.",
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
    parser.add_argument("--intensity", type=float, default=1,
                        help="Degree of stroke expression, 1 (original) to 4 (exaggerated)")
    args = parser.parse_args(argv)
    try:
        report = run_performance(args.inputs, args.out, intensity=args.intensity)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        parser.error(str(error))
    print(f"Wrote {len(report['performances'])} bilingual lyric artworks and explicit glyph paths")


if __name__ == "__main__":
    main()
