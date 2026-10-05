"""
Automated Regression Test Suite for ClearSight QA Defect Resolutions (CS-DEF-01 through CS-DEF-04, Lifecycle).
"""
import io
import os
import unittest
import openpyxl
import pandas as pd
import numpy as np

import server
from engine.codeframe_excel_parser import parse_excel_codeframe
from engine.tabulation_engine import build_crosstab_table
from engine.export_engine import generate_thesis_excel_tables


class TestDefectResolutions(unittest.TestCase):

    def setUp(self):
        server.load_bundled_sample()

    def test_cs_def_01_codeframe_parser_fstring_syntax(self):
        """CS-DEF-01: Ensure parser parses NET and Subnet headers without f-string backslash errors."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Codes", "Label", "Anchored Verbatims", "DP Instructions"])
        ws.append([None, "GAVE FAVORABLE COMMENTS (NET)", None, None])
        ws.append([None, "Public Transportation (Subnet)", None, None])
        ws.append([101, "MRT trains are cleaner and faster", "Mas mabilis na ang tren ngayon", "Keep"])
        
        buf = io.BytesIO()
        wb.save(buf)
        excel_bytes = buf.getvalue()

        cf = parse_excel_codeframe(excel_bytes, codeframe_name="transit_study.xlsx")
        self.assertEqual(cf["name"], "transit_study.xlsx")
        self.assertEqual(len(cf["topics"]), 1)
        self.assertEqual(cf["topics"][0]["net"], "GAVE FAVORABLE COMMENTS (NET)")
        self.assertEqual(cf["topics"][0]["codes"]["pos"]["code_id"], 101)

    def test_cs_def_02_export_academic_tables(self):
        """CS-DEF-02: Ensure generate_thesis_excel_tables dispatches and produces a valid openpyxl workbook."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            generate_thesis_excel_tables(tmp_path, "Consumer Perception Analysis")
            self.assertTrue(os.path.exists(tmp_path))
            self.assertGreater(os.path.getsize(tmp_path), 1000)
            wb = openpyxl.load_workbook(tmp_path)
            self.assertIn("Table 4.1 - Demographics", wb.sheetnames)
            self.assertIn("Table 4.2 - CrossTab", wb.sheetnames)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_cs_def_03_analysis_config_dynamic_execution_desync(self):
        """CS-DEF-03: Ensure execute_tabulation dynamically honors ANALYSIS_CONFIG session toggles."""
        handler = server.ClearSightRequestHandler.__new__(server.ClearSightRequestHandler)
        df = server.SESSION["df"]
        self.assertIsNotNone(df)

        # Baseline: default configuration has RS2, Chi2, Welch ANOVA, and RIM weighting active
        with server.SESSION_LOCK:
            server.SESSION["analysis_config"] = {
                "stats": {
                    "rao_scott_2": True,
                    "chi_square": True,
                    "welch_anova": True,
                    "fdr_benjamini_hochberg": True,
                    "fdr_benjamini_yekutieli": False
                },
                "hygiene": {
                    "rim_weighting": True,
                    "quarantine_straightliners": True,
                    "quarantine_speeders": True
                },
                "nlp": {
                    "pii_masking": True,
                    "contrastive_clause_weighting": True,
                    "review_queue_routing": True
                }
            }

        # 1. Chi-square on categorical variable (Age_Generation)
        tab_chi2_on = handler.execute_tabulation(df, ["Total", "Region"], ["Age_Generation"])[0]
        self.assertIsNotNone(tab_chi2_on.get("chi_square"))

        with server.SESSION_LOCK:
            server.SESSION["analysis_config"]["stats"]["chi_square"] = False

        tab_chi2_off = handler.execute_tabulation(df, ["Total", "Region"], ["Age_Generation"])[0]
        self.assertIsNone(tab_chi2_off.get("chi_square"), "Chi-square should be None when disabled")

        # 2. Rao-Scott RS2 on multi-select checkbox variable (Brand_Preference)
        tab_rs2_on = handler.execute_tabulation(df, ["Total", "Region"], ["Brand_Preference"])[0]
        self.assertIsNotNone(tab_rs2_on.get("mrcv"))

        with server.SESSION_LOCK:
            server.SESSION["analysis_config"]["stats"]["rao_scott_2"] = False

        tab_rs2_off = handler.execute_tabulation(df, ["Total", "Region"], ["Brand_Preference"])[0]
        self.assertIsNone(tab_rs2_off.get("mrcv"), "Rao-Scott RS2 should be None when disabled")

        # 3. Welch ANOVA on rating scale mean variable (Overall_CSAT)
        tab_anova_on = handler.execute_tabulation(df, ["Total", "Region"], ["Overall_CSAT"], metric="mean")[0]
        self.assertIsNotNone(tab_anova_on.get("anova"))

        with server.SESSION_LOCK:
            server.SESSION["analysis_config"]["stats"]["welch_anova"] = False

        tab_anova_off = handler.execute_tabulation(df, ["Total", "Region"], ["Overall_CSAT"], metric="mean")[0]
        self.assertIsNone(tab_anova_off.get("anova"), "Welch ANOVA should be None when disabled")

        # 4. RIM Weighting toggle
        with server.SESSION_LOCK:
            server.SESSION["analysis_config"]["hygiene"]["rim_weighting"] = False

        tab_no_rim = handler.execute_tabulation(df, ["Total", "Region"], ["Brand_Preference"])[0]
        self.assertEqual(tab_no_rim["unweighted_bases"][0], tab_no_rim["weighted_bases"][0])

    def test_cs_def_04_toast_svg_icons(self):
        """CS-DEF-04: Ensure app.js contains SVG stroke icons for showToast."""
        app_js_path = os.path.join(os.path.dirname(__file__), "..", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("svg width=\"16\" height=\"16\"", content)
        self.assertIn("stroke=\"currentColor\"", content)
        self.assertIn("toast-notification", content)


if __name__ == "__main__":
    unittest.main()
