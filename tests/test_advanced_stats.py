"""
Unit Tests for ClearSight's Advanced Quantitative Statistical Engines:
1. Survey-Weighted Kruskal-Wallis & Dunn's Post-Hoc (engine/non_parametric.py)
2. Vectorized TURF Combinatorial Optimization (engine/turf_engine.py)
3. Johnson's Relative Weights Key Driver Analysis (engine/driver_analysis.py)
"""
import unittest
import numpy as np

from engine.non_parametric import (
    survey_weighted_midranks,
    survey_weighted_kruskal_wallis,
    survey_weighted_dunn_posthoc
)
from engine.turf_engine import calculate_turf
from engine.driver_analysis import johnsons_relative_weights


class TestAdvancedStatsEngines(unittest.TestCase):

    def test_survey_weighted_midranks_unweighted_matches_scipy(self):
        """When weights are all 1.0, mid-ranks must match standard rankdata."""
        from scipy.stats import rankdata
        y = np.array([10.0, 20.0, 20.0, 30.0, 40.0])
        ranks, n_hat = survey_weighted_midranks(y, weights=None)
        expected = rankdata(y)
        np.testing.assert_allclose(ranks, expected)
        self.assertEqual(n_hat, 5.0)

    def test_survey_weighted_kruskal_wallis(self):
        """Test Kruskal-Wallis with unequal groups and survey weights."""
        y = [1, 2, 2, 3, 4, 5, 8, 9, 9, 10, 10, 10]
        groups = ["A", "A", "A", "A", "B", "B", "B", "B", "C", "C", "C", "C"]
        weights = [1.0, 1.2, 0.8, 1.0, 2.0, 1.5, 2.5, 2.0, 0.5, 0.6, 0.4, 0.5]

        res = survey_weighted_kruskal_wallis(y, groups, weights)
        self.assertEqual(res["df"], 2)
        self.assertGreater(res["h_stat"], 0.0)
        self.assertTrue(0.0 <= res["p_value"] <= 1.0)
        self.assertTrue(res["significant"])
        self.assertIn("A", res["groups"])
        self.assertIn("B", res["groups"])
        self.assertIn("C", res["groups"])

        # Test Dunn pairwise post-hoc
        dunn = survey_weighted_dunn_posthoc(y, groups, weights)
        self.assertEqual(len(dunn), 3)  # A vs B, A vs C, B vs C
        for pair in dunn:
            self.assertTrue(0.0 <= pair["p_adj"] <= 1.0)

    def test_turf_exhaustive_simd(self):
        """Test TURF combinatorial optimization under 1.5M threshold."""
        # 10 respondents, 4 beverage flavors
        # Respondent 1-5 like Lemon; 4-8 like Mango; 8-10 like Peach; 1 like Berry
        matrix = [
            [1, 0, 0, 1],
            [1, 0, 0, 0],
            [1, 0, 0, 0],
            [1, 1, 0, 0],
            [1, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 1, 1, 0],
            [0, 0, 1, 0],
            [0, 0, 1, 0],
        ]
        labels = ["Lemon", "Mango", "Peach", "Berry"]
        res = calculate_turf(matrix, labels, k=2, top_n=3)

        self.assertEqual(res["mode"], "exhaustive_simd")
        self.assertEqual(res["k_subset_size"], 2)
        self.assertEqual(len(res["top_portfolios"]), 3)

        # Lemon + Mango reaches respondents 1-8 (80%)
        # Lemon + Peach reaches respondents 1-5 and 8-10 (80%)
        # Mango + Peach reaches respondents 4-10 (70%)
        top_portfolio = res["top_portfolios"][0]
        self.assertGreaterEqual(top_portfolio["reach_pct"], 80.0)

    def test_johnsons_relative_weights_decomposition(self):
        """Test Johnson's Relative Weights variance decomposition."""
        np.random.seed(42)
        n = 200
        # Correlated brand rating attributes
        base_quality = np.random.normal(0, 1, n)
        x1 = base_quality + np.random.normal(0, 0.5, n)  # Product Quality
        x2 = base_quality * 0.7 + np.random.normal(0, 0.5, n)  # Customer Service
        x3 = np.random.normal(0, 1, n)  # Packaging Design
        # CSAT outcome driven primarily by x1 and x2
        y = 0.5 * x1 + 0.3 * x2 + 0.1 * x3 + np.random.normal(0, 0.3, n)

        X = np.column_stack([x1, x2, x3])
        feature_names = ["Product Quality", "Customer Service", "Packaging"]

        res = johnsons_relative_weights(X, y, feature_names)
        self.assertGreater(res["model_r_squared"], 0.5)

        drivers = res["drivers"]
        self.assertEqual(len(drivers), 3)

        # Invariant check: sum of raw relative weights == R^2
        raw_sum = sum(d["relative_weight_raw"] for d in drivers)
        self.assertAlmostEqual(raw_sum, res["model_r_squared"], places=4)

        # Invariant check: sum of relative importance percentages == 100%
        pct_sum = sum(d["relative_importance_pct"] for d in drivers)
        self.assertAlmostEqual(pct_sum, 100.0, places=1)

        # Product Quality should be the #1 driver
        self.assertEqual(drivers[0]["feature"], "Product Quality")

    def test_johnsons_relative_weights_tikhonov_regularization(self):
        """Test near-singular collinear matrix triggers Tikhonov guard cleanly."""
        np.random.seed(42)
        n = 100
        x1 = np.random.normal(0, 1, n)
        x2 = x1 + np.random.normal(0, 1e-4, n)  # 99.999% collinear!
        y = 0.8 * x1 + np.random.normal(0, 0.2, n)

        X = np.column_stack([x1, x2])
        res = johnsons_relative_weights(X, y, ["Feature 1", "Feature 2"])
        self.assertTrue(res["is_tikhonov_regularized"])
        self.assertGreater(res["model_r_squared"], 0.0)


if __name__ == "__main__":
    unittest.main()
