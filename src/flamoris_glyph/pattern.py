"""Experimental Pattern DNA 1: bounded, outline-only morphology.

No stroke/radical inference, material, or playback. Shapely is an optional extra.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math

from fontTools.pens.basePen import BasePen
from fontTools.svgLib.path import parse_path

from .geometry import fmt
from .style import canonical_json, number

ENGINE_VERSION = "outline-pattern-1"
PRESETS = {
    "heavy-condensed-headline": dict(width=0.76, offset_x=12, offset_y=9, corner_radius=0, irregularity=0),
    "elegant-high-contrast-editorial": dict(width=0.98, offset_x=7, offset_y=-2.5, corner_radius=0, irregularity=0),
    "showa-retro-signboard": dict(width=1.02, offset_x=3, offset_y=3, corner_radius=3, irregularity=2.5),
}


@dataclass(frozen=True)
class PatternDNA:
    profile: str
    width: float = 1
    offset_x: float = 0
    offset_y: float = 0
    corner_radius: float = 0
    irregularity: float = 0
    variation: float = 0.35

    def __post_init__(self):
        if self.profile not in PRESETS:
            raise ValueError("Unknown Pattern DNA profile")
        for name, low, high in (("width", 0.65, 1.08), ("offset_x", -5, 14),
                                ("offset_y", -5, 14), ("corner_radius", 0, 6),
                                ("irregularity", 0, 4), ("variation", 0, 1)):
            number(getattr(self, name), name, low, high)

    @classmethod
    def preset(cls, profile):
        if profile not in PRESETS:
            raise ValueError("Unknown Pattern DNA profile")
        return cls(profile=profile, **PRESETS[profile])

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Pattern DNA must be an object")
        data = dict(data)
        version = data.pop("schema_version", None)
        if type(version) is not int or version != 1:
            raise ValueError("Unsupported Pattern DNA schema_version (expected 1)")
        if set(data) != set(cls.__dataclass_fields__):
            raise ValueError("Pattern DNA requires exactly the documented fields")
        return cls(**data)

    def to_dict(self):
        return {"schema_version": 1, **asdict(self)}

    def parameters(self, key, seed):
        raw = hashlib.sha256(canonical_json([ENGINE_VERSION, seed, key, self.profile]).encode()).digest()
        samples = [int.from_bytes(raw[i:i+4], "big") / (2**32 - 1) * 2 - 1 for i in (0, 4, 8)]
        return {"width": round(self.width * (1 + samples[0] * 0.015 * self.variation), 6),
                "offset_x": round(self.offset_x * (1 + samples[1] * 0.08 * self.variation), 6),
                "offset_y": round(self.offset_y * (1 + samples[1] * 0.08 * self.variation), 6),
                "corner_radius": self.corner_radius,
                "irregularity": self.irregularity,
                "phase": round(samples[2] * self.variation * math.pi, 6)}


def engine_metadata():
    try:
        import shapely
    except ImportError as error:
        raise ValueError("Pattern DNA requires the optional extra: pip install -e '.[patterns]'") from error
    if shapely.__version__ != "2.1.2":
        raise ValueError("Pattern engine 1 requires Shapely 2.1.2 for reproducibility")
    return {"version": ENGINE_VERSION, "shapely": shapely.__version__, "geos": shapely.geos_version_string,
            "flatten_tolerance": 0.35}


class _FlattenPen(BasePen):
    """Adaptive curve flattening with bounded recursion and point budget."""
    def __init__(self):
        super().__init__(None)
        self.rings, self.current, self.count = [], [], 0

    def add(self, p):
        self.count += 1
        if self.count > 16000:
            raise ValueError("Pattern input exceeds 16000 flattened points")
        self.current.append(tuple(p))

    def _moveTo(self, p):
        if self.current:
            raise ValueError("Open pattern contour")
        self.add(p)

    def _lineTo(self, p):
        self.add(p)

    def curve(self, points, depth=0):
        a, b = points[0], points[-1]
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        error = max((abs(dx*(a[1]-p[1]) - (a[0]-p[0])*dy) / length
                     if length else math.dist(a, p)) for p in points[1:-1])
        # Also reject collinear overshoot/backtracking as a flat chord.
        excess = sum(math.dist(p, q) for p, q in zip(points, points[1:])) - length
        if error <= 0.35 and excess <= 0.35:
            self.add(b)
            return
        if depth >= 14:
            raise ValueError("Pattern curve exceeds flattening tolerance")
        levels = [points]
        while len(levels[-1]) > 1:
            levels.append([((p[0]+q[0])/2, (p[1]+q[1])/2) for p, q in zip(levels[-1], levels[-1][1:])])
        self.curve([level[0] for level in levels], depth+1)
        self.curve([level[-1] for level in reversed(levels)], depth+1)

    def _qCurveToOne(self, p1, p2):
        self.curve([self.current[-1], p1, p2])

    def _curveToOne(self, p1, p2, p3):
        self.curve([self.current[-1], p1, p2, p3])

    def _closePath(self):
        if len(set(self.current)) < 3:
            raise ValueError("Degenerate pattern contour")
        self.rings.append(self.current)
        self.current = []

    def _endPath(self):
        raise ValueError("Open pattern contour")


def _winding(point, ring):
    x, y = point
    winding = 0
    for a, b in zip(ring, ring[1:] + ring[:1]):
        cross = (b[0]-a[0])*(y-a[1]) - (x-a[0])*(b[1]-a[1])
        if a[1] <= y < b[1] and cross > 0:
            winding += 1
        elif b[1] <= y < a[1] and cross < 0:
            winding -= 1
    return winding


def path_geometry(d):
    """Respect SVG nonzero fill, including overlapping same-winding contours."""
    engine_metadata()
    from shapely.geometry import LineString, LinearRing
    from shapely.ops import polygonize, unary_union
    pen = _FlattenPen()
    parse_path(d, pen)
    if pen.current or not pen.rings or len(pen.rings) > 256:
        raise ValueError("Pattern requires 1..256 closed contours")
    if any(not LinearRing(r).is_simple for r in pen.rings):
        raise ValueError("Pattern input has a self-intersecting contour")
    lines = [LineString(r + [r[0]]) for r in pen.rings]
    faces = list(polygonize(unary_union(lines)))
    filled = [face for face in faces if sum(_winding(tuple(face.representative_point().coords)[0], r)
                                           for r in pen.rings) != 0]
    result = unary_union(filled)
    if result.is_empty or not result.is_valid or result.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Pattern input has no valid filled polygon")
    return result


def _polygons(g):
    return [g] if g.geom_type == "Polygon" else list(g.geoms)


def topology(g):
    polygons = _polygons(g)
    return (len(polygons), sum(len(p.interiors) for p in polygons))


def _offset(g, x, y):
    from shapely.affinity import scale
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return g
    if x*y < 0:
        return _offset(_offset(g, x, 0), 0, y)
    sign = 1 if x+y >= 0 else -1
    # Very narrow ellipses approximate one-axis morphology. The 0.03 unit
    # cross-axis effect is explicit, bounded, and below flattening tolerance.
    rx, ry = max(abs(x), 0.03), max(abs(y), 0.03)
    return scale(scale(g, xfact=1/rx, yfact=1/ry, origin=(500, 500)).buffer(
        sign, quad_segs=4, join_style="mitre", mitre_limit=2),
        xfact=rx, yfact=ry, origin=(500, 500))


def _candidate(g, params, amount):
    from shapely.affinity import scale
    from shapely.ops import transform
    g = _offset(g, params["offset_x"]*amount, params["offset_y"]*amount)
    r = params["corner_radius"]*amount
    if r:
        g = g.buffer(-r, quad_segs=4).buffer(r, quad_segs=4)
    # Width is an invertible affine transform; counter protection need not
    # weaken it when reducing morphology strength.
    g = scale(g, xfact=params["width"], yfact=1, origin=(500, 500))
    amp, phase = params["irregularity"]*amount, params["phase"]
    if amp:
        g = transform(lambda x, y: (x + amp*math.sin(y/110+phase),
                                    y + amp*0.45*math.sin(x/140+phase)), g)
    return g


def geometry_path(g):
    """Canonical four-decimal rings; no machine-specific polygon ordering."""
    from shapely.geometry.polygon import orient
    contours = []
    for polygon in _polygons(g):
        polygon = orient(polygon, sign=1)
        for ring in [polygon.exterior, *polygon.interiors]:
            points = [(round(x, 4), round(y, 4)) for x, y in list(ring.coords)[:-1]]
            points = [p for i, p in enumerate(points) if p != points[i-1]]
            if len(set(points)) < 3:
                raise ValueError("Pattern rounding collapsed a contour")
            start = min(range(len(points)), key=lambda i: points[i])
            points = points[start:] + points[:start]
            contours.append("M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in points) + " Z")
    return " ".join(sorted(contours))


def transform_shape(shape, pattern, key, seed):
    engine_metadata()
    params = pattern.parameters(key, seed)
    # Protect the filled union as well as individual authored stroke paths.
    # Unions matter at crossings and for holes formed by multiple paths.
    from shapely.ops import unary_union
    originals = [path_geometry(p["d"]) for p in shape["paths"]]
    combined = unary_union(originals)
    target_topology = [topology(g) for g in originals] + [topology(combined)]
    reasons = set()
    for attempt in range(9):
        amount = 0.5**attempt
        candidates = [_candidate(g, params, amount) for g in originals]
        if any(g.is_empty or not g.is_valid or g.geom_type not in {"Polygon", "MultiPolygon"} for g in candidates):
            reasons.add("invalid-or-empty-geometry")
            continue
        # Validate the rounded serialized geometry, which is what consumers get.
        try:
            ds = [geometry_path(g) for g in candidates]
            candidates = [path_geometry(d) for d in ds]
        except ValueError:
            reasons.add("rounded-geometry-invalid")
            continue
        union = unary_union(candidates)
        if [topology(g) for g in candidates] + [topology(union)] != target_topology:
            reasons.add("component-or-hole-count-change")
            continue
        if any(not (0 <= g.bounds[0] < g.bounds[2] <= 1000 and 0 <= g.bounds[1] < g.bounds[3] <= 1000)
               for g in candidates):
            reasons.add("bounds-exceeded")
            continue
        if any(not 0.55 <= b.area/a.area <= 1.8 for a, b in zip(originals, candidates)):
            reasons.add("area-change-limit")
            continue
        # Each original hole must retain at least 35% of its area. Counts alone
        # cannot distinguish a lost hole from a newly created hole elsewhere.
        from shapely.geometry import Polygon
        from shapely.affinity import scale
        reference = scale(combined, xfact=params["width"], yfact=1, origin=(500, 500))
        original_holes = [Polygon(r) for p in _polygons(reference) for r in p.interiors]
        new_holes = [Polygon(r) for p in _polygons(union) for r in p.interiors]
        if any(not any(h.intersection(n).area >= h.area*0.35 for n in new_holes) for h in original_holes):
            reasons.add("counter-area-loss")
            continue
        if any(not any(p.intersection(n).area >= p.area*0.35 for n in _polygons(union))
               for p in _polygons(reference)):
            reasons.add("component-area-loss")
            continue
        paths = [{**p, "d": d} for p, d in zip(shape["paths"], ds)]
        return {**shape, "paths": paths}, {
            "parameters": params, "applied_strength": amount,
            "warnings": sorted(reasons), "components": topology(union)[0], "holes": topology(union)[1],
            "review_required": True,
        }
    return shape, {"parameters": params, "applied_strength": 0,
                   "warnings": sorted(reasons | {"pattern-rejected-original-retained"}),
                   "components": topology(combined)[0], "holes": topology(combined)[1], "review_required": True}
