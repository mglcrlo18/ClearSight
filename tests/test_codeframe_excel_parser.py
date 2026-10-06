"""
Tests for ClearSight's Dynamic Excel Codeframe Parser (engine/codeframe_excel_parser.py).
Validates:
1. Multi-level hierarchy parsing (NET -> Subnet -> Sub-Subnet -> Leaf Codes).
2. Global Code ID uniqueness (zero collision assertion).
3. Anchored verbatims and DP instructions extraction.
4. Compilation into ClearSight's validated codeframe schema (schema_version: 1).
"""
import io
import unittest
import openpyxl

from engine.codeframe_excel_parser import parse_excel_codeframe, CodeframeNormalizer
from engine.codeframe_loader import CodeframeError


class TestCodeframeExcelParser(unittest.TestCase):

    def _create_test_workbook(self, rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Codeframe"
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, val in enumerate(row, start=1):
                ws.cell(row=r_idx, column=c_idx, value=val)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_valid_hierarchical_codeframe_parsing(self):
        rows = [
            ["Project: Frontier 2022", None, None, None],
            ["Q10. Household Situation", None, None, None],
            ["Codes", "Label", "Anchored Verbatims", "DP Instructions"],
            [None, "GAVE FAVORABLE COMMENTS (NET)", None, None],
            [None, "Infrastructure (Subnet)", None, None],
            [None, "Infrastructure in General (Sub-Subnet)", None, None],
            [31, "Roads have been paved/repaired", "Naaayos ang mga kalsada (sementado)", "Lump to code 001"],
            [32, "Roads have been widened", "Pinalawak ang mga kalsada", "Lump to code 001"],
            [None, "Public Lighting (Sub-Subnet)", None, None],
            [41, "Street lights installed", "May mga solar light na sa madidilim na lugar", None],
            [None, "GAVE UNFAVORABLE COMMENTS (NET)", None, None],
            [None, "Economic Hardship (Subnet)", None, None],
            [101, "High prices of basic goods", "Sobrang mahal ng mga bilihin ngayon", "Multi-code with fuel"],
            [102, "Lack of stable employment", "Walang trabaho ang mga tao dito", None],
        ]
        buf = self._create_test_workbook(rows)
        cf = parse_excel_codeframe(buf, codeframe_name="Frontier Household Codeframe")

        self.assertEqual(cf["name"], "Frontier Household Codeframe")
        self.assertIn("topics", cf)
        self.assertEqual(len(cf["topics"]), 5)

        # Verify topic structure
        t31 = next(t for t in cf["topics"] if 31 in [c["code_id"] for c in t["codes"].values()])
        self.assertEqual(t31["net"], "GAVE FAVORABLE COMMENTS (NET)")
        self.assertIn("Infrastructure (Subnet)", t31["subnet"])
        self.assertIn("Infrastructure in General (Sub-Subnet)", t31["subnet"])
        self.assertIn("pos", t31["codes"])
        self.assertEqual(t31["codes"]["pos"]["label"], "Roads have been paved/repaired")
        self.assertIn("Naaayos ang mga kalsada (sementado)", t31["exemplars"])
        self.assertEqual(t31.get("dp_instruction"), "Lump to code 001")

        # Verify negative topic
        t101 = next(t for t in cf["topics"] if 101 in [c["code_id"] for c in t["codes"].values()])
        self.assertEqual(t101["net"], "GAVE UNFAVORABLE COMMENTS (NET)")
        self.assertIn("neg", t101["codes"])
        self.assertEqual(t101["codes"]["neg"]["label"], "High prices of basic goods")

    def test_duplicate_code_id_collision_raises_error(self):
        rows = [
            ["Codes", "Label", "Anchored Verbatims"],
            [None, "GAVE FAVORABLE COMMENTS (NET)", None],
            [31, "Roads have been paved/repaired", "Magandang daan"],
            [None, "GAVE UNFAVORABLE COMMENTS (NET)", None],
            [31, "Damaged/unpaved roads", "Sirang daan"],  # DUPLICATE CODE 31!
        ]
        buf = self._create_test_workbook(rows)
        with self.assertRaises(CodeframeError) as ctx:
            parse_excel_codeframe(buf)
        self.assertIn("Code ID collision", str(ctx.exception))
        self.assertIn("31", str(ctx.exception))

    def test_variable_depth_subnets(self):
        """Verify that shallow branches (NET -> Leaf) and deep branches (NET -> Sub -> SubSub -> Leaf) work together."""
        rows = [
            ["Codes", "Label", "Anchored Verbatims"],
            [None, "Fragrance (NET)", None],
            [None, "Product-specific scent (Subnet)", None],
            [None, "Scent type (Sub-Subnet)", None],
            [None, "Floral scent (Sub-sub-subnet)", None],
            [35, "Smells like sampaguita", "Mabangong sampaguita"],
            [None, "Packaging (NET)", None],
            [81, "Convenient bottle pouch", "Madaling hawakan"],  # Direct leaf under NET!
        ]
        buf = self._create_test_workbook(rows)
        cf = parse_excel_codeframe(buf)
        self.assertEqual(len(cf["topics"]), 2)

        t35 = next(t for t in cf["topics"] if 35 in [c["code_id"] for c in t["codes"].values()])
        self.assertIn("Floral scent (Sub-sub-subnet)", t35["subnet"])

        t81 = next(t for t in cf["topics"] if 81 in [c["code_id"] for c in t["codes"].values()])
        self.assertEqual(t81["net"], "Packaging (NET)")

    def test_codeframe_normalizer_csv_bom(self):
        """Verify CodeframeNormalizer handles UTF-8 BOM (\\xef\\xbb\\xbf) and alternative header keys."""
        csv_bytes = (
            "\ufeffTheme,Category,Code,Quotes\n"
            "Affordable Price,Economic Relief,101,Mura at sulit talaga\n"
            "Slow Service,Operational Delays,201,Napakabagal ng pila sa cashier\n"
        ).encode("utf-8-sig")

        cf = CodeframeNormalizer.parse_tabular_codeframe(csv_bytes, filename="test_subsidy_codeframe.csv")
        self.assertEqual(cf["schema_version"], 1)
        self.assertEqual(len(cf["topics"]), 2)

        t101 = next(t for t in cf["topics"] if 101 in [c["code_id"] for c in t["codes"].values()])
        self.assertEqual(t101["codes"]["pos"]["label"], "Affordable Price")
        self.assertIn("Economic Relief (Subnet)", t101["subnet"])
        self.assertIn("mura", t101["keywords"])

    def test_codeframe_normalizer_cp1252(self):
        """Verify CodeframeNormalizer decodes Windows-1252 encoded CSV codeframes."""
        csv_text = "label,net_group,code_id,exemplars\nClean Store,Store Environment,111,Malinis ang sahig\n"
        csv_bytes = csv_text.encode("cp1252")

        cf = CodeframeNormalizer.parse_tabular_codeframe(csv_bytes, filename="cp1252_test.csv")
        self.assertEqual(len(cf["topics"]), 1)
        t = cf["topics"][0]
        self.assertEqual(t["codes"]["pos"]["code_id"], 111)
        self.assertEqual(t["codes"]["pos"]["label"], "Clean Store")


if __name__ == "__main__":
    unittest.main()
