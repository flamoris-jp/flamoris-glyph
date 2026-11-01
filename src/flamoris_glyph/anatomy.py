"""Experimental role grammar: redesign centerlines, then grow role-specific ink.

Only the explicit authored 赤 maps are supported. No font/raster decomposition.
This standalone study API does not change the bundle contract or legacy renderer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

from .bundle import _svg, validate_svg
from .pattern import engine_metadata, path_geometry
from .structure import AuthoredStructureSource, ROLES, _cubic, _grid_path, _UNIT_CIRCLE
from .style import digest, number

ENGINE = "role-anatomy-study-1"


@dataclass(frozen=True)
class BoneRule:
    length: float = 1
    angle: float = 0  # degrees; positive is clockwise in SVG coordinates
    end_turn: float = 0  # independent direction of the final handle
    bend: float = 0  # middle control-point displacement along the chord normal
    dx: float = 0
    dy: float = 0
    anchor: float = .5

    def __post_init__(self):
        for name, low, high in (("length", .65, 1.5), ("angle", -25, 25), ("end_turn", -65, 65),
                                ("bend", -70, 70), ("dx", -100, 100),
                                ("dy", -80, 80), ("anchor", 0, 1)):
            number(getattr(self, name), name, low, high)


@dataclass(frozen=True)
class InkRule:
    # Full widths at five independently positioned stations along the bone.
    widths: tuple = (1, 1, 1, 1, 1)
    stations: tuple = (0, .25, .5, .75, 1)
    width_ratio: float = 1
    bias: float = 0  # side allocation; preserves total width
    start_cap: str = "flat"
    end_cap: str = "flat"

    def __post_init__(self):
        if not isinstance(self.widths, (list, tuple)) or len(self.widths) != 5:
            raise ValueError("Ink requires five width stations")
        object.__setattr__(self, "widths", tuple(self.widths))
        if not isinstance(self.stations, (list, tuple)) or len(self.stations) != 5:
            raise ValueError("Ink requires five station positions")
        object.__setattr__(self, "stations", tuple(self.stations))
        for t in self.stations:
            number(t, "station position", 0, 1)
        if self.stations[0] != 0 or self.stations[-1] != 1 or any(b-a < .04 for a, b in zip(self.stations, self.stations[1:])):
            raise ValueError("Stations must increase from 0 to 1, at least .04 apart")
        for width in self.widths:
            number(width, "width station", 0, 2)
        if min(self.widths[1:4]) <= 0 or max(self.widths) == 0:
            raise ValueError("Only endpoint width stations may be zero")
        for cap, width in ((self.start_cap, self.widths[0]), (self.end_cap, self.widths[-1])):
            if cap not in {"flat", "round", "point"} or (cap == "point") != (width == 0):
                raise ValueError("Point caps require zero endpoint width; other caps require positive width")
        number(self.width_ratio, "width_ratio", .1, 2)
        number(self.bias, "bias", -.45, .45)


@dataclass(frozen=True)
class AnatomyDNA:
    bones: tuple = field(default_factory=lambda: tuple(BoneRule() for _ in ROLES))
    ink: tuple = field(default_factory=lambda: tuple(InkRule() for _ in ROLES))
    weight: float = 1
    source_width_mix: float = 1
    source_taper_mix: float = 1
    minimum_gap: float = 6

    def __post_init__(self):
        for name, kind in (("bones", BoneRule), ("ink", InkRule)):
            values = getattr(self, name)
            if not isinstance(values, (list, tuple)) or len(values) != len(ROLES) or any(type(v) is not kind for v in values):
                raise ValueError(f"{name} requires seven ordered role rules")
            object.__setattr__(self, name, tuple(values))
        for name, low, high in (("weight", .5, 2.2), ("source_width_mix", 0, 1),
                                ("source_taper_mix", 0, 1), ("minimum_gap", 0, 35)):
            number(getattr(self, name), name, low, high)

    def to_dict(self):
        return {"schema_version": 1, "kind": ENGINE,
                "weight": self.weight, "source_width_mix": self.source_width_mix,
                "source_taper_mix": self.source_taper_mix, "minimum_gap": self.minimum_gap,
                "roles": {role: {"bone": asdict(bone), "ink": asdict(ink)}
                          for role, bone, ink in zip(ROLES, self.bones, self.ink)}}

    @classmethod
    def from_dict(cls, data):
        fields = {"schema_version", "kind", "weight", "source_width_mix", "source_taper_mix", "minimum_gap", "roles"}
        if (not isinstance(data, dict) or set(data) != fields or type(data["schema_version"]) is not int
                or data["schema_version"] != 1 or data["kind"] != ENGINE
                or not isinstance(data["roles"], dict) or set(data["roles"]) != set(ROLES)):
            raise ValueError("Expected exact role-anatomy-study-1 schema")
        bones, ink = [], []
        for role in ROLES:
            entry = data["roles"][role]
            if not isinstance(entry, dict) or set(entry) != {"bone", "ink"}:
                raise ValueError("Each role requires bone and ink rules")
            for name, kind, target in (("bone", BoneRule, bones), ("ink", InkRule, ink)):
                rule = entry[name]
                if not isinstance(rule, dict) or set(rule) != set(kind.__dataclass_fields__):
                    raise ValueError(f"Incomplete {name} rule")
                target.append(kind(**rule))
        return cls(tuple(bones), tuple(ink), **{k: data[k] for k in fields - {"schema_version", "kind", "roles"}})


def design_bone(stroke, rule):
    points = stroke["points"]
    anchor = _cubic(points, rule.anchor)
    vx, vy = points[-1][0]-points[0][0], points[-1][1]-points[0][1]
    length = math.hypot(vx, vy)
    nx, ny = -vy/length, vx/length
    angle = math.radians(rule.angle)
    c, s = math.cos(angle), math.sin(angle)
    result = []
    for i, (x, y) in enumerate(points):
        x, y = (x-anchor[0])*rule.length, (y-anchor[1])*rule.length
        if i in {1, 2}:
            x, y = x+nx*rule.bend, y+ny*rule.bend
        result.append([round(anchor[0]+c*x-s*y+rule.dx, 4),
                       round(anchor[1]+s*x+c*y+rule.dy, 4)])
    angle = math.radians(rule.end_turn)
    c, s = math.cos(angle), math.sin(angle)
    dx, dy = result[3][0]-result[2][0], result[3][1]-result[2][1]
    result[2] = [round(result[3][0]-c*dx+s*dy, 4), round(result[3][1]-s*dx-c*dy, 4)]
    return result


def _width(rule, t):
    # Monotone cubic Hermite interpolation: shared slopes avoid scalloped
    # edges at every station; no overshoot beyond the specified extrema.
    x, y = rule.stations, rule.widths
    h = [b-a for a, b in zip(x, x[1:])]
    d = [(b-a)/step for a, b, step in zip(y, y[1:], h)]

    def endpoint(a, b, ha, hb):
        m = ((2*ha+hb)*a-ha*b)/(ha+hb)
        return 0 if m*a <= 0 else math.copysign(min(abs(m), 3*abs(a)), a)

    slopes = [endpoint(d[0], d[1], h[0], h[1])]
    for i in range(1, 4):
        w1, w2 = 2*h[i]+h[i-1], h[i]+2*h[i-1]
        slopes.append(0 if d[i-1]*d[i] <= 0 else (w1+w2)/(w1/d[i-1]+w2/d[i]))
    slopes.append(endpoint(d[-1], d[-2], h[-1], h[-2]))
    i = next((j for j in range(4) if t <= x[j+1]), 3)
    u = (t-x[i])/h[i]
    return ((2*u**3-3*u*u+1)*y[i]+(u**3-2*u*u+u)*h[i]*slopes[i]
            +(-2*u**3+3*u*u)*y[i+1]+(u**3-u*u)*h[i]*slopes[i+1])


def design_skeleton(base, bones):
    """Apply role rules, then attach named junctions to the redesigned main bar.

    Explicit 赤 grammar, not an inferred repair. Outer marks stay unattached.
    """
    result = {stroke["id"]: design_bone(stroke, rule)
              for stroke, rule in zip(base["strokes"], bones)}
    bar = result["main-bar"]

    def on_bar(x):
        if not bar[0][0] <= x <= bar[-1][0]:
            raise ValueError("Required junction is outside the redesigned main bar")
        lo, hi = 0., 1.
        for _ in range(30):
            mid = (lo+hi)/2
            if _cubic(bar, mid)[0] < x:
                lo = mid
            else:
                hi = mid
        return [round(v, 4) for v in _cubic(bar, (lo+hi)/2)]

    for role, endpoint, handle in (("top-stem", 3, 2), ("inner-left", 0, 1), ("inner-right", 0, 1)):
        points = result[role]
        target = on_bar(points[endpoint][0])
        delta = [target[a]-points[endpoint][a] for a in (0, 1)]
        points[endpoint] = target
        points[handle] = [round(points[handle][a]+delta[a], 4) for a in (0, 1)]
    return result


def grow_ink(points, rule, nominal_width, source_end, taper_mix):
    from shapely.geometry import Polygon
    samples = [_cubic(points, i/128) for i in range(129)]
    left, right, widths, frames = [], [], [], []
    for i, (x, y) in enumerate(samples):
        before, after = samples[max(0, i-1)], samples[min(128, i+1)]
        dx, dy = after[0]-before[0], after[1]-before[1]
        length = math.hypot(dx, dy)
        if length < .000001:
            raise ValueError("Degenerate anatomy tangent")
        tx, ty = dx/length, dy/length
        nx, ny = -ty, tx
        t = i/128
        w = nominal_width*_width(rule, t)*(1-taper_mix*(1-source_end)*t*t)
        widths.append(w)
        frames.append((tx, ty, nx, ny))
        left.append((x+nx*w*(.5+rule.bias), y+ny*w*(.5+rule.bias)))
        right.append((x-nx*w*(.5-rule.bias), y-ny*w*(.5-rule.bias)))

    def arc(index, direction):
        x, y = samples[index]
        tx, ty, nx, ny = frames[index]
        radius = widths[index]/2
        # Offset the cap center by the same side bias as the envelope.
        x, y = x+nx*widths[index]*rule.bias, y+ny*widths[index]*rule.bias
        return [(x+direction*radius*(nx*u+tx*v), y+direction*radius*(ny*u+ty*v))
                for u, v in _UNIT_CIRCLE[:17]][1:-1]

    coords = left+(arc(128, 1) if rule.end_cap == "round" else [])
    coords += list(reversed(right))+(arc(0, -1) if rule.start_cap == "round" else [])
    coords = [(round(x, 2), round(y, 2)) for x, y in coords]
    coords = [p for i, p in enumerate(coords) if p != coords[i-1]]
    polygon = Polygon(coords)
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        raise ValueError("Ink envelope self-intersects; revise bone curvature or width profile")
    if not (0 <= polygon.bounds[0] < polygon.bounds[2] <= 1000 and 0 <= polygon.bounds[1] < polygon.bounds[3] <= 1000):
        raise ValueError("Anatomy outline outside the 1000-unit box")
    return polygon, [round(widths[i], 4) for i in (0, 32, 64, 96, 128)]


def design_glyph(source, dna, char="赤"):
    """Return closed path-only SVG and diagnostics, or fail without repairs.

    Source widths/taper can be blended with DNA; source serif shapes are not
    reproduced. The authored role map is the only anatomy authority.
    """
    from shapely.ops import unary_union
    if type(source) is not AuthoredStructureSource or type(dna) is not AnatomyDNA or char != "赤":
        raise ValueError("Anatomy study requires an explicit authored 赤 source and AnatomyDNA")
    engine = engine_metadata()  # same pinned optional geometry dependency
    base = source.base
    skeleton = design_skeleton(base, dna.bones)
    paths, polygons, landmarks, widths = [], {}, {}, {}
    for stroke, ink in zip(base["strokes"], dna.ink):
        role = stroke["id"]
        points = skeleton[role]
        source_width = (base["horizontal_width"] if role.endswith("bar") else
                        base["diagonal_width"] if role.startswith("outer") else base["vertical_width"])
        designed = base["vertical_width"]*ink.width_ratio
        nominal = dna.weight*(designed*(1-dna.source_width_mix)+source_width*dna.source_width_mix)
        polygon, sample_widths = grow_ink(points, ink, nominal, stroke["end_scale"], dna.source_taper_mix)
        path = {"id": role, "d": _grid_path(polygon)}
        paths.append(path)
        polygons[role], landmarks[role], widths[role] = path_geometry(path["d"]), points, sample_widths
    # Boolean unions are diagnostic only, never used to construct exported ink.
    body = unary_union([polygons[r] for r in ROLES[:5]])
    if body.geom_type != "Polygon" or len(body.interiors):
        raise ValueError("Required body connections or open inner white space were lost")
    for a, b in (("top-bar", "top-stem"), ("main-bar", "top-stem"),
                 ("main-bar", "inner-left"), ("main-bar", "inner-right")):
        if polygons[a].intersection(polygons[b]).area < 1:
            raise ValueError(f"Required role connection lost: {a} / {b}")
    gaps = {r: round(polygons[r].distance(body), 4) for r in ROLES[5:]}
    gaps["outer-pair"] = round(polygons[ROLES[5]].distance(polygons[ROLES[6]]), 4)
    gaps["upper-bars"] = round(polygons["top-bar"].distance(polygons["main-bar"]), 4)
    if any(value <= 0 or value < dna.minimum_gap for value in gaps.values()):
        raise ValueError(f"White-space clearance below {dna.minimum_gap}: {gaps}")
    silhouette = unary_union(list(polygons.values()))
    if silhouette.geom_type != "MultiPolygon" or len(silhouette.geoms) != 3:
        raise ValueError("Expected body plus two separate outer marks")
    svg = _svg({"paths": paths}, {"fill": "#171512"})
    validate_svg(svg)
    qa = {"engine": ENGINE, "geometry_engine": engine, "source": source.provenance,
          "dna_sha256": digest(dna.to_dict()), "source_family": base["family"],
          "landmarks": landmarks, "width_stations": widths, "width_sample_t": [0, .25, .5, .75, 1],
          "clearances": gaps, "junctions": "explicit-main-bar-attachments",
          "silhouettes": 3, "semantic_roles": list(ROLES), "visual_review": "required",
          "source_serifs_reproduced": False, "automatic_optical_correction": False}
    return svg, qa
