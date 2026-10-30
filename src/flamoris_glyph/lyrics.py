"""Cue-level timing and stable occurrence identities; never invent word timings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata

_TIME = re.compile(
    r"^(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})\s*-->\s*"
    r"(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})(?:\s+.*)?$"
)
_TAG = re.compile(r"</?(?:b|i|u|font)(?:\s+[^<>]*)?>", re.IGNORECASE)


@dataclass(frozen=True)
class Cue:
    id: str
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class Occurrence:
    occurrence_id: str
    character: str
    cue_id: str
    line: int
    column: int


def parse_cues(content: str, *, srt: bool = False) -> list[Cue]:
    content = unicodedata.normalize("NFC", content.removeprefix("\ufeff"))
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if not srt:
        return [Cue(f"cue{i:04d}", line) for i, line in enumerate(content.splitlines(), 1) if line.strip()]
    cues = []
    for block in re.split(r"\n[ \t]*\n", content.strip()):
        lines = block.splitlines()
        if not lines:
            continue
        # A numeric lyric line is text; only the header may be a sequence number.
        offset = 1 if lines[0].strip().isdigit() else 0
        match = _TIME.fullmatch(lines[offset].strip()) if len(lines) > offset else None
        if not match or len(lines) <= offset + 1:
            raise ValueError(f"Invalid SRT block {len(cues) + 1}: expected timestamp and lyric text")
        values = [int(v) for v in match.groups()]
        def ms(v: list[int]) -> int:
            return ((v[0] * 60 + v[1]) * 60 + v[2]) * 1000 + v[3]
        start, end = ms(values[:4]), ms(values[4:])
        if end <= start:
            raise ValueError("SRT cue end must be after start")
        text = _TAG.sub("", "\n".join(lines[offset + 1:]))
        if not text.strip():
            raise ValueError("SRT cue must contain lyric text")
        cues.append(Cue(f"cue{len(cues) + 1:04d}", text, start, end))
    return cues


def occurrences(cues: list[Cue]) -> list[Occurrence]:
    result = []
    for cue in cues:
        index = 0
        for line_no, line in enumerate(cue.text.splitlines(), 1):
            for column, char in enumerate(line, 1):
                if char.isspace():
                    continue
                # MVP uses single NFC codepoints, not shaping or grapheme clusters.
                category = unicodedata.category(char)
                if (category[0] in "MC" or 0x1F3FB <= ord(char) <= 0x1F3FF
                        or 0x1F1E6 <= ord(char) <= 0x1F1FF):
                    raise ValueError(f"Unsupported combining/sequence character U+{ord(char):04X} in {cue.id}")
                index += 1
                result.append(Occurrence(f"{cue.id}-char{index:04d}", char, cue.id, line_no, column))
    return result


def cue_dicts(cues: list[Cue]) -> list[dict]:
    return [asdict(c) for c in cues]
