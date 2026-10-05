"""
Integration tests for ClearSight server's new features:
1. /api/upload-codeframe (Excel DP codeframe parser)
2. /api/export/vertical-codeframe (vertical Excel serializer)
3. /api/stats/kruskal (survey-weighted Kruskal-Wallis)
4. /api/stats/turf (vectorized TURF optimization)
5. /api/stats/key-drivers (Johnson's Relative Weights)
"""
import io
import json
import unittest
import numpy as np
import pandas as pd
import openpyxl

import server


class TestServerFeaturesIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Load sample dataset in session
        server.load_bundled_sample()
        # Add mock binary and numeric columns for TURF and Key Drivers testing if needed
        with server.SESSION_LOCK:
            df = server.SESSION["df"]
            np.random.seed(42)
            n = len(df)
            df["Flavor_Lemon"] = np.random.binomial(1, 0.4, n)
            df["Flavor_Mango"] = np.random.binomial(1, 0.5, n)
            df["Flavor_Peach"] = np.random.binomial(1, 0.3, n)
            df["Driver_Quality"] = np.random.normal(4, 1, n)
            df["Driver_Service"] = np.random.normal(3.5, 1, n)
            df["Driver_Price"] = np.random.normal(3.8, 1, n)
            if "CSAT" not in df.columns:
                df["CSAT"] = 0.5 * df["Driver_Quality"] + 0.3 * df["Driver_Service"] + np.random.normal(0, 0.2, n)

    def test_upload_excel_codeframe(self):
        # Build mock Excel codeframe in memory
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Codes", "Label", "Anchored Verbatims", "DP Instructions"])
        ws.append([None, "GAVE FAVORABLE COMMENTS (NET)", None, None])
        ws.append([None, "Infrastructure (Subnet)", None, None])
        ws.append([31, "Roads have been paved/repaired", "Maayos ang daan", "Lump to code 001"])
        buf = io.BytesIO()
        wb.save(buf)
        excel_bytes = buf.getvalue()

        handler = server.ClearSightRequestHandler.__new__(server.ClearSightRequestHandler)
        handler.headers = {"X-Filename": "test_codeframe.xlsx"}

        # Intercept send_json_response
        captured = []
        handler.send_json_response = lambda data, status=200: captured.append((status, data))

        handler.handle_upload_codeframe(excel_bytes)
        self.assertEqual(len(captured), 1)
        status, data = captured[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["topics_count"], 1)

        with server.SESSION_LOCK:
            self.assertIsNotNone(server.SESSION["custom_codeframe"])

    def test_stats_kruskal_endpoint(self):
        handler = server.ClearSightRequestHandler.__new__(server.ClearSightRequestHandler)
        captured = []
        handler.send_json_response = lambda data, status=200: captured.append((status, data))

        payload = json.dumps({"variable": "CSAT", "group_by": "Region"}).encode("utf-8")
        handler.handle_stats_kruskal(payload)

        self.assertEqual(len(captured), 1)
        status, data = captured[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "success")
        self.assertIn("kruskal_wallis", data)
        self.assertIn("dunn_posthoc", data)
        self.assertGreater(data["kruskal_wallis"]["h_stat"], 0.0)

    def test_stats_turf_endpoint(self):
        handler = server.ClearSightRequestHandler.__new__(server.ClearSightRequestHandler)
        captured = []
        handler.send_json_response = lambda data, status=200: captured.append((status, data))

        payload = json.dumps({
            "items": ["Flavor_Lemon", "Flavor_Mango", "Flavor_Peach"],
            "k": 2,
            "top_n": 3
        }).encode("utf-8")
        handler.handle_stats_turf(payload)

        self.assertEqual(len(captured), 1)
        status, data = captured[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "success")
        self.assertIn("turf", data)
        self.assertEqual(len(data["turf"]["top_portfolios"]), 3)

    def test_stats_key_drivers_endpoint(self):
        handler = server.ClearSightRequestHandler.__new__(server.ClearSightRequestHandler)
        captured = []
        handler.send_json_response = lambda data, status=200: captured.append((status, data))

        payload = json.dumps({
            "target": "CSAT",
            "predictors": ["Driver_Quality", "Driver_Service", "Driver_Price"]
        }).encode("utf-8")
        handler.handle_stats_key_drivers(payload)

        self.assertEqual(len(captured), 1)
        status, data = captured[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "success")
        self.assertIn("key_drivers", data)
        self.assertGreater(data["key_drivers"]["model_r_squared"], 0.0)
        self.assertEqual(len(data["key_drivers"]["drivers"]), 3)


if __name__ == "__main__":
    unittest.main()
