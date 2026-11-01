"""Authored seven-role 赤 study: source anatomy and design DNA stay separate.

This is explicit authoring, not stroke extraction from arbitrary font outlines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import re

from .geometry import warp
from .pattern import engine_metadata, geometry_path
from .style import digest, number

ENGINE_VERSION = "authored-structure-1"
ROLES = ("top-bar", "top-stem", "main-bar", "inner-left", "inner-right", "outer-left", "outer-right")
PROFILES = ("baseline", "heavy-condensed-headline", "elegant-high-contrast-editorial", "showa-retro-signboard")


@dataclass(frozen=True)
class StructureDNA:
    profile: str = "baseline"
    width: float = 1
    bar_span: float = 1
    junction_shift: float = 0
    lower_spread: float = 1
    curve_gain: float = 0
    weight: float = 1
    contrast: float = 0
    terminal_style: str = "inherit"
    terminal_gain: float = 1
    variation: float = 0

    def __post_init__(self):
        if self.profile not in PROFILES or self.terminal_style not in {"inherit", "block", "hairline", "round"}:
            raise ValueError("Unsupported structural profile or terminal style")
        for name, low, high in (("width", .65, 1.12), ("bar_span", .7, 1.15),
                                ("junction_shift", -65, 35), ("lower_spread", .7, 1.5),
                                ("curve_gain", -.5, 1.2), ("weight", .65, 2.1),
                                ("contrast", -1, 1), ("terminal_gain", 0, 1.5), ("variation", 0, 1)):
            number(getattr(self, name), name, low, high)

    @classmethod
    def preset(cls, profile):
        if profile == "baseline":
            return cls()
        if profile == "heavy-condensed-headline":
            return cls(profile, width=.76, bar_span=.82, junction_shift=-45, lower_spread=.84,
                       curve_gain=-.4, weight=1.9, contrast=-.9, terminal_style="block", variation=.35)
        if profile == "elegant-high-contrast-editorial":
            return cls(profile, width=.98, bar_span=1.06, junction_shift=12, lower_spread=1.28,
                       curve_gain=.85, weight=1.12, contrast=.85, terminal_style="hairline", terminal_gain=1.25, variation=.35)
        if profile == "showa-retro-signboard":
            return cls(profile, width=1.06, bar_span=1.03, junction_shift=-15, lower_spread=1.25,
                       curve_gain=1.05, weight=1.4, contrast=-.65, terminal_style="round", terminal_gain=1.15, variation=.35)
        raise ValueError("Unknown structural profile")

    def to_dict(self):
        return {"schema_version": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Structure DNA must be an object")
        d = dict(data)
        version = d.pop("schema_version", None)
        if type(version) is not int or version != 1 or set(d) != set(cls.__dataclass_fields__):
            raise ValueError("Structure DNA requires schema 1 and exactly the documented fields")
        return cls(**d)

    def parameters(self, key, seed):
        raw = bytes.fromhex(digest([ENGINE_VERSION, seed, key, self.profile]))
        samples = [int.from_bytes(raw[i:i+4], "big")/(2**32-1)*2-1 for i in (0, 4, 8)]
        p = asdict(self)
        p["weight"] = round(self.weight*(1+samples[0]*.045*self.variation), 6)
        p["lower_spread"] = round(self.lower_spread*(1+samples[1]*.025*self.variation), 6)
        p["curve_gain"] = round(self.curve_gain+samples[2]*.08*self.variation, 6)
        return p


def structure_engine():
    return {**engine_metadata(), "version": ENGINE_VERSION, "samples_per_stroke": 65, "assembly_grid": .01,
            "assembly_hole_area": .01, "assembly_hole_budget": .05, "sample_precision": 4, "circle_points": 32}


class AuthoredStructureSource:
    def __init__(self, data, base_id):
        if (not isinstance(data, dict) or set(data) != {"schema_version", "character", "license_note", "bases"}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["character"] != "赤"
                or not isinstance(data["license_note"], str) or not data["license_note"].strip()
                or not isinstance(data["bases"], dict) or not 1 <= len(data["bases"]) <= 8):
            raise ValueError("Expected explicit authored 赤 structure schema 1")
        if not isinstance(base_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", base_id) or base_id not in data["bases"]:
            raise ValueError("Unknown authored base ID")
        self.base = json.loads(json.dumps(data["bases"][base_id], allow_nan=False))
        b = self.base
        if (not isinstance(b, dict) or set(b) != {"family", "horizontal_width", "vertical_width", "diagonal_width", "serif_size", "strokes"}
                or b["family"] not in {"gothic", "mincho"} or not isinstance(b["strokes"], list)
                or any(not isinstance(s, dict) for s in b["strokes"])
                or [s.get("id") for s in b["strokes"]] != list(ROLES)):
            raise ValueError("Authored base needs a family and seven explicit ordered roles")
        for n in ("horizontal_width", "vertical_width", "diagonal_width"):
            number(b[n], n, 8, 90)
        number(b["serif_size"], "serif_size", 0, 30)
        for s in b["strokes"]:
            if (set(s) != {"id", "points", "end_scale", "terminal"} or s["terminal"] not in {"tome", "hane", "harai"}
                    or not isinstance(s["points"], list) or len(s["points"]) != 4):
                raise ValueError("Each authored role needs four cubic points and terminal metadata")
            number(s["end_scale"], "end_scale", .05, 1.3)
            for p in s["points"]:
                if not isinstance(p, list) or len(p) != 2:
                    raise ValueError("Expected [x, y] points")
                for coordinate in p:
                    number(coordinate, "authored coordinate", 100, 900)
            if s["points"][0] == s["points"][-1]:
                raise ValueError("Degenerate authored centerline")
        self.provenance = {"kind": "authored-skeleton",
                           "sha256": digest({"base": b, "character": "赤", "renderer": ENGINE_VERSION}),
                           "license_note": f"{data['license_note']}; manually authored {base_id} base, {ENGINE_VERSION}"}

    def close(self):
        pass

    def render(self, char, params, style):
        raise ValueError("AuthoredStructureSource requires explicit structure=StructureDNA")

    def render_structured(self, char, params, style, dna, key, seed):
        if char != "赤":
            raise ValueError(f"No authored structural map for {char!r}; this study supports only 赤")
        from shapely.errors import GEOSException
        try:
            return render_structure(self.base, dna.parameters(key, seed), params)
        except GEOSException as error:
            raise ValueError("Structured envelope assembly failed; revise the authored map") from error


def _points(stroke, p):
    role = stroke["id"]
    points = [list(point) for point in stroke["points"]]
    if role in {"top-bar", "main-bar"}:
        for point in points:
            point[0] = 500+(point[0]-500)*p["bar_span"]
            point[1] += p["junction_shift"]*(.5 if role == "top-bar" else 1)
    elif role == "top-stem":
        for i, point in enumerate(points):
            point[1] += p["junction_shift"]*(.25+.75*i/3)
    else:
        direction = -1 if role.endswith("left") else 1
        for i, point in enumerate(points):
            t = i/3
            point[0] = 500+(point[0]-500)*(1+(p["lower_spread"]-1)*t*t)
            point[1] += p["junction_shift"]*(1-t)
            if i in {1, 2}:
                point[0] += direction*p["curve_gain"]*(34 if role.startswith("inner") else 24)
                point[1] += p["curve_gain"]*(18 if i == 1 else -12)
        # Curve the lower sweep at the terminal as well, not only its weight.
        points[-1][0] += direction*p["curve_gain"]*(28 if role.startswith("inner") else 12)
    return [[round(500+(x-500)*p["width"], 4), round(y, 4)] for x, y in points]


def _cubic(points, t):
    # Python 3.12 changed float sum() accumulation. Use explicit binary
    # products and fsum so a grid-boundary sample stays portable on 3.11/3.12.
    r = 1-t
    coefficients = (r*r*r, 3*r*r*t, 3*r*t*t, t*t*t)
    return tuple(math.fsum(c*v[a] for c, v in zip(coefficients, points)) for a in (0, 1))

# Fixed unit-circle coordinates avoid platform libm differences in GEOS buffer.
_UNIT_CIRCLE = ((1.0, 0.0), (0.980785280403, 0.195090322016), (0.923879532511, 0.382683432365), (0.831469612303, 0.55557023302), (0.707106781187, 0.707106781187), (0.55557023302, 0.831469612303), (0.382683432365, 0.923879532511), (0.195090322016, 0.980785280403), (0.0, 1.0), (-0.195090322016, 0.980785280403), (-0.382683432365, 0.923879532511), (-0.55557023302, 0.831469612303), (-0.707106781187, 0.707106781187), (-0.831469612303, 0.55557023302), (-0.923879532511, 0.382683432365), (-0.980785280403, 0.195090322016), (-1.0, 0.0), (-0.980785280403, -0.195090322016), (-0.923879532511, -0.382683432365), (-0.831469612303, -0.55557023302), (-0.707106781187, -0.707106781187), (-0.55557023302, -0.831469612303), (-0.382683432365, -0.923879532511), (-0.195090322016, -0.980785280403), (-0.0, -1.0), (0.195090322016, -0.980785280403), (0.382683432365, -0.923879532511), (0.55557023302, -0.831469612303), (0.707106781187, -0.707106781187), (0.831469612303, -0.55557023302), (0.923879532511, -0.382683432365), (0.980785280403, -0.195090322016))


def _disc(center, radius, sides=32):
    from shapely.geometry import Polygon
    x, y = center
    return Polygon([(round(x+u*radius, 4), round(y+v*radius, 4))
                    for u, v in _UNIT_CIRCLE[::32//sides]])


def _stroke_polygon(points, start_width, end_width, cap):
    from shapely.geometry import Polygon
    from shapely import union_all
    samples = [tuple(round(v, 4) for v in _cubic(points, i/64)) for i in range(65)]
    widths = []
    for i, (x, y) in enumerate(samples):
        t = i/64
        before, after = samples[max(0, i-1)], samples[min(64, i+1)]
        dx, dy = after[0]-before[0], after[1]-before[1]
        length = math.sqrt(dx*dx+dy*dy)
        if length < 1e-6:
            raise ValueError("Degenerate structured tangent")
        width = start_width+(end_width-start_width)*t*t
        if cap == "round":
            width *= 1+.12*math.sin(math.pi*t)
        widths.append(round(width, 4))
    # Build a filled swept envelope from segment trapezoids and joint discs.
    # This defines thick curved strokes directly; no buffer(0) repair of a
    # self-crossing outline or loss of the authored centerline is involved.
    pieces = []
    for i, (a, b) in enumerate(zip(samples, samples[1:])):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.sqrt(dx*dx+dy*dy)
        if length < 1e-6:
            raise ValueError("Degenerate structured segment")
        nx, ny = -dy/length, dx/length
        ra, rb = widths[i]/2, widths[i+1]/2
        pieces.append(Polygon([(round(x, 4), round(y, 4)) for x, y in
                               [(a[0]+nx*ra, a[1]+ny*ra), (b[0]+nx*rb, b[1]+ny*rb),
                                (b[0]-nx*rb, b[1]-ny*rb), (a[0]-nx*ra, a[1]-ny*ra)]]))
    pieces.extend(_disc(samples[i], widths[i]/2, sides=16) for i in range(1, 64))
    g = union_all(pieces, grid_size=.01)
    if cap == "round":
        g = union_all([g, _disc(samples[0], round(start_width/2, 4)),
                       _disc(samples[-1], round(end_width/2, 4))], grid_size=.01)
    else:
        # Joint discs must not accidentally round a requested flat terminal.
        # Keep the inward endpoint tangent half-plane at each end.
        for endpoint, adjacent in ((samples[0], samples[1]), (samples[-1], samples[-2])):
            dx, dy = adjacent[0]-endpoint[0], adjacent[1]-endpoint[1]
            length = math.sqrt(dx*dx+dy*dy)
            tx, ty, nx, ny = dx/length, dy/length, -dy/length, dx/length
            x, y = endpoint
            plane = Polygon([(x+nx*4000, y+ny*4000), (x-nx*4000, y-ny*4000),
                             (x-nx*4000+tx*4000, y-ny*4000+ty*4000),
                             (x+nx*4000+tx*4000, y+ny*4000+ty*4000)])
            g = g.intersection(plane)
    return g, [round(widths[i], 4) for i in (0, 32, 64)]


def render_structure(base, p, legacy_params):
    from shapely import union_all, set_precision
    from shapely.geometry import Polygon
    from shapely.ops import transform
    vertical = base["vertical_width"]*p["weight"]
    ratio = base["horizontal_width"]/base["vertical_width"]
    target = .13 if p["contrast"] >= 0 else 1
    ratio += (target-ratio)*abs(p["contrast"])
    horizontal = vertical*ratio
    diagonal = base["diagonal_width"]*p["weight"]
    terminal = p["terminal_style"]
    if terminal == "inherit":
        terminal = "hairline" if base["family"] == "mincho" else "block"
    serif = ((base["serif_size"] if p["terminal_style"] == "inherit" else 19)
             *p["terminal_gain"] if terminal == "hairline" else 0)
    paths, landmarks, widths, slivers = [], {}, {}, {}
    for stroke in base["strokes"]:
        role = stroke["id"]
        points = _points(stroke, p)
        width = horizontal if role.endswith("bar") else vertical if role == "top-stem" or role.startswith("inner") else diagonal
        end_scale = stroke["end_scale"]
        if terminal == "block":
            end_scale += (1-end_scale)*.9
        elif terminal == "hairline" and role not in {"top-bar", "main-bar", "top-stem"}:
            end_scale = max(.07, end_scale*.28)
        elif terminal == "round":
            end_scale = 1.12 if role.startswith("outer") else .96
        g, sample_widths = _stroke_polygon(points, width, width*end_scale, terminal)
        if serif and role.endswith("bar"):
            # Explicit author-selected bar terminals, not inferred from a font.
            x, y = points[-1]
            g = union_all([g, Polygon([(x-serif*.95, y+width/2), (x+serif*.2, y+width/2),
                                       (x-serif*.3, y-serif*1.1)])], grid_size=.01)
        if serif and role == "top-stem":
            x, y = points[0]
            g = union_all([g, Polygon([(x-width*.8, y-5), (x+width*.9, y+5),
                                       (x+width*.43, y+serif*.6), (x-width*.45, y+serif*.3)])], grid_size=.01)
        if terminal == "round" and role.startswith("inner"):
            g = union_all([g, _disc(points[-1], round(width*.57*p["terminal_gain"], 4))], grid_size=.01)
        if g.geom_type == "MultiPolygon" and len(g.geoms) == 1:
            g = g.geoms[0]
        if g.is_empty or not g.is_valid or g.geom_type != "Polygon":
            raise ValueError(f"Structured role {role} disconnected or invalid")
        g = transform(lambda x, y: warp((x, y), legacy_params), g)
        g = set_precision(g, .01)
        if not g.is_valid or not (0 <= g.bounds[0] < g.bounds[2] <= 1000 and 0 <= g.bounds[1] < g.bounds[3] <= 1000):
            raise ValueError(f"Structured role {role} outside design box or invalid")
        # A solid swept stroke has no authored counters. Grid unions can
        # leave subpixel enclosed slivers: fill only explicitly budgeted ones
        # and record their count. Larger holes fail instead of being erased.
        holes = [Polygon(r).area for r in g.interiors]
        if len(holes) > 64 or any(a > .01 for a in holes) or sum(holes) > .05:
            raise ValueError(f"Structured role {role} unexpectedly encloses a hole")
        slivers[role] = len(holes)
        if holes:
            g = Polygon(g.exterior)
        paths.append({"id": role, "d": geometry_path(g), "terminal": stroke["terminal"]})
        landmarks[role] = [[round(v, 4) for v in warp(tuple(point), legacy_params)] for point in points]
        widths[role] = sample_widths
    return {"paths": paths, "advance": 1000, "stroke_model": "authored"}, {
        "parameters": p, "source_family": base["family"], "landmarks": landmarks,
        "stroke_widths": widths, "assembly_holes_filled": slivers, "review_required": True,
    }
