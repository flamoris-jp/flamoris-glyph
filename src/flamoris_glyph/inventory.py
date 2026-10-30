"""Deterministic Unicode glyph inventory from plain lyrics and SRT."""

from __future__ import annotations

from collections import Counter
import unicodedata


def parse_lyrics(content: str, *, srt: bool = False) -> str:
    """Return lyric text, stripping SRT cue numbers and timestamps if requested."""
    content = content.removeprefix("\ufeff")
    if not srt:
        return content
    from .lyrics import parse_cues
    return "\n".join(cue.text for cue in parse_cues(content, srt=True))


def build_manifest(lyrics: str, *, song: str, title: str = "") -> dict:
    """Create a stable, song-scoped character manifest (no font or SVG generation)."""
    counts = Counter(ch for ch in lyrics if not ch.isspace() and not unicodedata.category(ch).startswith("C"))
    title_chars = set(ch for ch in title if not ch.isspace())
    ordered = list(dict.fromkeys([*counts, *(ch for ch in title if not ch.isspace())]))
    glyphs = []
    for char in ordered:
        glyphs.append({
            "id": f"u{ord(char):06X}",
            "char": char,
            "count": counts[char],
            "in_title": char in title_chars,
            "codepoint": f"U+{ord(char):04X}",
        })
    return {"schema_version": 1, "song": song, "title": title, "glyph_count": len(glyphs), "glyphs": glyphs}

