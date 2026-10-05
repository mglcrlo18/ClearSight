"""
Tests for ClearSight's Vertical Codeframe Exporter (engine/export_engine.py).
Validates:
1. Generation of vertical hierarchical .xlsx workbooks.
2. Native collapsible outline levels (outlineLevel and summaryBelow=False).
3. Pre-flight formula injection defense (CWE-1236).
4. Round-trip compatibility: export -> parse_excel_codeframe.
"""
import os
import tempfile
import unittest
import openpyxl

from engine.export_engine import generate_vertical_codeframe_excel
from engine.codeframe_excel_parser import parse_excel_codeframe


class TestExportVerticalCodeframe(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sample_codeframe = {
            "schema_version": 1,
            "id": "frontier_q10_test",
            "name": "Q10. Household Situation",
            "domain": "governance",
            "topics": [
                {
                    "id": "paved_roads_31",
                    "net": "GAVE FAVORABLE COMMENTS (NET)",
                    "subnet": "Infrastructure (Subnet) > Infrastructure in General (Sub-Subnet)",
                    "codes": {
                        "pos": {"code_id": 31, "label": "Roads have been paved/repaired"}
                    },
                    "keywords": ["paved", "repaired", "kalsada"],
                    "exemplars": ["Naaayos ang mga kalsada (sementado)"],
                    "dp_instruction": "Lump to code 001"
                },
                {
                    "id": "widened_roads_32",
                    "net": "GAVE FAVORABLE COMMENTS (NET)",
                    "subnet": "Infrastructure (Subnet) > Infrastructure in General (Sub-Subnet)",
                    "codes": {
                        "pos": {"code_id": 32, "label": "Roads have been widened"}
                    },
                    "keywords": ["widened", "pinalawak"],
                    "exemplars": ["Pinalawak ang mga kalsada"],
                    "dp_instruction": "Lump to code 001"
                },
                {
                    "id": "high_prices_101",
                    "net": "GAVE UNFAVORABLE COMMENTS (NET)",
                    "subnet": "Economic Hardship (Subnet)",
                    "codes": {
                        "neg": {"code_id": 101, "label": "=1+1 Malicious Formula in Label"}
                    },
                    "keywords": ["prices", "mahal"],
                    "exemplars": ["@evil_macro_command in verbatim"],
                    "dp_instruction": "+2-3 malicious formula"
                }
            ]
        }

    def test_export_creates_valid_excel_with_outlines(self):
        out_path = os.path.join(self.temp_dir, "vertical_codeframe_test.xlsx")
        res = generate_vertical_codeframe_excel(
            out_path,
            self.sample_codeframe,
            project_title="Frontier 2022 Palawan Study",
            question_text="Q10. Sa kabuuan, ano ang sitwasyon sa tahanan?"
        )
        self.assertTrue(os.path.exists(res))

        wb = openpyxl.load_workbook(out_path)
        ws = wb["Vertical Codeframe"]

        # Check outline property
        self.assertFalse(ws.sheet_properties.outlinePr.summaryBelow)

        # Check headers
        self.assertEqual(ws.cell(row=4, column=1).value, "Codes")
        self.assertEqual(ws.cell(row=4, column=2).value, "Theme / Standardized Label")
        self.assertEqual(ws.cell(row=4, column=3).value, "Anchored Verbatims (Raw Quotes)")
        self.assertEqual(ws.cell(row=4, column=4).value, "DP / Coding Instructions")

        # Check that codes are present
        found_31 = False
        found_101 = False
        found_sanitized_label = False
        found_sanitized_verbatim = False

        for r in range(5, ws.max_row + 1):
            val_a = ws.cell(row=r, column=1).value
            val_b = ws.cell(row=r, column=2).value
            val_c = ws.cell(row=r, column=3).value
            val_d = ws.cell(row=r, column=4).value

            if val_a == 31:
                found_31 = True
                self.assertIn("Roads have been paved/repaired", str(val_b))
                self.assertIn("Naaayos ang mga kalsada", str(val_c))
                self.assertEqual(val_d, "Lump to code 001")
                # Sub-sub-subnet leaf outline level should be 3
                self.assertEqual(ws.row_dimensions[r].outlineLevel, 3)

            if val_a == 101:
                found_101 = True
                # CWE-1236 check: must start with apostrophe
                if "'=1+1" in str(val_b):
                    found_sanitized_label = True
                if "'@evil_macro" in str(val_c):
                    found_sanitized_verbatim = True

        self.assertTrue(found_31)
        self.assertTrue(found_101)
        self.assertTrue(found_sanitized_label)
        self.assertTrue(found_sanitized_verbatim)

    def test_round_trip_parse_after_export(self):
        """Export vertical codeframe to Excel, then parse it back with codeframe_excel_parser."""
        out_path = os.path.join(self.temp_dir, "round_trip_test.xlsx")
        generate_vertical_codeframe_excel(
            out_path,
            self.sample_codeframe,
            project_title="Frontier Palawan",
            question_text="Q10. Household Situation"
        )

        parsed_cf = parse_excel_codeframe(out_path, codeframe_name="Round Trip Tested Codeframe")
        self.assertIn("topics", parsed_cf)
        codes_found = []
        for t in parsed_cf["topics"]:
            for pol, c_info in t["codes"].items():
                codes_found.append(c_info["code_id"])

        self.assertIn(31, codes_found)
        self.assertIn(32, codes_found)
        self.assertIn(101, codes_found)


if __name__ == "__main__":
    unittest.main()
