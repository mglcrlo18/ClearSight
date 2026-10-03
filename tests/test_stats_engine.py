"""
Unit tests for ClearSight statistical engine.
Verifies all known-answer mathematical benchmarks from QA Audit.
"""

import math
import numpy as np
import pandas as pd
try:
    import pytest
except ImportError:
    pytest = None

import engine.stats_engine as se

f_distribution_p_value = se.f_distribution_p_value
normal_p_value_2sided = se.normal_p_value_2sided
calculate_kish_neff = se.calculate_kish_neff
calculate_rim_weights = se.calculate_rim_weights
z_test_pairwise_proportions = se.test_pairwise_proportions
z_test_vs_total_benchmark = se.test_vs_total_benchmark
welch_t_test_means = se.test_means_significance
apply_fdr_benjamini_hochberg = se.apply_fdr_benjamini_hochberg
apply_fdr_benjamini_yekutieli = se.apply_fdr_benjamini_yekutieli
rao_scott_second_order_mrcv = se.rao_scott_second_order_mrcv
from engine.driver_analysis import compute_johnsons_relative_weights


def test_f_distribution_p_value_known_points():
    """CS-004 verification: F p-values must be strictly in [0, 1] and match known values."""
    # F = 3.0, df1 = 0.87, df2 = 2000
    p_val = f_distribution_p_value(3.0, 0.87, 2000.0)
    assert 0.0 <= p_val <= 1.0
    # Expected value around 0.088
    assert abs(p_val - 0.088) < 0.01

    # Edge cases
    assert f_distribution_p_value(0.0, 2.0, 50.0) == 1.0
    assert 0.0 <= f_distribution_p_value(15.0, 3.0, 100.0) <= 0.001


def test_normal_p_value_large_z():
    """CS-114 verification: large z values must not prematurely collapse to 0.0."""
    p_val_9 = normal_p_value_2sided(9.0)
    assert p_val_9 > 0.0
    assert p_val_9 < 1e-15


def test_kish_neff_calculation():
    """Kish effective base calculation check."""
    # Equal weights -> Neff = N
    w_equal = np.ones(100)
    assert abs(calculate_kish_neff(w_equal) - 100.0) < 1e-5

    # Known unequal weights
    w_unequal = np.array([2.0] * 50 + [0.5] * 50)
    # sum(w) = 125, sum(w^2) = 50*4 + 50*0.25 = 200 + 12.5 = 212.5
    # Neff = 125^2 / 212.5 = 15625 / 212.5 = 73.529
    assert abs(calculate_kish_neff(w_unequal) - 73.529) < 0.01


def test_rim_weighting_convergence_and_re_raking():
    """CS-011, CS-012, CS-013: Rim weighting converges and respects target margins."""
    np.random.seed(123)
    df = pd.DataFrame({
        "Region": ["NCR"] * 30 + ["Luzon"] * 50 + ["VisMin"] * 20,
        "Gender": ["Female"] * 60 + ["Male"] * 40
    })

    targets = {
        "Region": {"NCR": 0.20, "Luzon": 0.50, "VisMin": 0.30},
        "Gender": {"Female": 0.50, "Male": 0.50}
    }

    weights, diag = calculate_rim_weights(df, targets, trim_percentile=95.0)
    assert diag["converged"] is True
    assert diag["max_margin_error_pct"] < 2.0
    assert abs(np.sum(weights) - len(df)) < 0.1


def test_rim_weighting_empty_category_error():
    """CS-051: Target category with zero sample respondents raises clear ValueError."""
    df = pd.DataFrame({"Region": ["NCR"] * 10})
    targets = {"Region": {"NCR": 0.50, "Mindanao": 0.50}}
    threw = False
    try:
        calculate_rim_weights(df, targets)
    except ValueError as exc:
        threw = True
        assert "has 0 respondents" in str(exc)
    assert threw, "Expected ValueError when target category has 0 respondents"


def test_benchmark_vs_rest_of_sample():
    """CS-014: Column vs rest-of-sample benchmark test eliminates part-whole overlap bias."""
    # Column: n=100, p=0.60. Total: N=400, p=0.45.
    # Rest of sample: n=300, p = (400*0.45 - 100*0.60) / 300 = (180 - 60)/300 = 120/300 = 0.40.
    marker = z_test_vs_total_benchmark(p_col=0.60, p_total=0.45, n_col=100, n_total=400)
    # The true difference (0.60 vs 0.40) is highly significant
    assert marker == "++"


def test_fdr_corrections_nan_handling():
    """CS-053: Benjamini-Hochberg must not mark NaNs as significant."""
    p_vals = [0.01, float('nan'), 0.02, 0.85]
    bh_sig = apply_fdr_benjamini_hochberg(p_vals, alpha=0.05)
    assert bh_sig[0] is True
    assert bh_sig[1] is False  # NaN must be False
    assert bh_sig[2] is True
    assert bh_sig[3] is False

    by_sig = apply_fdr_benjamini_yekutieli(p_vals, alpha=0.05)
    assert by_sig[1] is False


def test_johnsons_relative_weights():
    """CS-056, CS-057: Shares must strictly sum to 100% without ddof inflation."""
    np.random.seed(42)
    N = 100
    x1 = np.random.normal(0, 1, N)
    x2 = 0.6 * x1 + np.random.normal(0, 0.8, N)
    y = 0.5 * x1 + 0.3 * x2 + np.random.normal(0, 0.5, N)

    df = pd.DataFrame({"Y": y, "X1": x1, "X2": x2})
    res = compute_johnsons_relative_weights(df, "Y", ["X1", "X2"])
    assert "weights" in res
    assert 0.0 < res["r_squared"] <= 1.0

    total_shares = sum(w["relative_importance_pct"] for w in res["weights"])
    assert abs(total_shares - 100.0) < 0.5
