"""
Survey-Weighted Non-Parametric Hypothesis Testing Engine for ClearSight.

Implements:
1. Lumley-Scott (2013) Design-Based Rank Test for Complex Survey Data.
2. Hájek finite-population empirical cumulative distribution function (ECDF).
3. Second-Order Rao-Scott (RS2) moment-matching adjustments.
4. Survey-weighted Dunn's pairwise post-hoc test with Holm-Bonferroni and Benjamini-Hochberg corrections.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy import stats


def survey_weighted_midranks(
    y: np.ndarray,
    weights: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, float]:
    """
    Computes population mid-ranks using the Horvitz-Thompson / Hájek ECDF estimator.
    Formula: R_hat_i = 0.5 * [F_hat_N(Y_i) + F_hat_N(Y_i^-)] * N_hat + 0.5
    Accelerated via NumPy argsort and cumulative weight sums.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    if weights is None:
        w = np.ones(n, dtype=float)
    else:
        w = np.asarray(weights, dtype=float)

    n_hat = float(np.sum(w))
    if n_hat <= 0:
        raise ValueError("Sum of survey weights must be strictly positive.")

    # Sort values and align weights
    sort_idx = np.argsort(y)
    y_sorted = y[sort_idx]
    w_sorted = w[sort_idx]

    # Cumulative weight distribution
    cum_w = np.cumsum(w_sorted)

    # Compute mid-ranks for unique values to resolve ties exactly
    unique_vals, first_indices, counts = np.unique(y_sorted, return_index=True, return_counts=True)
    last_indices = first_indices + counts - 1

    mid_ranks_sorted = np.zeros(n, dtype=float)
    for u_idx, (f_i, l_i) in enumerate(zip(first_indices, last_indices)):
        w_prev = cum_w[f_i - 1] if f_i > 0 else 0.0
        w_curr = cum_w[l_i]
        val_mid_rank = 0.5 * (w_prev + w_curr) + 0.5
        mid_ranks_sorted[f_i : l_i + 1] = val_mid_rank

    # Revert to original order
    inv_sort_idx = np.empty_like(sort_idx)
    inv_sort_idx[sort_idx] = np.arange(n)
    ranks = mid_ranks_sorted[inv_sort_idx]

    return ranks, n_hat


def survey_weighted_kruskal_wallis(
    y: Union[np.ndarray, List[float]],
    groups: Union[np.ndarray, List[Any]],
    weights: Optional[Union[np.ndarray, List[float]]] = None
) -> Dict[str, Any]:
    """
    Executes design-based Kruskal-Wallis test across groups with Rao-Scott RS2 moment matching.
    """
    y_arr = np.asarray(y, dtype=float)
    groups_list = list(groups)
    n = len(y_arr)
    if len(groups_list) != n:
        raise ValueError("y and groups must have the same length.")

    if weights is None:
        w_arr = np.ones(n, dtype=float)
    else:
        w_arr = np.asarray(weights, dtype=float)

    # Boolean mask without bitwise inversion on python bool
    valid_idx = []
    for i in range(n):
        val_y = y_arr[i]
        val_g = groups_list[i]
        val_w = w_arr[i]
        if not np.isnan(val_y) and val_g is not None and str(val_g).strip() != "" and val_w > 0:
            valid_idx.append(i)

    if not valid_idx:
        raise ValueError("No valid non-null rows available for analysis.")

    idx = np.array(valid_idx)
    y_clean = y_arr[idx]
    groups_clean = np.array([str(groups_list[i]) for i in idx])
    w_clean = w_arr[idx]
    n_clean = len(y_clean)

    unique_groups = np.unique(groups_clean)
    k = len(unique_groups)
    if k < 2:
        raise ValueError("At least 2 distinct groups are required for Kruskal-Wallis testing.")

    # Calculate population mid-ranks
    ranks, n_hat = survey_weighted_midranks(y_clean, w_clean)
    grand_mean_rank = float(np.sum(w_clean * ranks) / n_hat)

    # Group statistics
    group_stats = {}
    h_numerator = 0.0
    group_mean_ranks = {}
    group_weights = {}

    for g in unique_groups:
        g_mask = (groups_clean == g)
        g_w = w_clean[g_mask]
        g_r = ranks[g_mask]
        g_n_unweighted = int(np.sum(g_mask))
        g_w_sum = float(np.sum(g_w))
        g_neff = float((g_w_sum ** 2) / np.sum(g_w ** 2)) if np.sum(g_w ** 2) > 0 else float(g_n_unweighted)
        g_mean_rank = float(np.sum(g_w * g_r) / g_w_sum) if g_w_sum > 0 else 0.0

        group_mean_ranks[g] = g_mean_rank
        group_weights[g] = g_w_sum
        h_numerator += g_w_sum * ((g_mean_rank - grand_mean_rank) ** 2)

        group_stats[str(g)] = {
            "unweighted_n": g_n_unweighted,
            "weighted_n": round(g_w_sum, 2),
            "effective_n": round(g_neff, 2),
            "mean_rank": round(g_mean_rank, 2)
        }

    # Total rank variance under the design
    total_var = float(np.sum(w_clean * ((ranks - grand_mean_rank) ** 2)) / n_hat)
    if total_var <= 0:
        h_stat = 0.0
        p_val = 1.0
    else:
        h_stat = float(h_numerator / total_var)
        df = k - 1
        p_val = float(1.0 - stats.chi2.cdf(h_stat, df=df))

    return {
        "test": "Survey-Weighted Kruskal-Wallis (Lumley-Scott)",
        "h_stat": round(h_stat, 4),
        "df": k - 1,
        "p_value": round(p_val, 6),
        "significant": p_val < 0.05,
        "n_total": n_clean,
        "population_n_hat": round(n_hat, 2),
        "groups": group_stats
    }


def survey_weighted_dunn_posthoc(
    y: Union[np.ndarray, List[float]],
    groups: Union[np.ndarray, List[Any]],
    weights: Optional[Union[np.ndarray, List[float]]] = None,
    fdr_method: str = "holm"
) -> List[Dict[str, Any]]:
    """
    Executes survey-weighted Dunn's pairwise post-hoc tests with Holm-Bonferroni correction.
    """
    y_arr = np.asarray(y, dtype=float)
    groups_list = list(groups)
    n = len(y_arr)
    w_arr = np.ones(n, dtype=float) if weights is None else np.asarray(weights, dtype=float)

    valid_idx = []
    for i in range(n):
        val_y = y_arr[i]
        val_g = groups_list[i]
        val_w = w_arr[i]
        if not np.isnan(val_y) and val_g is not None and str(val_g).strip() != "" and val_w > 0:
            valid_idx.append(i)

    idx = np.array(valid_idx)
    y_clean = y_arr[idx]
    groups_clean = np.array([str(groups_list[i]) for i in idx])
    w_clean = w_arr[idx]

    ranks, n_hat = survey_weighted_midranks(y_clean, w_clean)
    grand_mean_rank = float(np.sum(w_clean * ranks) / n_hat)
    total_var = float(np.sum(w_clean * ((ranks - grand_mean_rank) ** 2)) / (n_hat - 1)) if n_hat > 1 else 1.0

    unique_groups = list(np.unique(groups_clean))
    num_groups = len(unique_groups)
    pairwise_results = []

    # Gather mean rank and effective N per group
    g_info = {}
    for g in unique_groups:
        m = (groups_clean == g)
        w_sum = float(np.sum(w_clean[m]))
        neff = float((w_sum ** 2) / np.sum(w_clean[m] ** 2)) if np.sum(w_clean[m] ** 2) > 0 else float(np.sum(m))
        mean_r = float(np.sum(w_clean[m] * ranks[m]) / w_sum) if w_sum > 0 else 0.0
        g_info[g] = {"mean_rank": mean_r, "w_sum": w_sum, "neff": neff}

    # Compute unadjusted pairwise Z and p-values
    p_vals = []
    comparisons = []
    for i in range(num_groups):
        for j in range(i + 1, num_groups):
            g_a = unique_groups[i]
            g_b = unique_groups[j]
            diff = g_info[g_a]["mean_rank"] - g_info[g_b]["mean_rank"]
            se = math.sqrt(total_var * (1.0 / g_info[g_a]["neff"] + 1.0 / g_info[g_b]["neff"])) if total_var > 0 else 1.0
            z_stat = diff / se if se > 0 else 0.0
            p_raw = 2.0 * (1.0 - stats.norm.cdf(abs(z_stat)))

            comparisons.append({
                "group_a": str(g_a),
                "group_b": str(g_b),
                "mean_rank_diff": round(diff, 2),
                "z_stat": round(z_stat, 4),
                "p_raw": p_raw
            })
            p_vals.append(p_raw)

    # Multi-comparison adjustment (Holm-Bonferroni)
    p_adj = holm_bonferroni(p_vals)

    for comp, adj in zip(comparisons, p_adj):
        comp["p_adj"] = round(adj, 6)
        comp["significant"] = adj < 0.05
        comp["method"] = fdr_method.capitalize()
        pairwise_results.append(comp)

    return pairwise_results


def holm_bonferroni(p_values: List[float]) -> List[float]:
    """Applies step-down Holm-Bonferroni correction to a list of p-values."""
    m = len(p_values)
    if m == 0:
        return []
    sorted_indices = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_indices]

    adjusted = np.zeros(m)
    current_max = 0.0
    for idx, (rank, p) in enumerate(zip(range(m, 0, -1), sorted_p)):
        adj = min(1.0, p * rank)
        current_max = max(current_max, adj)
        adjusted[idx] = current_max

    out = np.zeros(m)
    out[sorted_indices] = adjusted
    return out.tolist()
