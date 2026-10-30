"""Offline inventory, SVG bundle generation, and portable bundle validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from fontTools.ttLib import TTLibError

from .bundle import compile_bundle, preview_bundle, validate_bundle, write_bundle
from .geometry import FontSource, SkeletonSource
from .inventory import build_manifest, parse_lyrics
from .lyrics import parse_cues
from .style import StyleDNA


def read_text(path: Path, limit: int = 2_000_000) -> str:
    if path.stat().st_size > limit:
        raise ValueError(f"Input exceeds {limit} bytes: {path.name}")
    return path.read_text(encoding="utf-8-sig")


def _lyric_args(parser):
    parser.add_argument("lyrics", type=Path, help="UTF-8 .txt or .srt lyric file")
    parser.add_argument("--song", required=True, help="Song identifier/name")
    parser.add_argument("--title", default="", help="Optional additional title lettering")
    parser.add_argument("--out", type=Path, required=True, help="Output path (new directory for generate)")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="FLAMORIS Glyph: inventory or generate/validate portable SVG lettering.")
    mode = argv.pop(0) if argv and argv[0] in {"generate", "validate", "preview"} else "inventory"
    if mode in {"validate", "preview"}:
        parser.add_argument("bundle", type=Path)
    else:
        _lyric_args(parser)
    if mode == "generate":
        sources = parser.add_mutually_exclusive_group(required=True)
        sources.add_argument("--font", type=Path, help="Static TTF/OTF source (not included in output)")
        sources.add_argument("--skeletons", type=Path, help="Explicit line/quadratic stroke JSON")
        parser.add_argument("--source-license", help="Required font license/provenance note, copied to manifest")
        parser.add_argument("--style", type=Path, help="Version 1 Style DNA JSON; defaults to tango")
        parser.add_argument("--seed", type=int, default=0)
        parser.add_argument("--reuse", choices=["occurrence", "character"], default="occurrence")
    if mode == "preview":
        parser.add_argument("--out", type=Path, required=True)
        parser.add_argument("--columns", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if mode == "preview":
            svg = preview_bundle(args.bundle, columns=args.columns)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("xb") as output:
                output.write(svg.encode("utf-8"))
            print(f"Wrote preview to {args.out}")
            return
        if mode == "validate":
            manifest = validate_bundle(args.bundle)
            print(f"Validated {len(manifest['occurrences'])} occurrences, {len(manifest['glyphs'])} SVG glyphs")
            return
        data = read_text(args.lyrics)
        srt = args.lyrics.suffix.lower() == ".srt"
        if mode == "inventory":
            manifest = build_manifest(parse_lyrics(data, srt=srt), song=args.song, title=args.title)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            print(f"Wrote {manifest['glyph_count']} unique glyphs to {args.out}")
            return
        style = StyleDNA.from_dict(json.loads(read_text(args.style))) if args.style else StyleDNA()
        if args.font:
            if args.font.stat().st_size > 50_000_000:
                raise ValueError("Font exceeds 50 MB limit")
            source = FontSource(args.font, license_note=args.source_license)
        else:
            source = SkeletonSource(json.loads(read_text(args.skeletons)))
        try:
            manifest, assets = compile_bundle(parse_cues(data, srt=srt), source, song=args.song,
                                               title=args.title, style=style, seed=args.seed, reuse=args.reuse)
            write_bundle(args.out, manifest, assets)
        finally:
            source.close()
        print(f"Wrote {len(manifest['occurrences'])} occurrences, {len(assets)} SVG glyphs to {args.out}")
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError, TTLibError, NotImplementedError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

