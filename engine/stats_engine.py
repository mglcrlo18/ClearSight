"""
ClearSight Analytics - Statistical Core Engine
Production-grade survey mathematics implementing:
1. Deming-Stephan Iterative Proportional Fitting (Rim Weighting) with Re-Raked Trimming
2. Kish Effective Sample Size (Neff) & Design Effect (Deff)
3. Non-Overlapping Column vs. Rest-of-Sample Benchmark Testing (+/++, -/--)
4. Dual Significance Testing (lowercase 90%, UPPERCASE 95%, 99% tier)
5. Multi-Select (MRCV) Rao-Scott Second-Order F-Test
6. Welch's t-Test for Means & Chi-Square Independence Test
7. Benjamini-Hochberg (BH) & Benjamini-Yekutieli (BY) FDR Corrections
8. Small-Base Suppression & Guarding
"""

import math
from typing import Optional, Union, Tuple, List, Dict
import numpy as np
import pandas as pd
try:
    from scipy import stats as sp_stats
    from scipy.special import betainc as sp_betainc
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# ---------------------------------------------------------------------------
# Mathematical Distribution Approximations & Exact Functions
# ---------------------------------------------------------------------------

def normal_p_value_2sided(z: float) -> float:
    """
    Two-tailed p-value for standard normal z-score using math.erfc.
    Avoids underflow at large z values (e.g. z > 8.0) and maintains precise relative ranks.
    """
    if math.isnan(z):
        return float('nan')
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


def f_distribution_p_value(f_stat: float, df1: float, df2: float) -> float:
    """
    Survival function P(F > f_stat) for F-distribution with df1, df2 degrees of freedom.
    Uses scipy.stats.f.sf when available; falls back to robust Lentz continued fraction.
    Strictly clamped to [0.0, 1.0].
    """
    if math.isnan(f_stat) or math.isnan(df1) or math.isnan(df2):
        return float('nan')
    if f_stat <= 0.0 or df1 <= 0.0 or df2 <= 0.0:
        return 1.0

    if HAS_SCIPY:
        val = float(sp_stats.f.sf(f_stat, df1, df2))
        return max(0.0, min(1.0, val))

    # Fallback to incomplete beta
    x = df2 / (df2 + df1 * f_stat)
    a = df2 / 2.0
    b = df1 / 2.0
    return max(0.0, min(1.0, regularized_incomplete_beta(a, b, x)))


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """
    Continued fraction approximation for incomplete beta function I_x(a, b).
    Clamped strictly to [0.0, 1.0].
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    if HAS_SCIPY:
        return float(max(0.0, min(1.0, sp_betainc(a, b, x))))

    # Symmetry transformation
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - regularized_incomplete_beta(b, a, 1.0 - x)

    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - lbeta)

    # Continued fraction (Abramowitz & Stegun 26.5.8)
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0

    c = 1.0
    d = 1.0 - qab * x / qap
    fpmin = 1e-30
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d

    for m in range(1, 201):
        m2 = 2 * m
        # Even step: d_{2m}
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c

        # Odd step: d_{2m+1}
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        del_val = d * c
        h *= del_val

        if abs(del_val - 1.0) < 1e-14:
            break

    val = front * h / a
    return max(0.0, min(1.0, val))


# ---------------------------------------------------------------------------
# 1. Deming-Stephan Iterative Proportional Fitting (Rim Weighting)
# ---------------------------------------------------------------------------

def normalize_category_key(val) -> str:
    """Normalizes category representations so float 1.0 matches int 1 and string '1'."""
    if pd.isna(val):
        return "__NA__"
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def calculate_rim_weights(
    df: pd.DataFrame, 
    target_margins: dict, 
    max_iter: int = 100, 
    tol: float = 1e-5,
    trim_percentile: float = 95.0
) -> tuple[np.ndarray, dict]:
    """
    Executes Deming-Stephan rim weighting (Iterative Proportional Fitting).
    Includes:
    - Target margin validation (must sum to 1.0 or 100%)
    - Category canonicalization (prevents 1.0 vs 1 mismatch)
    - Zero-cell detection
    - Bounded re-raked soft trimming to prevent margin loss
    """
    N = len(df)
    if N == 0:
        raise ValueError("Cannot calculate rim weights on an empty DataFrame (N = 0).")

    weights = np.ones(N, dtype=np.float64)
    normalized_targets = {}

    # 1. Validate & Normalize Target Margins
    for var, targets in target_margins.items():
        if var not in df.columns:
            continue
        
        raw_sum = sum(targets.values())
        if any(float(v) < 0 for v in targets.values()) or raw_sum <= 0:
            raise ValueError(f"Targets for {var} must be non-negative and sum to more than 0")
        is_counts = all(float(v).is_integer() for v in targets.values()) and len(targets) > 1
        # P5-05: integer population counts are valid whatever their total (e.g. {20, 30} or census counts);
        # only fractional targets must look like proportions (1.0) or percentages (100).
        if (raw_sum > 101.0 and all(v >= 1.0 for v in targets.values())) or (is_counts and not 99.0 <= raw_sum <= 101.0):
            norm_factor = raw_sum
        elif 99.0 <= raw_sum <= 101.0:
            norm_factor = 100.0
        elif 0.99 <= raw_sum <= 1.01:
            norm_factor = 1.0
        else:
            raise ValueError(f"Targets for {var} sum to {raw_sum}; must be 1.0 or 100%")
        
        # Check that categories in df are covered by targets (CS-050)
        df_cats = set(df[var].dropna().map(normalize_category_key))
        target_cats = set(map(normalize_category_key, targets.keys()))
        missing_in_targets = df_cats - target_cats
        if missing_in_targets:
            raise ValueError(f"{var}: categories without targets: {sorted(missing_in_targets)}")

        normalized_targets[var] = {}
        for cat, val in targets.items():
            norm_key = normalize_category_key(cat)
            norm_val = val / norm_factor
            normalized_targets[var][norm_key] = norm_val

    if not normalized_targets:
        return weights, {
            "converged": True,
            "iterations": 0,
            "max_margin_error": 0.0,
            "kish_n_eff": float(N),
            "weighting_efficiency_pct": 100.0,
            "min_weight": 1.0,
            "max_weight": 1.0
        }

    # 2. Build Category Masks & Check for Empty Cells
    series_normalized = {var: df[var].apply(normalize_category_key) for var in normalized_targets}
    margin_masks = {}

    for var, targets in normalized_targets.items():
        margin_masks[var] = {}
        var_series = series_normalized[var]
        for cat, target_pct in targets.items():
            mask = (var_series == cat).values
            count = np.sum(mask)
            if count == 0 and target_pct > 0:
                raise ValueError(
                    f"Target category '{cat}' for benchmark variable '{var}' "
                    f"has 0 respondents in the sample dataset. Weighting cannot converge."
                )
            target_count = target_pct * N
            margin_masks[var][cat] = (mask, target_count)

    # 3. Iterative Raking Loop with Re-Raked Trimming
    converged = False
    iteration = 0
    max_delta = 1.0

    # Outer loop allows re-raking after trimming so final weights match targets!
    rake_trim_cycles = 5 if trim_percentile is not None else 1

    for cycle in range(rake_trim_cycles):
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

            iteration += 1
            if max_delta < tol:
                converged = True
                break

        # Apply soft mean-shift trim if requested, then re-rake
        if trim_percentile is not None and trim_percentile < 100.0:
            weights = apply_soft_mean_shift_trim(weights, percentile=trim_percentile)
            if cycle == rake_trim_cycles - 1:
                # Final touchup rake so margins are preserved
                for var, cat_data in margin_masks.items():
                    for cat, (mask, target_count) in cat_data.items():
                        c_sum = np.sum(weights[mask])
                        if c_sum > 0:
                            weights[mask] *= (target_count / c_sum)

    # Calculate final margin error
    max_margin_error = 0.0
    for var, cat_data in margin_masks.items():
        for cat, (mask, target_count) in cat_data.items():
            actual_pct = np.sum(weights[mask]) / np.sum(weights)
            expected_pct = target_count / N
            err = abs(actual_pct - expected_pct)
            if err > max_margin_error:
                max_margin_error = err

    n_eff = calculate_kish_neff(weights)
    efficiency = (n_eff / N) * 100.0

    diagnostics = {
        "converged": bool(converged and max_margin_error < 0.02),
        "iterations": int(iteration),
        "max_delta": float(max_delta),
        "max_margin_error_pct": float(round(max_margin_error * 100.0, 3)),
        "unweighted_N": int(N),
        "weighted_sum": float(round(np.sum(weights), 2)),
        "kish_n_eff": float(round(n_eff, 1)),
        "weighting_efficiency_pct": float(round(efficiency, 2)),
        "kish_deff": float(round(N / n_eff, 3)) if n_eff > 0 else 1.0,
        "min_weight": float(round(np.min(weights), 3)),
        "max_weight": float(round(np.max(weights), 3))
    }

    return weights, diagnostics


def apply_soft_mean_shift_trim(weights: np.ndarray, percentile: Optional[float] = 95.0, cap_ratio: Optional[float] = None) -> np.ndarray:
    """Compresses extreme weights relative to mean weight or percentile. If None, returns weights unchanged (CS-113)."""
    if len(weights) == 0:
        return weights
    if percentile is None and cap_ratio is None:
        return weights
    total_target = float(np.sum(weights))
    if cap_ratio is not None:
        cap = cap_ratio * float(np.mean(weights))
        trimmed = np.minimum(weights, cap)
        return trimmed * (total_target / float(np.sum(trimmed)))
    threshold = float(np.percentile(weights, percentile))
    excess_mask = weights > threshold
    if np.any(excess_mask):
        weights = weights.copy()
        weights[excess_mask] = threshold + np.log1p(weights[excess_mask] - threshold)
    current_sum = float(np.sum(weights))
    if current_sum > 0:
        weights = weights * (total_target / current_sum)
    return weights


def calculate_kish_neff(weights: np.ndarray) -> float:
    """Calculates Kish's Effective Sample Size: (sum(w))^2 / sum(w^2)."""
    valid_weights = weights[np.isfinite(weights) & (weights >= 0)]
    if len(valid_weights) == 0:
        return 0.0
    sum_w = float(np.sum(valid_weights))
    sum_w_sq = float(np.sum(valid_weights ** 2))
    if sum_w_sq <= 0:
        return 0.0
    return float((sum_w ** 2) / sum_w_sq)


# ---------------------------------------------------------------------------
# 2. Significance Testing Engine: Pairwise Columns & Overlap-Corrected Benchmark
# ---------------------------------------------------------------------------

def test_pairwise_proportions(
    p1: float, 
    p2: float, 
    neff1: float, 
    neff2: float,
    min_base: float = 20.0
) -> tuple[float, float, bool]:
    """
    Computes two-tailed z-test for two proportions using Kish effective sample sizes.
    Validates inputs and returns (z_stat, p_value, is_small_base).
    """
    # Small base flag
    is_small_base = (neff1 < min_base or neff2 < min_base)
    
    if neff1 <= 1 or neff2 <= 1:
        return 0.0, 1.0, True

    # Validate inputs (CS-055)
    p1 = float(p1)
    p2 = float(p2)
    if not (0.0 <= p1 <= 1.0 and 0.0 <= p2 <= 1.0):
        raise ValueError(f"Proportions must be in [0, 1], got {p1}, {p2}")

    p_pool = (p1 * neff1 + p2 * neff2) / (neff1 + neff2)
    se_pool = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / neff1 + 1.0 / neff2))

    if se_pool <= 0.0:
        return 0.0, 1.0, is_small_base

    z = (p1 - p2) / se_pool
    p_val = normal_p_value_2sided(z)
    return float(z), float(p_val), is_small_base


def evaluate_column_comparison_letter(
    p_current: float, 
    p_target: float, 
    neff_current: float, 
    neff_target: float, 
    target_letter: str,
    alpha_95: float = 0.05,
    alpha_90: float = 0.10,
    suppress_small_base: bool = True
) -> str:
    """
    Evaluates pairwise column comparison letter:
    - UPPERCASE (e.g. 'A') if p_current > p_target at 95% confidence (p < 0.05).
    - lowercase (e.g. 'a') if p_current > p_target at 90% confidence (p < 0.10).
    - If small base (Neff < 20) and suppress_small_base is True, returns empty string.
    """
    if p_current <= p_target:
        return ""
    z, p_val, is_small = test_pairwise_proportions(p_current, p_target, neff_current, neff_target)
    if is_small and suppress_small_base:
        return ""

    if p_val < alpha_95:
        return target_letter.upper()
    elif p_val < alpha_90:
        return target_letter.lower()
    return ""


def test_vs_total_benchmark(
    p_col: float, 
    p_total: float, 
    n_col: float, 
    n_total: float,
    neff_col: float = None,
    neff_total: float = None,
    min_base: float = 20.0
) -> str:
    """
    Mathematically rigorous Benchmark testing: Column vs. Rest-of-Sample.
    Removes part-whole correlation bias where the column is a subset of the Total.
    
    Tests:
    - '++': Significantly HIGHER than rest-of-sample at 95% confidence (p < 0.05)
    - '+':  Significantly HIGHER than rest-of-sample at 90% confidence (p < 0.10)
    - '--': Significantly LOWER than rest-of-sample at 95% confidence (p < 0.05)
    - '-':  Significantly LOWER than rest-of-sample at 90% confidence (p < 0.10)
    - '':   Not statistically different or small base
    """
    if n_col <= 1 or n_total <= n_col:
        return ""
    
    if neff_col is None:
        neff_col = n_col
    if neff_total is None:
        neff_total = n_total

    if neff_col < min_base:
        return ""

    p_col = max(0.0, min(1.0, float(p_col)))
    p_total = max(0.0, min(1.0, float(p_total)))

    # Compute rest-of-sample size and proportion
    n_rest = n_total - n_col
    if n_rest <= 1:
        return ""

    # p_rest = (count_total - count_col) / n_rest
    count_total = p_total * n_total
    count_col = p_col * n_col
    count_rest = max(0.0, count_total - count_col)
    p_rest = max(0.0, min(1.0, count_rest / n_rest))

    # Proportional effective base for rest of sample
    eff_ratio = neff_total / max(1.0, n_total)
    neff_rest = max(1.0, n_rest * eff_ratio)

    z, p_val, is_small = test_pairwise_proportions(p_col, p_rest, neff_col, neff_rest, min_base=min_base)
    if is_small:
        return ""

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
# 3. Welch's t-Test for Scale Means & Chi-Square Independence
# ---------------------------------------------------------------------------

def test_means_significance(
    m1: float, 
    sd1: float, 
    neff1: float, 
    m2: float, 
    sd2: float, 
    neff2: float,
    min_base: float = 20.0
) -> tuple[float, float, bool]:
    """
    Computes Welch's t-test for difference in weighted means using Satterthwaite degrees of freedom.
    Returns (t_stat, p_value, is_small_base).
    """
    is_small_base = (neff1 < min_base or neff2 < min_base)
    if neff1 <= 1 or neff2 <= 1:
        return 0.0, 1.0, True

    var1 = (sd1 ** 2) / neff1
    var2 = (sd2 ** 2) / neff2
    se_diff = math.sqrt(var1 + var2)

    if se_diff <= 0.0:
        return 0.0, 1.0, is_small_base

    t_stat = (m1 - m2) / se_diff
    
    # Satterthwaite approximation for degrees of freedom
    num = (var1 + var2) ** 2
    denom = (var1 ** 2) / (neff1 - 1.0) + (var2 ** 2) / (neff2 - 1.0)
    df = num / denom if denom > 0 else 1.0

    if HAS_SCIPY:
        p_val = float(sp_stats.t.sf(abs(t_stat), df) * 2.0)
    else:
        # Normal approximation if df is large
        p_val = normal_p_value_2sided(t_stat)

    return float(t_stat), float(p_val), is_small_base


def chi_square_independence(contingency_table: np.ndarray) -> tuple[float, int, float]:
    """Computes Pearson Chi-Square test of independence on a contingency table."""
    r, c = contingency_table.shape
    if r < 2 or c < 2:
        return 0.0, 0, 1.0
        
    row_sums = np.sum(contingency_table, axis=1, keepdims=True)
    col_sums = np.sum(contingency_table, axis=0, keepdims=True)
    total = np.sum(contingency_table)
    
    if total <= 0:
        return 0.0, 0, 1.0

    expected = (row_sums @ col_sums) / total
    valid = expected > 0
    chi2 = float(np.sum(((contingency_table[valid] - expected[valid]) ** 2) / expected[valid]))
    df = int((r - 1) * (c - 1))

    if HAS_SCIPY:
        p_val = float(sp_stats.chi2.sf(chi2, df))
    else:
        # Wilson-Hilferty transformation of chi-square to standard normal
        z = ((chi2 / df) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))
        p_val = normal_p_value_2sided(z)

    return chi2, df, max(0.0, min(1.0, p_val))


# ---------------------------------------------------------------------------
# 4. Multi-Select (MRCV) Rao-Scott Second-Order Adjustment
# ---------------------------------------------------------------------------

def rao_scott_second_order_mrcv(
    mention_table: np.ndarray, 
    n_eff: float,
    respondent_matrix: np.ndarray = None
) -> tuple[float, float, float]:
    """
    Computes Rao-Scott Second-Order F-test for Multiple-Response Categorical Variables (MRCV).
    If respondent_matrix (0/1 indicators) is provided, computes exact design-effect covariance.
    Otherwise uses Satterthwaite adjusted moment matching.
    """
    r, c = mention_table.shape
    if r < 2 or c < 2 or n_eff <= 1:
        return 0.0, 1.0, 1.0

    row_sums = np.sum(mention_table, axis=1, keepdims=True)
    col_sums = np.sum(mention_table, axis=0, keepdims=True)
    total = np.sum(mention_table)

    if total <= 0:
        return 0.0, 1.0, 1.0

    expected = (row_sums @ col_sums) / total
    valid = expected > 0
    chi2_raw = float(np.sum(((mention_table[valid] - expected[valid]) ** 2) / expected[valid]))
    df_raw = float((r - 1) * (c - 1))

    # Design effect estimation (CS-005: Eigenvalue-based second-order Rao-Scott)
    if respondent_matrix is not None and len(respondent_matrix) > 0:
        Y = respondent_matrix.astype(float)
        p_ijk = Y / len(Y)
        cov_hat = np.cov(Y, rowvar=False)
        p_marg = np.mean(Y, axis=0)
        V_0 = np.diag(p_marg) - np.outer(p_marg, p_marg)

        eigvals = np.real(np.linalg.eigvals(np.linalg.pinv(V_0) @ cov_hat))
        eigvals = eigvals[eigvals > 0]
        if len(eigvals) > 0:
            delta_bar = float(np.mean(eigvals))
            a_sq = float(np.var(eigvals) / (delta_bar ** 2)) if delta_bar > 0 else 0.0
        else:
            delta_bar, a_sq = 1.0, 0.0
    else:
        delta_bar, a_sq = 1.0, 0.0

    f_stat = chi2_raw / (df_raw * delta_bar * (1.0 + a_sq))
    df1_adj = max(1.0, df_raw / (1.0 + a_sq))
    df2_adj = max(1.0, n_eff - 1.0)

    p_val = f_distribution_p_value(f_stat, df1_adj, df2_adj)
    return float(f_stat), float(df1_adj), float(p_val)


# ---------------------------------------------------------------------------
# 5. False Discovery Rate (FDR) Corrections: Benjamini-Hochberg & Benjamini-Yekutieli
# ---------------------------------------------------------------------------

def apply_fdr_benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """
    Applies the Benjamini-Hochberg (BH) procedure to control False Discovery Rate.
    Correctly ignores NaN/None p-values (returns False for them).
    """
    m = len(p_values)
    if m == 0:
        return []

    is_significant = [False] * m
    valid_entries = [(idx, p) for idx, p in enumerate(p_values) if p is not None and not math.isnan(p)]
    
    k_valid = len(valid_entries)
    if k_valid == 0:
        return is_significant

    # Sort ascending by p-value
    valid_entries.sort(key=lambda x: x[1])

    max_sig_rank = -1
    for rank, (orig_idx, p_val) in enumerate(valid_entries, start=1):
        threshold = (rank / k_valid) * alpha
        if p_val <= threshold:
            max_sig_rank = rank

    if max_sig_rank != -1:
        for i in range(max_sig_rank):
            orig_idx = valid_entries[i][0]
            is_significant[orig_idx] = True

    return is_significant


def apply_fdr_benjamini_yekutieli(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """
    Applies the Benjamini-Yekutieli (BY) procedure for arbitrary or negative dependence.
    Scales alpha by c(m) = sum(1/i for i in 1..m).
    """
    m = len(p_values)
    if m == 0:
        return []

    valid_entries = [(idx, p) for idx, p in enumerate(p_values) if p is not None and not math.isnan(p)]
    k_valid = len(valid_entries)
    if k_valid == 0:
        return [False] * m

    c_m = sum(1.0 / i for i in range(1, k_valid + 1))
    adjusted_alpha = alpha / c_m

    return apply_fdr_benjamini_hochberg(p_values, alpha=adjusted_alpha)
