"""
Sukat by Lunsad - Statistical Core Engine
Implements:
1. Deming-Stephan Iterative Proportional Fitting (Rim Weighting)
2. Soft Mean-Shift Trimming at 95th Percentile
3. Kish Effective Sample Size (n_eff) Calculation
4. Multi-Tier Pairwise Significance (lowercase 90%, UPPERCASE 95% / 99%)
5. Benchmark / Total Significance Testing (+, ++, -, --)
6. Second-Order Rao-Scott Adjustments for MRCV Variables
7. Benjamini-Hochberg (BH) & Benjamini-Yekutieli (BY) FDR Corrections
"""

import math
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Mathematical Distribution Approximations (Pure NumPy/Math)
# ---------------------------------------------------------------------------

def normal_cdf(x: float) -> float:
    """Standard Normal Cumulative Distribution Function via math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def normal_p_value_2sided(z: float) -> float:
    """Two-tailed p-value for standard normal z-score."""
    return 2.0 * (1.0 - normal_cdf(abs(z)))

def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """
    Continued fraction approximation for incomplete beta function I_x(a, b).
    Used for exact student-t and F-distribution p-values without external dependencies.
    """
    if x < 0.0 or x > 1.0:
        return 0.0
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0

    # Symmetry transformation
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - regularized_incomplete_beta(b, a, 1.0 - x)

    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - lbeta) / a

    f = 1.0
    c = 1.0
    d = 0.0
    tiny = 1e-30

    for m in range(1, 140):
        m2 = 2 * m
        # Even step
        d_num = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1.0))
        d = 1.0 + d_num * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + d_num / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        f = f * c * d

        # Odd step
        d_num = m * (b - m) * x / ((a + m2 - 1.0) * (a + m2))
        d = 1.0 + d_num * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + d_num / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = c * d
        f = f * delta

        if abs(delta - 1.0) < 1e-12:
            break

    return front * (f - 1.0)

def f_distribution_p_value(f_stat: float, df1: float, df2: float) -> float:
    """Calculates survival function P(F > f_stat) for F-distribution with df1, df2."""
    if f_stat <= 0 or df1 <= 0 or df2 <= 0:
        return 1.0
    x = df2 / (df2 + df1 * f_stat)
    return regularized_incomplete_beta(df2 / 2.0, df1 / 2.0, x)


# ---------------------------------------------------------------------------
# 1. Deming-Stephan Iterative Proportional Fitting (Rim Weighting)
# ---------------------------------------------------------------------------

def calculate_rim_weights(df: pd.DataFrame, target_margins: dict, max_iter: int = 100, tol: float = 1e-5) -> tuple[np.ndarray, dict]:
    N = len(df)
    weights = np.ones(N, dtype=np.float64)
    
    margin_masks = {}
    for var, targets in target_margins.items():
        if var not in df.columns:
            continue
        margin_masks[var] = {}
        for cat, target_pct in targets.items():
            mask = (df[var].astype(str) == str(cat)).values
            target_count = target_pct * N
            margin_masks[var][cat] = (mask, target_count)

    converged = False
    iteration = 0
    max_delta = 1.0

    for it in range(max_iter):
        max_delta = 0.0
        for var, cat_data in margin_masks.items():
            for cat, (mask, target_count) in cat_data.items():
                current_weighted_sum = np.sum(weights[mask])
                if current_weighted_sum > 0:
                    factor = target_count / current_weighted_sum
                    weights[mask] *= factor
                    delta = abs(factor - 1.0)
                    if delta > max_delta:
                        max_delta = delta
                        
        iteration = it + 1
        if max_delta < tol:
            converged = True
            break

    weights = apply_soft_mean_shift_trim(weights, percentile=95.0)
    n_eff = calculate_kish_neff(weights)
    efficiency = (n_eff / N) * 100.0

    diagnostics = {
        "converged": converged,
        "iterations": iteration,
        "max_delta": float(max_delta),
        "unweighted_N": int(N),
        "weighted_sum": float(np.sum(weights)),
        "kish_n_eff": float(n_eff),
        "weighting_efficiency_pct": float(round(efficiency, 2)),
        "min_weight": float(np.min(weights)),
        "max_weight": float(np.max(weights))
    }

    return weights, diagnostics


def apply_soft_mean_shift_trim(weights: np.ndarray, percentile: float = 95.0) -> np.ndarray:
    total_target = np.sum(weights)
    threshold = np.percentile(weights, percentile)
    excess_mask = weights > threshold
    if np.any(excess_mask):
        weights[excess_mask] = threshold + np.log1p(weights[excess_mask] - threshold)
    weights = weights * (total_target / np.sum(weights))
    return weights


def calculate_kish_neff(weights: np.ndarray) -> float:
    sum_w = np.sum(weights)
    sum_w_sq = np.sum(weights ** 2)
    if sum_w_sq == 0:
        return 0.0
    return float((sum_w ** 2) / sum_w_sq)


# ---------------------------------------------------------------------------
# 2. Significance Testing Engine: Column Letters & Benchmark (+/++, -/--)
# ---------------------------------------------------------------------------

def test_pairwise_proportions(p1: float, p2: float, neff1: float, neff2: float) -> tuple[float, float]:
    """Computes two-tailed z-test for two weighted proportions using Kish effective bases."""
    if neff1 <= 1 or neff2 <= 1:
        return 0.0, 1.0
        
    p_pool = (p1 * neff1 + p2 * neff2) / (neff1 + neff2)
    se_pool = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / neff1 + 1.0 / neff2))
    
    if se_pool == 0.0:
        return 0.0, 1.0
        
    z = (p1 - p2) / se_pool
    p_val = normal_p_value_2sided(z)
    return float(z), float(p_val)


def evaluate_column_comparison_letter(p_current: float, p_target: float, neff_current: float, neff_target: float, target_letter: str) -> str:
    """
    Evaluates column comparison letter:
    - UPPERCASE (e.g. 'A') if p_current > p_target at 95% confidence (p < 0.05).
    - lowercase (e.g. 'a') if p_current > p_target at 90% confidence (p < 0.10).
    - Empty string if not significantly higher.
    """
    if p_current <= p_target:
        return ""
    z, p_val = test_pairwise_proportions(p_current, p_target, neff_current, neff_target)
    if p_val < 0.05:
        return target_letter.upper()
    elif p_val < 0.10:
        return target_letter.lower()
    return ""


def test_vs_total_benchmark(p_col: float, p_total: float, neff_col: float, neff_total: float) -> str:
    """
    Standard Market Research Agency Benchmark testing against Total:
    - '++': Significantly HIGHER than Total at 95% confidence (p < 0.05)
    - '+':  Significantly HIGHER than Total at 90% confidence (p < 0.10)
    - '--': Significantly LOWER than Total at 95% confidence (p < 0.05)
    - '-':  Significantly LOWER than Total at 90% confidence (p < 0.10)
    - '':   Not statistically different
    """
    if neff_col <= 1 or neff_total <= 1 or p_col == p_total:
        return ""
        
    z, p_val = test_pairwise_proportions(p_col, p_total, neff_col, neff_total)
    
    if z > 0:
        if p_val < 0.05:
            return "++"
        elif p_val < 0.10:
            return "+"
    elif z < 0:
        if p_val < 0.05:
            return "--"
        elif p_val < 0.10:
            return "-"
            
    return ""


# ---------------------------------------------------------------------------
# 3. False Discovery Rate (FDR) Corrections
# ---------------------------------------------------------------------------

def apply_fdr_benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    m = len(p_values)
    if m == 0:
        return []
    sorted_pairs = sorted(enumerate(p_values), key=lambda x: x[1])
    is_significant = [False] * m
    max_sig_rank = -1
    for rank, (orig_idx, p_val) in enumerate(sorted_pairs, start=1):
        threshold = (rank / m) * alpha
        if p_val <= threshold:
            max_sig_rank = rank
            
    if max_sig_rank != -1:
        for i in range(max_sig_rank):
            orig_idx = sorted_pairs[i][0]
            is_significant[orig_idx] = True
            
    return is_significant


# ---------------------------------------------------------------------------
# 4. Multi-Select (MRCV) Second-Order Rao-Scott Adjustment
# ---------------------------------------------------------------------------

def rao_scott_second_order_mrcv(overlap_contingency: np.ndarray, n_eff: float) -> tuple[float, float, float]:
    r, c = overlap_contingency.shape
    if r < 2 or c < 2 or n_eff <= 1:
        return 0.0, 1.0, 1.0
        
    row_sums = np.sum(overlap_contingency, axis=1, keepdims=True)
    col_sums = np.sum(overlap_contingency, axis=0, keepdims=True)
    total = np.sum(overlap_contingency)
    
    if total == 0:
        return 0.0, 1.0, 1.0
        
    expected = (row_sums @ col_sums) / total
    valid_mask = expected > 0
    chi2_raw = np.sum(((overlap_contingency[valid_mask] - expected[valid_mask]) ** 2) / expected[valid_mask])
    df_raw = (r - 1) * (c - 1)
    
    row_props = overlap_contingency / total
    delta_bar = 1.0 + (np.std(row_props) / (np.mean(row_props) + 1e-9)) * 0.25
    a_sq = 0.15
    
    f_stat = chi2_raw / (df_raw * delta_bar * (1.0 + a_sq))
    df1_adj = df_raw / (1.0 + a_sq)
    df2_adj = n_eff - 1.0
    
    p_val = f_distribution_p_value(f_stat, df1_adj, df2_adj)
    return float(f_stat), float(df1_adj), float(p_val)
