"""Three explicit inputs: authored skeleton, design intent, drawing tool.

Swept elliptical footprints are a geometric experiment, not a physical brush
simulation, trained calligrapher or automatic font/stroke extraction.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass
import json
import math

from .anatomy import AnatomyDNA, BoneRule, InkRule, _width, design_skeleton, inspect_layout
from .bundle import _svg, validate_svg
from .pattern import engine_metadata, path_geometry
from .structure import AuthoredStructureSource, ROLES, _cubic, _grid_path, _UNIT_CIRCLE
from .style import canonical_json, digest, number

ENGINE = "calligraphy-footprint-1"


@dataclass(frozen=True)
class SkeletonPlan:
    points: tuple
    source_widths: tuple
    source_tapers: tuple
    base_width: float
    source_json: str

    def __post_init__(self):
        if not isinstance(self.points, tuple) or len(self.points) != 7:
            raise ValueError("Skeleton plan requires seven cubic roles")
        for points in self.points:
            if not isinstance(points, tuple) or len(points) != 4 or points[0] == points[-1]:
                raise ValueError("Expected nondegenerate cubic role")
            for p in points:
                if not isinstance(p, tuple) or len(p) != 2:
                    raise ValueError("Expected immutable coordinate pair")
                for v in p: number(v, "plan coordinate", 0, 1000)
        for values, label, lo, hi in ((self.source_widths, "source width", 8, 90),
                                       (self.source_tapers, "source taper", .05, 1.3)):
            if not isinstance(values, tuple) or len(values) != 7:
                raise ValueError("Expected seven source metrics")
            for v in values: number(v, label, lo, hi)
        number(self.base_width, "base_width", 8, 90)
        if not isinstance(self.source_json, str) or not isinstance(json.loads(self.source_json), dict):
            raise ValueError("Expected source provenance object")

    @classmethod
    def from_source(cls, source, bones):
        if type(source) is not AuthoredStructureSource or not isinstance(bones, tuple) or len(bones) != 7 or any(type(b) is not BoneRule for b in bones):
            raise ValueError("Explicit authored 赤 source and seven BoneRules required")
        base = source.base
        skeleton = design_skeleton(base, bones)
        widths = tuple(base["horizontal_width"] if r.endswith("bar") else
                       base["diagonal_width"] if r.startswith("outer") else base["vertical_width"] for r in ROLES)
        return cls(tuple(tuple(tuple(p) for p in skeleton[r]) for r in ROLES), widths,
                   tuple(s["end_scale"] for s in base["strokes"]), base["vertical_width"], canonical_json(source.provenance))

    def to_dict(self):
        return {"kind": "authored-aka-plan-1", "character": "赤", "source": json.loads(self.source_json),
                "base_width": self.base_width, "roles": {r: {"points": p, "source_width": w, "source_taper": t}
                for r, p, w, t in zip(ROLES, self.points, self.source_widths, self.source_tapers)}}


@dataclass(frozen=True)
class LetterDNA:
    ink: tuple
    weight: float
    source_width_mix: float
    source_taper_mix: float
    minimum_gap: float = 6

    def __post_init__(self):
        # Reuse the existing bounds without retaining bones in this input.
        checked = AnatomyDNA(ink=self.ink, weight=self.weight, source_width_mix=self.source_width_mix,
                             source_taper_mix=self.source_taper_mix, minimum_gap=self.minimum_gap)
        object.__setattr__(self, "ink", checked.ink)

    def to_dict(self):
        return {"schema_version": 1, "kind": "letter-intent-1", "weight": self.weight,
                "source_width_mix": self.source_width_mix, "source_taper_mix": self.source_taper_mix,
                "minimum_gap": self.minimum_gap, "roles": {r: asdict(ink) for r, ink in zip(ROLES, self.ink)}}

    @classmethod
    def from_dict(cls, data):
        fields = {"schema_version", "kind", "weight", "source_width_mix", "source_taper_mix", "minimum_gap", "roles"}
        if (not isinstance(data, dict) or set(data) != fields or type(data["schema_version"]) is not int
                or data["schema_version"] != 1 or data["kind"] != "letter-intent-1"
                or not isinstance(data["roles"], dict) or set(data["roles"]) != set(ROLES)):
            raise ValueError("Expected exact letter-intent-1 schema")
        for ink in data["roles"].values():
            if not isinstance(ink, dict) or set(ink) != set(InkRule.__dataclass_fields__):
                raise ValueError("Expected complete ink intent per role")
        return cls(tuple(InkRule(**data["roles"][r]) for r in ROLES), **{
            k: data[k] for k in fields - {"schema_version", "kind", "roles"}})


@dataclass(frozen=True)
class CalligraphyTool:
    mode: str
    angle: float = 0  # fixed nib angle for broad tool, clockwise in SVG
    aspect: float = 1  # minor/major diameter
    pressure: tuple = (1, 1, 1, 1, 1)

    def __post_init__(self):
        if not isinstance(self.mode, str) or self.mode not in {"round", "broad", "brush"}:
            raise ValueError("Unknown calligraphy tool")
        number(self.angle, "nib angle", -90, 90)
        number(self.aspect, "nib aspect", .1, 1)
        if not isinstance(self.pressure, (list, tuple)) or len(self.pressure) != 5:
            raise ValueError("Expected five pressure samples")
        object.__setattr__(self, "pressure", tuple(self.pressure))
        for v in self.pressure: number(v, "pressure", .05, 1.5)
        if self.mode != "brush" and self.pressure != (1, 1, 1, 1, 1):
            raise ValueError("Pressure changes are only supported by the brush model")
        if self.mode != "broad" and self.angle != 0:
            raise ValueError("Only the broad model accepts a fixed nib angle")
        if self.mode == "round" and self.aspect != 1:
            raise ValueError("Round tool requires a circular nib")

    @classmethod
    def preset(cls, mode):
        if mode == "round": return cls(mode)
        if mode == "broad": return cls(mode, angle=35, aspect=.18)
        if mode == "brush": return cls(mode, aspect=.5, pressure=(.35, .85, 1.05, 1.15, .25))
        raise ValueError("Unknown calligraphy tool")

    def to_dict(self):
        return {"schema_version": 1, "kind": "drawing-tool-1", **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if (not isinstance(data, dict) or set(data) != {"schema_version", "kind", *cls.__dataclass_fields__}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1
                or data["kind"] != "drawing-tool-1"):
            raise ValueError("Expected exact drawing-tool-1 schema")
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


def sample_stroke(points):
    """129 equal-distance samples using a 1025-point cubic arc-length lookup."""
    lookup = [_cubic(points, i/1024) for i in range(1025)]
    lengths = [0.]
    for a, b in zip(lookup, lookup[1:]): lengths.append(lengths[-1]+math.dist(a, b))
    if lengths[-1] < 1: raise ValueError("Degenerate calligraphy centerline")
    samples, tangents = [], []
    for i in range(129):
        target = lengths[-1]*i/128
        j = min(1024, max(1, bisect_left(lengths, target)))
        span = lengths[j]-lengths[j-1]
        t = (j-1+(target-lengths[j-1])/span)/1024 if span else (j-1)/1024
        samples.append(_cubic(points, t))
        r = 1-t
        dx, dy = (3*math.fsum((r*r*(points[1][a]-points[0][a]),
                               2*r*t*(points[2][a]-points[1][a]), t*t*(points[3][a]-points[2][a]))) for a in (0, 1))
        length = math.hypot(dx, dy)
        if length < .000001: raise ValueError("Degenerate calligraphy tangent")
        tangents.append((dx/length, dy/length))
    from shapely.geometry import LineString
    if not LineString(samples).is_simple: raise ValueError("Centerline crosses itself")
    return samples, tangents


def projected_width(diameter, tangent, tool, pressure=1):
    if tool.mode == "round": return diameter
    if tool.mode == "brush": return diameter*pressure
    nx, ny = -tangent[1], tangent[0]
    a = math.radians(tool.angle)
    dot_major = nx*math.cos(a)+ny*math.sin(a)
    dot_minor = -nx*math.sin(a)+ny*math.cos(a)
    return diameter*math.sqrt(dot_major**2+(tool.aspect*dot_minor)**2)


def sweep_stroke(points, ink, nominal, source_taper, taper_mix, tool):
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    samples, tangents = sample_stroke(points)
    footprints, desired, projected, pressures = [], [], [], []
    pressure_rule = InkRule(widths=tool.pressure)
    for i, ((x, y), (tx, ty)) in enumerate(zip(samples, tangents)):
        u = i/128
        width = nominal*_width(ink, u)*(1-taper_mix*(1-source_taper)*u*u)
        pressure = _width(pressure_rule, u) if tool.mode == "brush" else 1
        angle = math.atan2(ty, tx)+math.pi/2 if tool.mode == "brush" else math.radians(tool.angle)
        c, s = math.cos(angle), math.sin(angle)
        radius = width*pressure/2
        # Intent's side bias offsets the contact center along the local normal.
        x, y = x-ty*width*ink.bias, y+tx*width*ink.bias
        footprint = (Point(x, y) if radius < .000001 else Polygon([
            (x+radius*(c*a-s*b*tool.aspect), y+radius*(s*a+c*b*tool.aspect)) for a, b in _UNIT_CIRCLE]))
        footprints.append(footprint)
        desired.append(width); pressures.append(pressure)
        projected.append(projected_width(width, (tx, ty), tool, pressure))
    # The swept model intentionally uses Boolean assembly, unlike the older
    # normal-envelope renderer. Join adjacent nib footprints by convex hulls.
    g = unary_union([a.union(b).convex_hull for a, b in zip(footprints, footprints[1:])])
    for index, direction, cap in ((0, 1, ink.start_cap), (-1, -1, ink.end_cap)):
        if cap == "flat":
            x, y = samples[index]; tx, ty = tangents[index]; nx, ny = -ty, tx
            clip = Polygon([(x+nx*3000, y+ny*3000), (x-nx*3000, y-ny*3000),
                            (x-nx*3000+direction*tx*3000, y-ny*3000+direction*ty*3000),
                            (x+nx*3000+direction*tx*3000, y+ny*3000+direction*ty*3000)])
            g = g.intersection(clip)
    if g.geom_type != "Polygon" or not g.is_valid or g.is_empty or len(g.interiors):
        raise ValueError("Calligraphy sweep is not one simple closed role")
    if not (0 <= g.bounds[0] < g.bounds[2] <= 1000 and 0 <= g.bounds[1] < g.bounds[3] <= 1000):
        raise ValueError("Calligraphy sweep outside the 1000-unit box")
    indices = (0, 32, 64, 96, 128)
    return g, {"desired_width": [round(desired[i], 4) for i in indices],
               "projected_width": [round(projected[i], 4) for i in indices],
               "pressure": [round(pressures[i], 4) for i in indices]}


def canonicalize_sweep(polygon):
    """Quantize a valid swept role while enforcing the recorded error bound."""
    from shapely.geometry import Polygon
    coords = [(round(x, 2), round(y, 2)) for x, y in list(polygon.exterior.coords)[:-1]]
    coords = [p for i, p in enumerate(coords) if p != coords[i-1]]
    snapped = Polygon(coords)
    if not snapped.is_valid or snapped.is_empty or snapped.hausdorff_distance(polygon) > .0072:
        raise ValueError("Calligraphy coordinate rounding lost a valid role boundary")
    path = _grid_path(snapped)
    exported = path_geometry(path)
    if exported.hausdorff_distance(polygon) > .0173:
        raise ValueError("Calligraphy export exceeded boundary error allowance")
    return path, exported


def draw_glyph(plan, dna, tool):
    if type(plan) is not SkeletonPlan or type(dna) is not LetterDNA or type(tool) is not CalligraphyTool:
        raise ValueError("Expected separate SkeletonPlan, LetterDNA and CalligraphyTool")
    engine = engine_metadata()
    paths, polygons, diagnostics = [], {}, {}
    for role, points, source_width, taper, ink in zip(ROLES, plan.points, plan.source_widths, plan.source_tapers, dna.ink):
        nominal = dna.weight*(plan.base_width*ink.width_ratio*(1-dna.source_width_mix)+source_width*dna.source_width_mix)
        polygon, qa = sweep_stroke(points, ink, nominal, taper, dna.source_taper_mix, tool)
        d, exported = canonicalize_sweep(polygon)
        path = {"id": role, "d": d}
        paths.append(path); polygons[role] = exported; diagnostics[role] = qa
    gaps = inspect_layout(polygons, dna.minimum_gap)
    svg = _svg({"paths": paths}, {"fill": "#171512"})
    validate_svg(svg)
    return svg, {"engine": ENGINE, "geometry_engine": engine, "plan_sha256": digest(plan.to_dict()),
                 "dna_sha256": digest(dna.to_dict()), "tool_sha256": digest(tool.to_dict()),
                 "tool": tool.to_dict(), "landmarks": dict(zip(ROLES, plan.points)),
                 "stroke_diagnostics": diagnostics, "sample_u": [0, .25, .5, .75, 1],
                 "clearances": gaps, "silhouettes": 3, "stroke_order_inferred": False,
                 "physical_brush_simulation": False, "optical_correction": False,
                 "sampling": {"arc_lookup": 1025, "footprints": 129, "ellipse_vertices": 32, "grid": .01,
                              "max_export_boundary_error": .0173},
                 "visual_review": "required"}
