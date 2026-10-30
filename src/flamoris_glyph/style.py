"""Small, enforced Style DNA contract, independent of any AI or renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def number(value: object, name: str, low: float, high: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{name} must be a finite number in [{low}, {high}]")
    return float(value)


@dataclass(frozen=True)
class StyleDNA:
    name: str = "tango"
    palette: tuple[str, ...] = ("#C72F42", "#222222")
    variation: float = 0.45
    stroke_width: float = 42
    width: float = 1
    height: float = 1
    slant: float = 0
    hane_length: float = 65
    harai_taper: float = 0.08

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 100:
            raise ValueError("Style name must contain 1..100 characters")
        if (not isinstance(self.palette, tuple) or not 1 <= len(self.palette) <= 8
                or any(not isinstance(c, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in self.palette)):
            raise ValueError("palette must contain 1..8 #RRGGBB colors")
        for name, low, high in (("variation", 0, 1), ("stroke_width", 8, 80),
                                ("width", 0.85, 1.05), ("height", 0.85, 1.05),
                                ("slant", -0.1, 0.1), ("hane_length", 0, 80),
                                ("harai_taper", 0.02, 0.5)):
            number(getattr(self, name), name, low, high)

    @classmethod
    def from_dict(cls, data: dict) -> StyleDNA:
        if not isinstance(data, dict):
            raise ValueError("Style DNA must be an object")
        data = dict(data)
        version = data.pop("schema_version", None)
        if type(version) is not int or version != 1:
            raise ValueError("Unsupported Style DNA schema_version (expected 1)")
        return cls._from_versioned(data)

    @classmethod
    def _from_versioned(cls, data: dict) -> StyleDNA:
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Unknown Style DNA fields: {', '.join(sorted(unknown))}")
        if "palette" in data:
            if not isinstance(data["palette"], list):
                raise ValueError("palette must be an array")
            data["palette"] = tuple(data["palette"])
        return cls(**data)

    def to_dict(self) -> dict:
        return {"schema_version": 1, **asdict(self), "palette": list(self.palette)}


def variation_parameters(style: StyleDNA, key: str, seed: int) -> dict:
    # Hash-derived samples avoid Python hash randomization and RNG algorithm drift.
    raw = hashlib.sha256(canonical_json([seed, key]).encode("utf-8")).digest()
    unit = [int.from_bytes(raw[i:i + 4], "big") / (2**32 - 1) * 2 - 1 for i in range(0, 24, 4)]
    amount = style.variation
    return {
        "scale_x": round(style.width * (1 + unit[0] * 0.075 * amount), 6),
        "scale_y": round(style.height * (1 + unit[1] * 0.055 * amount), 6),
        "slant": round(style.slant + unit[2] * 0.055 * amount, 6),
        "bend": round(unit[3] * 18 * amount, 6),
        "stroke_width": round(style.stroke_width * (1 + unit[4] * 0.12 * amount), 6),
        "fill": style.palette[int.from_bytes(raw[24:28], "big") % len(style.palette)] if amount else style.palette[0],
    }
