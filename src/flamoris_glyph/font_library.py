"""Resolve user-installed fonts without committing or embedding their license files."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

_LOCAL_ID = re.compile(r"[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?\Z")
_LICENSE_NAMES = {"OFL.txt", "LICENSE", "LICENSE.txt"}
_NOTO_IDS = {"noto-sans-jp", "noto-serif-jp"}
_NOTO_URL = "https://github.com/notofonts/noto-cjk"


def resolve_local_font(font_id: str, library: Path) -> tuple[Path, str]:
    """Return one static font path and a path-free provenance note.

    Only the user-maintained directory is read; neither font nor license bytes
    are copied into the output bundle. This is NOT legal license verification.
    """
    if not _LOCAL_ID.fullmatch(font_id):
        raise ValueError("Font ID must be 1..64 lowercase ASCII letters/digits, '-' or '_' (no paths)")
    folder = library / font_id
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError(f"Local font '{font_id}' not found in {library}; see docs/local-fonts.md")
    entries = list(folder.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise ValueError(f"Symlinks are not permitted inside local font '{font_id}'")
    fonts = sorted((p for p in entries if p.is_file() and p.suffix.lower() in {".ttf", ".otf"}),
                   key=lambda p: p.name)
    if len(fonts) != 1:
        raise ValueError(f"Local font '{font_id}' needs exactly one static .ttf/.otf (found {len(fonts)})")
    licenses = sorted((p for p in entries if p.is_file() and p.name in _LICENSE_NAMES),
                      key=lambda p: p.name)
    if len(licenses) != 1:
        raise ValueError(f"Local font '{font_id}' needs exactly one license file (OFL.txt, LICENSE, or LICENSE.txt)")
    font, license_file = fonts[0], licenses[0]
    license_size = license_file.stat().st_size
    if not 0 < license_size <= 250_000:
        raise ValueError(f"Local font '{font_id}' has an empty or oversized license file")
    raw = license_file.read_bytes()
    if font_id in _NOTO_IDS:
        try:
            license_text = raw.decode("utf-8-sig").upper()
        except UnicodeError as error:
            raise ValueError("Noto license file must be UTF-8 text") from error
        if "SIL OPEN FONT LICENSE" not in license_text or "VERSION 1.1" not in license_text:
            raise ValueError("Noto local font requires its official SIL Open Font License 1.1 text")
    license_hash = hashlib.sha256(raw).hexdigest()
    note = (f"Local font ID: {font_id}; font: {font.name}; "
            f"user-provided license file: {license_file.name}; license SHA-256: {license_hash}")
    if font_id in _NOTO_IDS:
        note += f"; expected license: SIL OFL 1.1; upstream: {_NOTO_URL}"
    return font, note
