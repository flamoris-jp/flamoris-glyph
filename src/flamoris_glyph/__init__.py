"""FLAMORIS Glyph: occurrence-driven expressive vector lettering."""

from .bundle import compile_bundle, preview_bundle, validate_bundle, write_bundle
from .geometry import FontSource, SkeletonSource
from .inventory import build_manifest, parse_lyrics
from .lyrics import Cue, parse_cues
from .style import StyleDNA

__all__ = ["build_manifest", "parse_lyrics", "compile_bundle", "validate_bundle",
           "write_bundle", "preview_bundle", "FontSource", "SkeletonSource", "Cue", "parse_cues", "StyleDNA"]

