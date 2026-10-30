"""Portable, immutable SVG + JSON bundle compiler and reader validation."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

import fontTools
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.svgLib.path import parse_path

from .inventory import build_manifest
from .lyrics import Cue, cue_dicts, occurrences
from .style import StyleDNA, digest, variation_parameters

SVG_NS = "http://www.w3.org/2000/svg"
MAX_OCCURRENCES = 5000
MAX_ASSET_BYTES = 2_000_000
MAX_BUNDLE_BYTES = 64_000_000


def _sha(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _variant_id(char: str, key: str, seed: int, source: dict, style: StyleDNA, version: str) -> str:
    return "g" + digest({"character": char, "key": key, "seed": seed,
                         "source": source, "style": style.to_dict(), "generator": version})[:24]


def path_bounds(paths: list[dict]) -> list[float]:
    pen = BoundsPen(None)
    for path in paths:
        parse_path(path["d"], pen)
    if pen.bounds is None:
        raise ValueError("Glyph has no geometry")
    bounds = list(pen.bounds)
    if any(not math.isfinite(v) for v in bounds) or not (0 <= bounds[0] < bounds[2] <= 1000 and 0 <= bounds[1] < bounds[3] <= 1000):
        raise ValueError("Glyph geometry exceeds the 0..1000 design box")
    return [round(v, 4) for v in bounds]


def _svg(shape: dict, params: dict) -> str:
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": "0 0 1000 1000"})
    for index, path in enumerate(shape["paths"], 1):
        ET.SubElement(root, "path", {"id": f"stroke{index:03d}", "d": path["d"], "fill": params["fill"]})
    return ET.tostring(root, encoding="unicode") + "\n"


def compile_bundle(cues: list[Cue], source, *, song: str, style: StyleDNA | None = None,
                   title: str = "", seed: int = 0, reuse: str = "occurrence") -> tuple[dict, dict[str, str]]:
    """Compile in memory. source implements render/close/provenance, no transport."""
    if not isinstance(song, str) or not song.strip():
        raise ValueError("song must not be empty")
    if type(seed) is not int or not -(2**63) <= seed < 2**63:
        raise ValueError("seed must be a signed 64-bit integer")
    if reuse not in {"occurrence", "character"}:
        raise ValueError("reuse must be occurrence or character")
    if len({c.id for c in cues}) != len(cues):
        raise ValueError("Cue IDs must be unique")
    if any(not re.fullmatch(r"cue\d{4,}", c.id) for c in cues):
        raise ValueError("Cue IDs must be cue plus at least four digits")
    if any((c.start_ms is None) != (c.end_ms is None) or
           (c.start_ms is not None and (type(c.start_ms) is not int or type(c.end_ms) is not int
                                      or not 0 <= c.start_ms < c.end_ms)) for c in cues):
        raise ValueError("Cue timing must be null or a nonnegative increasing integer interval")
    style = style or StyleDNA()
    # Title is a separate cue namespace, with no timing; not silently deduplicated.
    lyric_cues = cues
    if title:
        from .lyrics import parse_cues
        title_cues = parse_cues(title)
        title = "\n".join(c.text for c in title_cues)
        if title:
            cues = [*cues, Cue(f"cue{max([int(c.id[3:]) for c in cues], default=0) + 1:04d}", title)]
    instances = occurrences(cues)
    if not instances or len(instances) > MAX_OCCURRENCES:
        raise ValueError(f"A bundle requires 1..{MAX_OCCURRENCES} visible occurrences")
    assets: dict[str, str] = {}
    glyphs: dict[str, dict] = {}
    mapping = []
    total_bytes = 0
    for occurrence in instances:
        key = occurrence.occurrence_id if reuse == "occurrence" else occurrence.character
        params = variation_parameters(style, key, seed)
        variant_id = _variant_id(occurrence.character, key, seed, source.provenance, style, "0.2.0")
        if variant_id not in glyphs:
            shape = source.render(occurrence.character, params, style)
            bounds = path_bounds(shape["paths"])
            svg = _svg(shape, params)
            validate_svg(svg)
            total_bytes += len(svg.encode("utf-8"))
            if total_bytes > MAX_BUNDLE_BYTES:
                raise ValueError("Generated assets exceed 64 MB; split the song into smaller bundles")
            asset = f"glyphs/{variant_id}.svg"
            assets[asset] = svg
            glyphs[variant_id] = {
                "variant_id": variant_id, "character": occurrence.character, "asset": asset,
                "sha256": _sha(svg), "parameters": params,
                "metrics": {"view_box": [0, 0, 1000, 1000], "bounds": bounds,
                            "anchor": [500, 500], "advance": shape["advance"]},
                "stroke_model": shape["stroke_model"],
                "strokes": [{"element_id": f"stroke{i:03d}", "source_id": p["id"], "terminal": p["terminal"]}
                            for i, p in enumerate(shape["paths"], 1)],
            }
        mapping.append({**asdict(occurrence), "glyph_variant_id": variant_id})
    lyrics_text = "\n".join(c.text for c in lyric_cues)
    manifest = {
        "schema_version": 2, "kind": "flamoris-glyph-bundle", "song": song, "title": title,
        "generator": {"name": "flamoris-glyph", "version": "0.2.0", "fonttools": fontTools.__version__},
        "seed": seed, "reuse": reuse, "style": style.to_dict(), "source": dict(source.provenance),
        "cues": cue_dicts(cues), "occurrences": mapping, "glyphs": list(glyphs.values()),
        "inventory": build_manifest(lyrics_text, song=song, title=title)["glyphs"],
    }
    return manifest, assets


def validate_svg(svg: str) -> None:
    """Closed path-only subset: no text, links, filters, script, or external resources."""
    if len(svg.encode("utf-8")) > MAX_ASSET_BYTES or "<!" in svg:
        raise ValueError("SVG too large or contains a declaration")
    root = ET.fromstring(svg)
    if root.tag != f"{{{SVG_NS}}}svg" or root.attrib != {"viewBox": "0 0 1000 1000"}:
        raise ValueError("SVG must have the normalized viewBox and no other root attributes")
    if root.text and root.text.strip():
        raise ValueError("SVG may not contain text")
    if not 1 <= len(root) <= 64:
        raise ValueError("SVG must contain 1..64 paths")
    ids, paths = set(), []
    for p in root:
        if p.tag != f"{{{SVG_NS}}}path" or set(p.attrib) != {"id", "d", "fill"} or len(p):
            raise ValueError("SVG supports only plain filled paths")
        if p.text or (p.tail and p.tail.strip()):
            raise ValueError("SVG may not contain text")
        if not re.fullmatch(r"stroke\d{3}", p.attrib["id"]) or p.attrib["id"] in ids:
            raise ValueError("Invalid or duplicate SVG path ID")
        ids.add(p.attrib["id"])
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", p.attrib["fill"]):
            raise ValueError("SVG fill must be #RRGGBB")
        d = p.attrib["d"]
        if not d or not re.fullmatch(r"[MLQCHVZmlqchvz0-9eE+.,\s-]+", d) or not d.rstrip().upper().endswith("Z"):
            raise ValueError("SVG path must use closed numeric geometry")
        # Inspect every contour, not just the last close command.
        pen = SVGPathPen(None)
        parse_path(d, pen)
        commands = pen.getCommands()
        if len(re.findall("M", commands)) != len(re.findall("Z", commands)):
            raise ValueError("Every SVG contour must be closed")
        paths.append({"d": d})
    path_bounds(paths)


def write_bundle(output: Path, manifest: dict, assets: dict[str, str]) -> None:
    """Publish only after a complete validated build; refuse existing destinations."""
    if output.exists() or output.is_symlink():
        raise ValueError(f"Output already exists: {output}; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".glyph-", dir=output.parent))
    try:
        (stage / "glyphs").mkdir()
        for relative, svg in assets.items():
            if not re.fullmatch(r"glyphs/g[0-9a-f]{24}\.svg", relative):
                raise ValueError("Invalid generated asset path")
            (stage / relative).write_bytes(svg.encode("utf-8"))
        (stage / "manifest.json").write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        validate_bundle(stage)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def validate_bundle(directory: Path) -> dict:
    """Validate portable references, identity links, content hashes, and safe SVG."""
    try:
        return _validate_bundle(directory)
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError(f"Malformed bundle structure: {error}") from error


def _validate_bundle(directory: Path) -> dict:
    path = directory / "manifest.json"
    if path.stat().st_size > 20_000_000:
        raise ValueError("Manifest is too large")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 2 or manifest.get("kind") != "flamoris-glyph-bundle":
        raise ValueError("Unsupported bundle format")
    style = StyleDNA.from_dict(manifest["style"])
    if (not isinstance(manifest["song"], str) or not manifest["song"].strip()
            or not isinstance(manifest["title"], str)
            or manifest["generator"]["name"] != "flamoris-glyph"
            or not isinstance(manifest["generator"]["version"], str)
            or not isinstance(manifest["generator"]["fonttools"], str)):
        raise ValueError("Invalid bundle identity or generator metadata")
    if manifest["reuse"] not in {"occurrence", "character"} or type(manifest["seed"]) is not int or not -(2**63) <= manifest["seed"] < 2**63:
        raise ValueError("Invalid bundle reuse policy or seed")
    source = manifest["source"]
    if (source["kind"] not in {"authored-skeleton", "font-outline"}
            or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
            or not isinstance(source["license_note"], str) or not source["license_note"].strip()):
        raise ValueError("Invalid source provenance")
    cues = manifest["cues"]
    if not isinstance(cues, list) or len(cues) > MAX_OCCURRENCES:
        raise ValueError("Invalid cue list")
    expected = occurrences([Cue(**c) for c in cues])
    for c in cues:
        if not re.fullmatch(r"cue\d{4,}", c["id"]):
            raise ValueError("Invalid cue ID")
        start, end = c["start_ms"], c["end_ms"]
        if ((start is None) != (end is None) or
                (start is not None and (type(start) is not int or type(end) is not int or not 0 <= start < end))):
            raise ValueError("Invalid cue interval")
    if len({c["id"] for c in cues}) != len(cues):
        raise ValueError("Duplicate cue IDs")
    if not 1 <= len(expected) <= MAX_OCCURRENCES:
        raise ValueError("Invalid occurrence count")
    glyphs = manifest["glyphs"]
    if not isinstance(glyphs, list) or not 1 <= len(glyphs) <= MAX_OCCURRENCES:
        raise ValueError("Invalid glyph list")
    by_id = {}
    total_bytes = 0
    for g in glyphs:
        variant_id = g["variant_id"]
        if not re.fullmatch(r"g[0-9a-f]{24}", variant_id) or variant_id in by_id:
            raise ValueError("Invalid or duplicate variant ID")
        relative = g["asset"]
        if relative != f"glyphs/{variant_id}.svg" or PurePosixPath(relative).is_absolute():
            raise ValueError("Invalid relative asset path")
        asset = directory / relative
        if asset.resolve().parent != (directory / "glyphs").resolve() or asset.is_symlink() or (directory / "glyphs").is_symlink():
            raise ValueError("Asset may not escape bundle or use symlinks")
        if asset.stat().st_size > MAX_ASSET_BYTES:
            raise ValueError("Asset is too large")
        total_bytes += asset.stat().st_size
        if total_bytes > MAX_BUNDLE_BYTES:
            raise ValueError("Bundle assets exceed 64 MB")
        svg = asset.read_bytes().decode("utf-8")
        if _sha(svg) != g["sha256"]:
            raise ValueError("Asset SHA-256 mismatch")
        validate_svg(svg)
        root = ET.fromstring(svg)
        if any(p.attrib["fill"] not in style.palette for p in root):
            raise ValueError("SVG color is outside Style DNA")
        if [p.attrib["id"] for p in root] != [s["element_id"] for s in g["strokes"]]:
            raise ValueError("Stroke element IDs do not match SVG")
        bounds = path_bounds([p.attrib for p in root])
        metrics = g["metrics"]
        if metrics["view_box"] != [0, 0, 1000, 1000] or metrics["anchor"] != [500, 500] or metrics["bounds"] != bounds:
            raise ValueError("Glyph metrics do not match SVG")
        if not isinstance(metrics["advance"], (int, float)) or isinstance(metrics["advance"], bool) or not math.isfinite(metrics["advance"]) or metrics["advance"] <= 0:
            raise ValueError("Invalid glyph advance")
        if g["stroke_model"] != ("authored" if source["kind"] == "authored-skeleton" else "outline"):
            raise ValueError("Stroke model does not match source")
        for s in g["strokes"]:
            if (g["stroke_model"] == "outline" and s["terminal"] is not None) or (g["stroke_model"] == "authored" and s["terminal"] not in {"tome", "hane", "harai"}):
                raise ValueError("Invalid stroke terminal metadata")
        by_id[variant_id] = g
    actual = manifest["occurrences"]
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValueError("Occurrence mapping is incomplete")
    used = set()
    for occurrence, item in zip(expected, actual):
        g = by_id.get(item.get("glyph_variant_id"))
        if not g or g["character"] != occurrence.character or {k: v for k, v in item.items() if k != "glyph_variant_id"} != asdict(occurrence):
            raise ValueError("Occurrence mapping does not match lyric cues")
        key = occurrence.occurrence_id if manifest["reuse"] == "occurrence" else occurrence.character
        if g["parameters"] != variation_parameters(style, key, manifest["seed"]):
            raise ValueError("Glyph parameters do not match Style DNA/seed")
        if g["variant_id"] != _variant_id(occurrence.character, key, manifest["seed"], source, style, manifest["generator"]["version"]):
            raise ValueError("Variant identity does not match source/style/seed")
        used.add(g["variant_id"])
    if used != set(by_id):
        raise ValueError("Bundle contains unreferenced glyphs")
    return manifest


def preview_bundle(directory: Path, *, columns: int = 3, limit: int = 96) -> str:
    """Self-contained contact sheet in occurrence order, for human art review."""
    if type(columns) is not int or not 1 <= columns <= 12 or type(limit) is not int or not 1 <= limit <= 96:
        raise ValueError("Preview requires 1..12 columns and 1..96 occurrences")
    manifest = validate_bundle(directory)
    items = manifest["occurrences"][:limit]
    by_id = {g["variant_id"]: g for g in manifest["glyphs"]}
    rows = (len(items) + columns - 1) // columns
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": f"0 0 {columns * 240} {rows * 240}"})
    ET.SubElement(root, "rect", {"width": "100%", "height": "100%", "fill": "#F6F0E6"})
    for index, item in enumerate(items):
        g = by_id[item["glyph_variant_id"]]
        group = ET.SubElement(root, "g", {"transform": f"translate({index % columns * 240} {index // columns * 240}) scale(0.24)"})
        asset_root = ET.fromstring((directory / g["asset"]).read_text(encoding="utf-8"))
        for p in asset_root:
            ET.SubElement(group, "path", {k: v for k, v in p.attrib.items() if k != "id"})
    return ET.tostring(root, encoding="unicode") + "\n"
