import unittest

from flamoris_glyph.inventory import build_manifest, parse_lyrics


class InventoryTests(unittest.TestCase):
    def test_unique_characters_and_frequencies(self):
        result = build_manifest("赤い赤\n靴", song="test", title="赤靴")
        self.assertEqual([g["char"] for g in result["glyphs"]], ["赤", "い", "靴"])
        self.assertEqual([g["count"] for g in result["glyphs"]], [2, 1, 1])

    def test_srt_strips_indices_and_timestamps(self):
        srt = "1\n00:00:01,000 --> 00:00:02,000\n赤い靴\n\n2\n00:00:03,000 --> 00:00:04,000\n夜"
        self.assertEqual(parse_lyrics(srt, srt=True), "赤い靴\n夜")

    def test_title_only_character(self):
        result = build_manifest("赤", song="test", title="赤靴")
        self.assertEqual(result["glyphs"][1]["char"], "靴")
        self.assertEqual(result["glyphs"][1]["count"], 0)


if __name__ == "__main__":
    unittest.main()
