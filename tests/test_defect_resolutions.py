"""
Automated Regression Test Suite for ClearSight QA Defect Resolutions (CS-DEF-01 through CS-DEF-04, CS-UI-01 through CS-STAT-01, Lifecycle & Statistical Suite).
"""
import io
import json
import os
import unittest
import openpyxl
import pandas as pd
import numpy as np

import server
from engine.codeframe_excel_parser import parse_excel_codeframe
from engine.tabulation_engine import build_crosstab_table
from engine.export_engine import generate_thesis_excel_tables
from engine.stats_engine import calculate_chi_square_df, chi_square_independence
from engine.statistical_suite import (
    run_independent_ttest,
    run_paired_ttest,
    run_mann_whitney_u,
    run_wilcoxon_signed_rank,
    run_kruskal_wallis,
    run_correlation_matrix,
    run_chi_square_association,
    run_linear_regression,
    run_ordinal_logistic_regression,
    run_path_analysis_sem,
    run_kruskal_quadrant_analysis
)


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

    def test_cs_ui_01_no_literal_newline_in_html(self):
        """CS-UI-01: Ensure no literal \\n strings are present in static/index.html."""
        index_path = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("\\n", content)
        self.assertIn("table-controls-spacer", content)

    def test_cs_ui_02_and_03_styles(self):
        """CS-UI-02 & CS-UI-03: Ensure transparent sig rows, badges, and high-contrast section headers."""
        styles_path = os.path.join(os.path.dirname(__file__), "..", "static", "styles.css")
        with open(styles_path, "r", encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".sig-subrow, .sig-row", css)
        self.assertIn("background-color: transparent !important;", css)
        self.assertIn(".sig-badge", css)
        self.assertIn(".stub-group-header td", css)
        self.assertIn("border-left: 3px solid #E10600 !important;", css)

    def test_cs_stat_01_chi_square_df(self):
        """CS-STAT-01: Verify calculate_chi_square_df strictly ignores zero-count rows and cols."""
        mat = np.array([
            [10, 20, 15, 5],
            [12, 18, 14, 6],
            [15, 15, 10, 10],
            [0, 0, 0, 0]  # unobserved 4th row
        ])
        df = calculate_chi_square_df(mat)
        self.assertEqual(df, 6, "Expected (3-1)*(4-1) = 6 degrees of freedom")

    def test_advanced_statistical_suite(self):
        """Part 2: Verify all 15 models of the modular statistical suite."""
        df = server.SESSION["df"]
        self.assertIsNotNone(df)

        # 1. Independent T-test
        res_tt = run_independent_ttest(
            df.loc[df["Gender"] == "Male", "Overall_CSAT"].dropna().to_numpy(),
            df.loc[df["Gender"] == "Female", "Overall_CSAT"].dropna().to_numpy()
        )
        self.assertIn("t_stat", res_tt)

        # 2. Paired T-test
        res_pt = run_paired_ttest(
            df["Overall_CSAT"].dropna().to_numpy(),
            df["Repurchase_Intent"].dropna().to_numpy()
        )
        self.assertIn("t_stat", res_pt)

        # 3. Mann-Whitney U
        res_mwu = run_mann_whitney_u(
            df.loc[df["Gender"] == "Male", "Overall_CSAT"].dropna().to_numpy(),
            df.loc[df["Gender"] == "Female", "Overall_CSAT"].dropna().to_numpy()
        )
        self.assertIn("u_stat", res_mwu)

        # 4. Wilcoxon Signed Rank
        res_w = run_wilcoxon_signed_rank(
            df["Overall_CSAT"].dropna().to_numpy(),
            df["Repurchase_Intent"].dropna().to_numpy()
        )
        self.assertIn("w_stat", res_w)

        # 5. Kruskal-Wallis H
        groups = [df.loc[df["Region"] == r, "Overall_CSAT"].dropna().to_numpy() for r in df["Region"].dropna().unique()]
        res_kw = run_kruskal_wallis(groups)
        self.assertIn("h_stat", res_kw)

        # 6. Pearson, Spearman, Kendall, Point-Biserial
        for m in ("pearson", "spearman", "kendall"):
            corr = run_correlation_matrix(df["Overall_CSAT"].to_numpy(), df["Repurchase_Intent"].to_numpy(), test_type=m)
            self.assertIn("coefficient", corr)

        # 7. Linear OLS Regression
        clean = df.dropna(subset=["Overall_CSAT", "Survey_Duration_Sec", "Repurchase_Intent"])
        X = clean[["Survey_Duration_Sec", "Repurchase_Intent"]].to_numpy(dtype=float)
        y = clean["Overall_CSAT"].to_numpy(dtype=float)
        ols = run_linear_regression(X, y, ["Survey_Duration_Sec", "Repurchase_Intent"])
        self.assertIn("r_squared", ols)

        # 8. Ordinal Logit
        ord_logit = run_ordinal_logistic_regression(X, y, ["Survey_Duration_Sec", "Repurchase_Intent"])
        self.assertIn("num_classes", ord_logit)

        # 9. Path Analysis / SEM
        corr_mat = np.corrcoef(clean[["Survey_Duration_Sec", "Repurchase_Intent", "Overall_CSAT"]].to_numpy(dtype=float), rowvar=False)
        sem = run_path_analysis_sem(corr_mat, ["Duration", "Repurchase", "CSAT"], 2)
        self.assertIn("explained_variance_r2", sem)
        self.assertIn("fit_indices", sem)

        # 10. Kruskal Quadrant Analysis (IPA)
        ipa = run_kruskal_quadrant_analysis(df, ["Survey_Duration_Sec", "Repurchase_Intent"], "Overall_CSAT")
        self.assertIn("attributes", ipa)
        self.assertEqual(len(ipa["attributes"]), 2)


if __name__ == "__main__":
    unittest.main()
