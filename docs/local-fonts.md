# Local font library (user-managed, never committed)

Glyph does not ship third-party fonts or third-party font license text. The user downloads a font directly from its publisher and places **one static TTF/OTF plus its actual license text** in a local folder. This allows the existing fontTools outline extractor to reuse the font without copying the font file into source control or exported SVG bundles.

## Noto Sans / Serif CJK JP

Official source: https://github.com/notofonts/noto-cjk

Install files from the official **static** Noto Sans CJK JP or Noto Serif CJK JP distribution, not variable TTF, OTC/TTC collections or web WOFF files. Keep the original license text supplied with the download (SIL Open Font License 1.1).

From the repository working directory:

```text
lib/fonts/
  noto-sans-jp/
    <one static Noto Sans JP .ttf or .otf>
    OFL.txt
  noto-serif-jp/
    <one static Noto Serif JP .ttf or .otf>
    OFL.txt
```

The actual font filenames follow the upstream package; the placeholders above are not file names. `LICENSE` or `LICENSE.txt` are also accepted. Each font ID folder must contain **exactly one** .ttf or .otf and **exactly one** license text. To choose another weight, use a separately named folder with one static font. Font IDs use lowercase ASCII letters/digits plus "-" or "_", not filesystem paths. Existing `--font` remains available for arbitrary explicit paths.

```bash
python -m flamoris_glyph.cli generate lyrics.srt \
  --song "My song" --font-id noto-sans-jp \
  --style examples/tango.style.json --seed 42 --out song-glyphs
```

Default library location is `lib/fonts/` **relative to the current working directory**. For a different directory, pass `--font-library /path/to/lib/fonts` (Windows paths work too). This is not an auto-discovery mechanism for system-installed fonts.

## Behavior and responsibility

- `lib/fonts/` is ignored by Git. The fonts and license files are **not** included in this repository, tests, output SVG, or bundle manifest.
- With `--font-id`, Glyph checks for a single static font and accompanying license file; for the two Noto IDs, it also checks that the text has the SIL Open Font License 1.1 header. It records only the local font ID, original filename, license filename, license SHA-256 and Noto upstream reference in manifest source provenance. Local absolute paths and file bytes are not recorded.
- The license check is **presence / recognizable header only**. It does not authenticate the font origin, validate every legal condition, or grant the user rights.
- No automatic downloads, redistribution, silent fallback fonts, or renaming of unsupported collections. Malformed/missing libraries fail explicitly.
- Existing direct `--font /some/font.otf --source-license "Font, license, source URL"` behavior is unchanged.
- Font-derived output rights still depend on the font license. Ordinary images and videos made with OFL fonts typically do not require font attribution; redistributing fonts or reusable derivative font-like SVG libraries can require the font license/copyright information, including with a separate export. Simply storing the license locally does not satisfy every downstream redistribution obligation. Review the official [SIL OFL FAQ](https://openfontlicense.org/ofl-faq/).

The built-in font-free synthetic demo and CI remain independent of downloaded fonts.
