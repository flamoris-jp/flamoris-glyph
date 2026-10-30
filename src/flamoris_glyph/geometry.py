"""Font outline and explicitly authored stroke sources. All output is closed paths."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from .style import StyleDNA, digest, number


def fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def warp(point: tuple[float, float], params: dict) -> tuple[float, float]:
    x, y = point
    # One continuous deformation for the entire character preserves its topology.
    return (500 + (x - 500) * params["scale_x"] + (500 - y) * params["slant"]
            + params["bend"] * math.sin(math.pi * y / 1000),
            500 + (y - 500) * params["scale_y"])


class _OutlinePen(BasePen):
    def __init__(self, glyph_set, out, normalizer, params):
        super().__init__(glyph_set)
        self.out, self.normalizer, self.params = out, normalizer, params

    def point(self, p):
        return warp(self.normalizer(p), self.params)

    def _moveTo(self, p):
        self.out.moveTo(self.point(p))

    def _lineTo(self, p):
        self.out.lineTo(self.point(p))

    def _curveToOne(self, p1, p2, p3):
        self.out.curveTo(self.point(p1), self.point(p2), self.point(p3))

    def _qCurveToOne(self, p1, p2):
        self.out.qCurveTo(self.point(p1), self.point(p2))

    def _closePath(self):
        self.out.closePath()

    def _endPath(self):
        raise ValueError("Open font contours are not supported")


class FontSource:
    """Static TTF/OTF outlines; no installed font lookup, shaping, or font embedding."""

    def __init__(self, path: Path, *, license_note: str):
        if not isinstance(license_note, str) or not license_note.strip():
            raise ValueError("Source license/provenance note is required")
        if path.suffix.lower() not in {".ttf", ".otf"}:
            raise ValueError("Font source must be a standalone .ttf or .otf")
        self.font = TTFont(path, recalcTimestamp=False)
        try:
            if "fvar" in self.font:
                raise ValueError("Use a static font instance; variable fonts are not supported yet")
            if not ("glyf" in self.font or "CFF " in self.font):
                raise ValueError("Font must contain TrueType or CFF outlines")
            self.glyph_set = self.font.getGlyphSet()
            self.cmap = self.font.getBestCmap() or {}
            self.upem = self.font["head"].unitsPerEm
            self.provenance = {"kind": "font-outline", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                               "license_note": license_note}
        except Exception:
            self.font.close()
            raise

    def close(self):
        self.font.close()

    def render(self, char: str, params: dict, style: StyleDNA) -> dict:
        name = self.cmap.get(ord(char))
        if not name or name == ".notdef":
            raise ValueError(f"Source font has no outline for {char!r} (U+{ord(char):04X})")
        glyph = self.glyph_set[name]
        bounds = BoundsPen(self.glyph_set)
        glyph.draw(bounds)
        if not bounds.bounds:
            raise ValueError(f"Empty outline for {char!r}")
        x0, y0, x1, y1 = bounds.bounds
        # Fit each glyph into a generous common design box; this is lettering,
        # not a typography/shaping engine. Advance remains separate metadata.
        scale = min(680 / max(x1 - x0, 1), 680 / max(y1 - y0, 1), 760 / self.upem)
        def normalize(p):
            return (500 + (p[0] - (x0 + x1) / 2) * scale,
                    500 - (p[1] - (y0 + y1) / 2) * scale)
        out = SVGPathPen(None, ntos=fmt)
        glyph.draw(_OutlinePen(self.glyph_set, out, normalize, params))
        return {"paths": [{"id": "outline", "d": out.getCommands(), "terminal": None}],
                "advance": round(glyph.width * 760 / self.upem, 4), "stroke_model": "outline"}


class SkeletonSource:
    """Numeric line/quadratic centerlines with explicit terminal semantics."""

    def __init__(self, data: dict):
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError("Unsupported skeleton schema_version (expected 1)")
        if set(data) != {"schema_version", "license_note", "glyphs"}:
            raise ValueError("Skeleton requires only schema_version, license_note, glyphs")
        if not isinstance(data["license_note"], str) or not data["license_note"].strip():
            raise ValueError("Skeleton license_note is required")
        glyphs = data["glyphs"]
        if not isinstance(glyphs, dict) or not 1 <= len(glyphs) <= 4096:
            raise ValueError("Skeleton glyphs must contain 1..4096 entries")
        self.glyphs = json.loads(json.dumps(glyphs, allow_nan=False))
        for char, strokes in self.glyphs.items():
            if len(char) != 1 or not isinstance(strokes, list) or not 1 <= len(strokes) <= 64:
                raise ValueError("Each skeleton needs one codepoint and 1..64 strokes")
            ids = set()
            for stroke in strokes:
                if not isinstance(stroke, dict) or set(stroke) != {"id", "points", "terminal"}:
                    raise ValueError("Stroke requires id, points, terminal")
                sid = stroke["id"]
                if not isinstance(sid, str) or not sid.isascii() or not sid.replace("-", "").isalnum() or sid in ids:
                    raise ValueError("Stroke IDs must be unique ASCII alphanumeric/hyphen tokens")
                ids.add(sid)
                if stroke["terminal"] not in {"tome", "hane", "harai"}:
                    raise ValueError("Unknown terminal; use tome, hane, harai")
                points = stroke["points"]
                if not isinstance(points, list) or len(points) not in {2, 3}:
                    raise ValueError("Stroke points must define a line (2) or quadratic (3)")
                for p in points:
                    if not isinstance(p, list) or len(p) != 2:
                        raise ValueError("Each point must be [x, y]")
                    for value in p:
                        number(value, "skeleton coordinate", 120, 880)
                if points[0] == points[-1]:
                    raise ValueError("Stroke start and end must differ")
        self.provenance = {"kind": "authored-skeleton", "sha256": digest(data), "license_note": data["license_note"]}

    def close(self):
        pass

    def render(self, char: str, params: dict, style: StyleDNA) -> dict:
        if char not in self.glyphs:
            raise ValueError(f"No authored skeleton for {char!r} (U+{ord(char):04X})")
        paths = []
        for stroke in self.glyphs[char]:
            points = stroke["points"]
            samples = []
            for i in range(33):
                t = i / 32
                if len(points) == 2:
                    p = tuple((1 - t) * points[0][a] + t * points[1][a] for a in (0, 1))
                else:
                    p = tuple((1 - t)**2 * points[0][a] + 2 * (1 - t) * t * points[1][a]
                              + t*t * points[2][a] for a in (0, 1))
                samples.append(p)
            if stroke["terminal"] == "hane":
                x, y = samples[-1]
                samples.extend((x - style.hane_length * i / 12, y - style.hane_length * i / 12) for i in range(1, 13))
            left, right = [], []
            for i, p in enumerate(samples):
                before, after = samples[max(i - 1, 0)], samples[min(i + 1, len(samples) - 1)]
                dx, dy = after[0] - before[0], after[1] - before[1]
                length = math.hypot(dx, dy)
                if length < 1e-8:
                    raise ValueError(f"Degenerate stroke tangent in {char!r}/{stroke['id']}")
                progress = i / (len(samples) - 1)
                taper = 1
                if stroke["terminal"] in {"harai", "hane"}:
                    taper = 1 - (1 - style.harai_taper) * progress**2
                radius = params["stroke_width"] * taper / 2
                left.append(warp((p[0] - dy / length * radius, p[1] + dx / length * radius), params))
                right.append(warp((p[0] + dy / length * radius, p[1] - dx / length * radius), params))
            polygon = left + list(reversed(right))
            d = "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in polygon) + " Z"
            paths.append({"id": stroke["id"], "d": d, "terminal": stroke["terminal"]})
        return {"paths": paths, "advance": 1000, "stroke_model": "authored"}
