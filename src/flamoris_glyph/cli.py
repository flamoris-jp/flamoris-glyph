"""Simple lyrics/SRT-to-manifest CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .inventory import build_manifest, parse_lyrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a song-scoped glyph manifest.")
    parser.add_argument("lyrics", type=Path, help="UTF-8 .txt or .srt lyric file")
    parser.add_argument("--song", required=True, help="Song identifier/name")
    parser.add_argument("--title", default="", help="Optional title characters to include")
    parser.add_argument("--out", type=Path, required=True, help="Output JSON manifest")
    args = parser.parse_args()
    data = args.lyrics.read_text(encoding="utf-8-sig")
    lyrics = parse_lyrics(data, srt=args.lyrics.suffix.lower() == ".srt")
    manifest = build_manifest(lyrics, song=args.song, title=args.title)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest['glyph_count']} unique glyphs to {args.out}")


if __name__ == "__main__":
    main()
