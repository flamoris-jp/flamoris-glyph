import unittest

from flamoris_glyph import parse_cues
from flamoris_glyph.inventory import parse_lyrics
from flamoris_glyph.lyrics import occurrences


class LyricTests(unittest.TestCase):
    def test_srt_preserves_numeric_lyric_and_multiline_positions(self):
        cues = parse_cues("\ufeff3\r\n00:01:01,050 --> 00:01:02.075\r\n123\r\n<b>赤</b> い\r\n", srt=True)
        self.assertEqual((cues[0].start_ms, cues[0].end_ms), (61050, 62075))
        self.assertEqual(cues[0].text, "123\n赤 い")
        items = occurrences(cues)
        self.assertEqual((items[-1].line, items[-1].column), (2, 3))
        self.assertEqual(items[-1].occurrence_id, "cue0001-char0005")
        self.assertEqual(parse_lyrics("1\n00:00:01,000 --> 00:00:02,000\n123", srt=True), "123")

    def test_overlapping_cues_allowed_but_not_retimed(self):
        cues = parse_cues("1\n00:00:01,000 --> 00:00:03,000\n赤\n\n2\n00:00:02,000 --> 00:00:04,000\n靴", srt=True)
        self.assertEqual([c.start_ms for c in cues], [1000, 2000])

    def test_nfc_composes_japanese_dakuten(self):
        self.assertEqual(occurrences(parse_cues("か\u3099"))[0].character, "が")

    def test_blank_lines_and_spaces_keep_source_positions(self):
        items = occurrences(parse_cues("赤\n\n い\t靴"))
        self.assertEqual(items[-1].cue_id, "cue0003")
        self.assertEqual(items[-1].column, 4)

    def test_bad_srt_is_rejected(self):
        for text in ("赤", "1", "1\n00:00:01,000 --> 00:00:02,000",
                     "1\n00:00:01,000 --> 00:00:01,000\n赤",
                     "1\n00:00:61,000 --> 00:00:62,000\n赤"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_cues(text, srt=True)

    def test_sequences_fail_explicitly_instead_of_splitting(self):
        for text in ("x\u0301", "👩\u200d💻", "赤\ufe0f", "👍🏻", "🇯🇵", "赤\x00"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                occurrences(parse_cues(text))
