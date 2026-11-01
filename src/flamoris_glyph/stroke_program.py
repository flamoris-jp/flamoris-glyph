"""Bounded, hand-authored brush actions for single-stroke research.

Actions change position, pressure and nib angle. Time alone does not change
the deposited ink in this geometric model. No AI or traditional fidelity claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from .bundle import _svg, validate_svg
from .calligraphy import canonicalize_sweep
from .pattern import engine_metadata
from .structure import _cubic, _UNIT_CIRCLE
from .style import digest, number

KIND = "stroke-program-1"
ACTIONS = {"enter", "travel", "settle", "collect", "release", "flick", "lift"}


@dataclass(frozen=True)
class StrokePhase:
    action: str
    points: tuple
    pressure: tuple
    angle: tuple
    duration: float

    def __post_init__(self):
        if not isinstance(self.action, str) or self.action not in ACTIONS:
            raise ValueError("Unknown stroke action")
        if not isinstance(self.points, (list, tuple)) or len(self.points) != 4:
            raise ValueError("Phase needs four cubic points, including stationary phases")
        points = []
        for pair in self.points:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("Expected [x,y] point")
            for v in pair: number(v, "phase coordinate", 0, 1000)
            points.append(tuple(pair))
        object.__setattr__(self, "points", tuple(points))
        for field, lo, hi in (("pressure", 0, 1.5), ("angle", -180, 180)):
            values = getattr(self, field)
            if not isinstance(values, (tuple, list)) or len(values) != 2:
                raise ValueError("Pressure and nib angle need start/end values")
            for v in values: number(v, field, lo, hi)
            object.__setattr__(self, field, tuple(values))
        number(self.duration, "phase duration", .05, 5)
        if self.action == "settle" and len(set(self.points)) != 1:
            raise ValueError("Settle phase must keep the contact center stationary")
        if self.action == "lift" and self.pressure[-1] != 0:
            raise ValueError("Lift phase must end off the paper")


@dataclass(frozen=True)
class StrokeProgram:
    phases: tuple

    def __post_init__(self):
        if not isinstance(self.phases, (tuple, list)) or not 1 <= len(self.phases) <= 8 or any(type(p) is not StrokePhase for p in self.phases):
            raise ValueError("One stroke program requires 1..8 explicit phases")
        object.__setattr__(self, "phases", tuple(self.phases))
        if self.phases[0].action != "enter" or self.phases[0].pressure[0] != 0 or self.phases[-1].pressure[-1] != 0:
            raise ValueError("Program must enter from zero pressure and finish lifted")
        ended, contacted = False, False
        for i, p in enumerate(self.phases):
            if i:
                prev = self.phases[i-1]
                if prev.points[-1] != p.points[0] or prev.pressure[-1] != p.pressure[0] or prev.angle[-1] != p.angle[0]:
                    raise ValueError("Phase position, pressure and angle must be continuous")
            if max(p.pressure) > 0:
                if ended: raise ValueError("A single stroke cannot start a second contact run")
                contacted = True
            if contacted and p.pressure[-1] == 0: ended = True
        if not contacted: raise ValueError("Program has no ink contact")

    def to_dict(self):
        return {"schema_version": 1, "kind": KIND, "phases": [asdict(p) for p in self.phases]}

    @classmethod
    def from_dict(cls, data):
        if (not isinstance(data, dict) or set(data) != {"schema_version", "kind", "phases"}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["kind"] != KIND
                or not isinstance(data["phases"], list) or not 1 <= len(data["phases"]) <= 8):
            raise ValueError("Expected exact stroke-program-1 schema")
        for p in data["phases"]:
            if not isinstance(p, dict) or set(p) != set(StrokePhase.__dataclass_fields__):
                raise ValueError("Expected complete stroke phase")
        return cls(tuple(StrokePhase(**p) for p in data["phases"]))


def sample_program(program):
    if type(program) is not StrokeProgram: raise ValueError("Expected StrokeProgram")
    states, clock = [], 0.
    for index, phase in enumerate(program.phases):
        for i in range(33):
            u = i/32
            smooth = u*u*(3-2*u)
            x, y = _cubic(phase.points, u)
            p = phase.pressure[0]*(1-smooth)+phase.pressure[1]*smooth
            a = phase.angle[0]*(1-smooth)+phase.angle[1]*smooth
            states.append({"time": round(clock+u*phase.duration, 6), "x": x, "y": y,
                           "pressure": p, "angle": a, "phase": index, "action": phase.action})
        clock += phase.duration
    return states


def paint_program(program, width=70, aspect=.5):
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    number(width, "nominal width", 8, 120); number(aspect, "nib aspect", .1, 1)
    engine = engine_metadata()
    states = sample_program(program)
    stamps, pieces = [], []
    for state in states:
        x, y, radius = state["x"], state["y"], width*state["pressure"]/2
        a = math.radians(state["angle"]); c, s = math.cos(a), math.sin(a)
        stamps.append(Point(x, y) if radius == 0 else Polygon([
            (x+radius*(c*u-s*v*aspect), y+radius*(s*u+c*v*aspect)) for u, v in _UNIT_CIRCLE]))
    for i, (a, b) in enumerate(zip(stamps, stamps[1:])):
        if states[i]["pressure"] > 0 or states[i+1]["pressure"] > 0:
            pieces.append(a.union(b).convex_hull)
    shape = unary_union(pieces)
    if shape.geom_type != "Polygon" or not shape.is_valid or shape.is_empty or len(shape.interiors):
        raise ValueError("Stroke program did not make one simple filled stroke")
    d, exported = canonicalize_sweep(shape)
    svg = _svg({"paths": [{"d": d}]}, {"fill": "#171512"})
    validate_svg(svg)
    return svg, {"engine": KIND, "geometry_engine": engine, "program_sha256": digest(program.to_dict()),
                 "width": width, "aspect": aspect, "duration": states[-1]["time"], "states": states,
                 "ink_area": round(exported.area, 4), "bounds": list(exported.bounds),
                 "samples_per_phase": 33, "ellipse_vertices": 32, "max_export_boundary_error": .0173,
                 "human_review": "pending", "physical_brush_simulation": False,
                 "duration_alone_changes_static_ink": False}
