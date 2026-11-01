from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from flamoris_glyph import StyleDNA, compile_bundle, parse_cues, validate_bundle, write_bundle
from flamoris_glyph.pattern import PatternDNA, path_geometry
from flamoris_glyph.structure import AuthoredStructureSource, StructureDNA, PROFILES, ROLES
from flamoris_glyph.structure_lab import run_study

ROOT = Path(__file__).resolve().parents[1]
STYLE = StyleDNA(name="structure-study-neutral", palette=("#171512",), variation=0)


class StructureTests(unittest.TestCase):
    def data(self):
        return json.loads((ROOT/"examples/aka-structure.json").read_text(encoding="utf-8"))

    def generate(self, base="gothic", profile="baseline", seed=42, text="赤赤", dna=None, reuse="occurrence"):
        return compile_bundle(parse_cues(text), AuthoredStructureSource(self.data(), base), song="test",
                              style=STYLE, structure=dna or StructureDNA.preset(profile), seed=seed, reuse=reuse)

    def test_explicit_anatomy_and_strict_versioned_dna(self):
        for profile in PROFILES:
            p=StructureDNA.preset(profile)
            self.assertEqual(p,StructureDNA.from_dict(p.to_dict()))
        d=StructureDNA.preset(PROFILES[1]).to_dict()
        for key,value in (("schema_version",True),("profile","unimplemented"),("width",True),
                          ("junction_shift",float("nan")),("terminal_style","magic"),("unknown",42)):
            bad={**d,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):StructureDNA.from_dict(bad)
        for kind in ("missing-role","duplicate-role","bad-coordinate","wrong-character","unknown-base"):
            bad=self.data()
            if kind=="missing-role":bad["bases"]["gothic"]["strokes"].pop()
            if kind=="duplicate-role":bad["bases"]["gothic"]["strokes"][-1]["id"]="top-bar"
            if kind=="bad-coordinate":bad["bases"]["gothic"]["strokes"][0]["points"][0][0]=-1
            if kind=="wrong-character":bad["character"]="靴"
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                AuthoredStructureSource(bad,"unknown" if kind=="unknown-base" else "gothic")

    def test_profiles_reposition_independent_roles_not_only_global_scale(self):
        for base in ("gothic","mincho"):
            neutral=self.generate(base)[0]["glyphs"][0]["structure_qa"]
            for profile in PROFILES[1:]:
                with self.subTest(base=base,profile=profile):
                    m,a=self.generate(base,profile)
                    qa=m["glyphs"][0]["structure_qa"]
                    # Three bars cannot be reproduced by one global vertical
                    # affine map: the main junction and top endpoint move by
                    # deliberately different semantic-role rules.
                    a0=neutral["landmarks"]["top-stem"][0][1]
                    b0=neutral["landmarks"]["top-bar"][0][1]
                    c0=neutral["landmarks"]["main-bar"][0][1]
                    a1=qa["landmarks"]["top-stem"][0][1]
                    b1=qa["landmarks"]["top-bar"][0][1]
                    c1=qa["landmarks"]["main-bar"][0][1]
                    self.assertGreater(abs((b1-a1)/(b0-a0)-(c1-a1)/(c0-a0)),.001)
                    self.assertNotEqual(qa["landmarks"]["inner-left"][-1],neutral["landmarks"]["inner-left"][-1])
                    self.assertNotEqual(qa["landmarks"]["inner-left"][1],neutral["landmarks"]["inner-left"][1])
                    for g in m["glyphs"]:
                        self.assertEqual([s["source_id"] for s in g["strokes"]],list(ROLES))
                        paths=list(ET.fromstring(a[g["asset"]]))
                        self.assertEqual(len(paths),7)
                        for path in paths:
                            geom=path_geometry(path.attrib["d"])
                            self.assertTrue(geom.is_valid)
                            self.assertEqual(geom.geom_type,"Polygon")
                            self.assertEqual(len(geom.interiors),0)

    def test_same_dna_retains_base_family_differences(self):
        for profile in PROFILES:
            gothic=self.generate("gothic",profile)[0]
            mincho=self.generate("mincho",profile)[0]
            self.assertEqual(gothic["structure"],mincho["structure"])
            g,g2=gothic["glyphs"][0],mincho["glyphs"][0]
            self.assertEqual(g["structure_qa"]["parameters"],g2["structure_qa"]["parameters"])
            self.assertNotEqual(g["sha256"],g2["sha256"])
            q,q2=g["structure_qa"],g2["structure_qa"]
            ratio=lambda qa:qa["stroke_widths"]["top-bar"][0]/qa["stroke_widths"]["top-stem"][0]
            self.assertGreater(ratio(q),ratio(q2))
            self.assertNotEqual(gothic["source"]["sha256"],mincho["source"]["sha256"])
        # Changing DNA never changes original source provenance.
        self.assertEqual(self.generate(profile="baseline")[0]["source"],
                         self.generate(profile=PROFILES[1])[0]["source"])

    def test_fixed_seed_different_seed_zero_variation_and_reuse(self):
        for base in ("gothic","mincho"):
            for profile in PROFILES[1:]:
                with self.subTest(base=base,profile=profile):
                    first=self.generate(base,profile)
                    self.assertEqual(first,self.generate(base,profile))
                    self.assertNotEqual(list(first[1].values()),list(self.generate(base,profile,43)[1].values()))
                    self.assertNotEqual(*first[1].values())
                    dna=replace(StructureDNA.preset(profile),variation=0)
                    self.assertEqual(*self.generate(base,dna=dna)[1].values())
                    self.assertEqual(list(self.generate(base,seed=42,dna=dna)[1].values()),
                                     list(self.generate(base,seed=43,dna=dna)[1].values()))
                    self.assertEqual(len(self.generate(base,profile,reuse="character")[1]),1)

    def test_roundtrip_and_reader_without_optional_geometry(self):
        for base in ("gothic","mincho"):
            m,a=self.generate(base,PROFILES[2])
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/"bundle";write_bundle(out,m,a)
                original_import=__import__
                def no_geometry(name,*args,**kwargs):
                    if name.startswith("shapely"):raise ImportError("optional engine unavailable")
                    return original_import(name,*args,**kwargs)
                with patch("builtins.__import__",side_effect=no_geometry):
                    self.assertEqual(validate_bundle(out),m)

    def test_metadata_tampering_rejected(self):
        for key in ("profile","version","engine","role","landmark","width","parameters"):
            m,a=self.generate(profile=PROFILES[1])
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/"bundle";write_bundle(out,m,a)
                if key=="profile":m["structure"]["profile"]="unsupported"
                if key=="version":m["generator"]["version"]="0.2.0"
                if key=="engine":del m["structure_engine"]
                if key=="role":m["glyphs"][0]["strokes"][0]["source_id"]="guessed"
                if key=="landmark":m["glyphs"][0]["structure_qa"]["landmarks"]["top-bar"][0][0]=-10
                if key=="width":m["glyphs"][0]["structure_qa"]["stroke_widths"]["top-bar"][0]=True
                if key=="parameters":m["glyphs"][0]["structure_qa"]["parameters"]["width"]=1
                (out/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
                with self.assertRaises(ValueError):validate_bundle(out)

    def test_no_implicit_font_inference_or_missing_character_substitution(self):
        source=AuthoredStructureSource(self.data(),"gothic")
        with self.assertRaisesRegex(ValueError,"explicit structure"):
            compile_bundle(parse_cues("赤"),source,song="test")
        with self.assertRaisesRegex(ValueError,"supports only"):
            self.generate(text="靴")
        with self.assertRaisesRegex(ValueError,"not both"):
            compile_bundle(parse_cues("赤"),source,song="test",structure=StructureDNA(),
                           pattern=PatternDNA.preset(PROFILES[1]))

    def test_all_cells_portable_golden_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=run_study(self.data(),root/"study")
            self.assertEqual(len(report["cells"]),16)
            self.assertTrue(report["fixed_seed_reproduction"])
            hashes={f"{r['base']}/{r['profile']}/{r['seed']}":r["sha256"] for r in report["cells"]}
            self.assertEqual(hashes,json.loads((ROOT/"tests/golden/structure-assets.json").read_text()))
            bad=self.data();del bad["bases"]["mincho"]
            with self.assertRaises(ValueError):run_study(bad,root/"bad")
            self.assertEqual([p.name for p in root.iterdir()],["study"])


if __name__=="__main__":unittest.main()
