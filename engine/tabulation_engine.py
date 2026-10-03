"""
ClearSight Analytics - Dynamic Cross-Tabulation & Statistical Engine
Plumbs raw survey microdata directly into rigorous significance testing:
1. Flexible Banner & Stub variable resolution (single-select, multi-select, rating scales)
2. Real bases: Unweighted N, Weighted Base Nw, Kish Effective Base Neff
3. Dual statistical testing:
   - Pairwise Column Comparisons (z-test with pooled proportions and Kish Neff; Welch t-test for means)
   - Benchmark vs. Total (Overlap-corrected Column vs. Rest-of-Sample z-test)
4. Multiple testing adjustment: Benjamini-Hochberg (BH) False Discovery Rate (FDR) per comparison family
5. Small base tracking (< 30) with explicit flags
"""

import math
import re
from collections import Counter
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import scipy.stats
from openpyxl.utils import get_column_letter

from engine.stats_engine import (
    test_pairwise_proportions,
    evaluate_column_comparison_letter,
    test_vs_total_benchmark,
    test_means_significance,
    calculate_kish_neff,
    apply_fdr_benjamini_hochberg
)


def resolve_column(df: pd.DataFrame, name: str) -> Optional[str]:
    """
    Finds matching DataFrame column by exact or alphanumeric normalized match (P3-11).
    Does NOT use loose bidirectional substrings to prevent short names capturing unrelated stubs.
    """
    if df is None or len(df.columns) == 0:
        return None
    if name in df.columns:
        return name

    clean_name = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    for col in df.columns:
        if re.sub(r'[^a-zA-Z0-9]', '', str(col)).lower() == clean_name:
            return col

    return None


def clean_label(text: str) -> str:
    """Removes trailing column letters like '(A)' or brackets."""
    return re.sub(r'\s*[\(\[]\s*[A-Z0-9]+\s*[\)\]]$', '', str(text)).strip()


def build_crosstab_table(
    df: pd.DataFrame,
    stub_name: str,
    banner_cols_input: List[str],
    weights: Optional[np.ndarray] = None,
    confidence_level: float = 0.95,
    fdr_enabled: bool = True,
    metric: str = "pct"
) -> Dict[str, Any]:
    """
    Computes a mathematically sound crosstabulation table directly from the DataFrame.
    """
    if df is None or len(df) == 0:
        return {
            "title": f"Tabulation: {stub_name}",
            "stub_label": stub_name,
            "banner_cols": ["Total"],
            "col_letters": ["Total"],
            "unweighted_bases": [0],
            "weighted_bases": [0.0],
            "effective_bases": [0.0],
            "small_base": [True],
            "rows": []
        }

    n_total_rows = len(df)
    # P3-24: Validate weights array length
    if weights is not None:
        if len(weights) != n_total_rows:
            raise ValueError(f"weights length {len(weights)} != rows {n_total_rows}")
        w_all = np.asarray(weights, dtype=float)
    else:
        w_all = np.ones(n_total_rows, dtype=float)

    # 1. Resolve Stub Column (P3-11: fail gracefully if not found)
    stub_col = resolve_column(df, stub_name)
    if stub_col is None:
        return {
            "title": stub_name,
            "stub_label": stub_name,
            "error": f"Column not found: {stub_name}",
            "banner_cols": banner_cols_input,
            "col_letters": ["Total"],
            "unweighted_bases": [0],
            "weighted_bases": [0.0],
            "effective_bases": [0.0],
            "small_base": [True],
            "rows": []
        }

    # 2. Resolve Banner Columns & Build Column Filters
    raw_banner_names = [clean_label(b) for b in banner_cols_input]
    if not raw_banner_names or raw_banner_names[0].lower() != "total":
        raw_banner_names = ["Total"] + raw_banner_names

    # Check if a single column was passed as banner (e.g. ["Total", "Region"])
    if len(raw_banner_names) == 2 and resolve_column(df, raw_banner_names[1]):
        b_col_found = resolve_column(df, raw_banner_names[1])
        unique_vals = sorted([str(v) for v in df[b_col_found].dropna().unique()])
        sub_banner_names = unique_vals
        col_masks = [df[b_col_found].astype(str) == v for v in unique_vals]
    else:
        sub_banner_names = []
        col_masks = []
        for b_name in raw_banner_names[1:]:
            matched = False
            # P3-10: Match banner value exactly in columns
            for col in df.columns:
                series_str = df[col].astype(str)
                m = (series_str == b_name)
                if m.any():
                    sub_banner_names.append(b_name)
                    col_masks.append(m)
                    matched = True
                    break
            if not matched:
                # Check if it's a binary column itself
                c_direct = resolve_column(df, b_name)
                if c_direct:
                    sub_banner_names.append(b_name)
                    col_masks.append(df[c_direct].notna() & (df[c_direct] != 0))
                else:
                    # Partial search fallback
                    for col in df.columns:
                        series_str = df[col].astype(str)
                        m = series_str.str.contains(r'\b' + re.escape(b_name) + r'\b', regex=True, na=False)
                        if m.any():
                            sub_banner_names.append(b_name)
                            col_masks.append(m)
                            matched = True
                            break
                    if not matched:
                        sub_banner_names.append(b_name)
                        col_masks.append(pd.Series(False, index=df.index))

    # Fallback to demographic if empty
    if len(sub_banner_names) == 0:
        demo_candidates = ["Region", "Age_Generation", "Gender", "Socioeconomic_Class"]
        chosen_col = None
        for cand in demo_candidates:
            if cand in df.columns and cand != stub_col:
                chosen_col = cand
                break
        if not chosen_col:
            for c in df.columns:
                if c != stub_col and 2 <= df[c].nunique() <= 8:
                    chosen_col = c
                    break
        if chosen_col:
            sub_banner_names = sorted([str(x) for x in df[chosen_col].dropna().unique()])
            col_masks = [df[chosen_col].astype(str) == v for v in sub_banner_names]

    col_letters = ["Total"] + [get_column_letter(i) for i in range(1, len(sub_banner_names) + 1)]
    banner_cols_display = ["Total"] + [f"{name} ({col_letters[i]})" for i, name in enumerate(sub_banner_names, start=1)]

    # 3. Compute Sample Bases per Column
    all_col_masks = [pd.Series(True, index=df.index)] + col_masks
    unweighted_bases = []
    weighted_bases = []
    effective_bases = []

    for mask in all_col_masks:
        valid = mask & df[stub_col].notna()
        n_col = int(valid.sum())
        w_sub = w_all[valid.to_numpy()]
        nw_col = float(w_sub.sum()) if n_col > 0 else 0.0
        neff_col = calculate_kish_neff(w_sub) if n_col > 0 else 0.0

        unweighted_bases.append(n_col)
        weighted_bases.append(round(nw_col, 1))
        effective_bases.append(round(neff_col, 1))

    # CS-018: Small base flag (< 30)
    small_base = [bool(ne < 30.0) for ne in effective_bases]

    # 4. Extract Stub Response Options & Detect Type
    stub_series = df[stub_col].dropna()
    is_numeric = pd.to_numeric(stub_series, errors='coerce').notna().all()
    num_uniques = stub_series.nunique()
    missing_codes = {97, 98, 99}

    # Detect rating scale boundaries (P3-03)
    m_scale = re.search(r'_(\d+)to(\d+)$', stub_col, re.IGNORECASE)
    is_rating_scale = False
    scale_lo, scale_hi = 1, 5
    if m_scale:
        scale_lo, scale_hi = int(m_scale.group(1)), int(m_scale.group(2))
        is_rating_scale = True
    elif is_numeric and num_uniques <= 11:
        numeric_vals_all = sorted([float(x) for x in stub_series.unique()])
        non_missing = [v for v in numeric_vals_all if v not in missing_codes]
        if non_missing and (min(non_missing) in (0, 1)) and (max(non_missing) in (4, 5, 6, 7, 10)):
            scale_lo = int(min(non_missing))
            scale_hi = int(max(non_missing))
            is_rating_scale = True

    # Check if multi-select checkboxes (commas separating options)
    has_commas = stub_series.astype(str).str.contains(', ', regex=False).mean() > 0.10

    row_definitions = []

    if has_commas:
        # P3-07, CS-019: Whole-option matching via indicator resolution
        from engine.ingestion import resolve_google_forms_checkboxes
        ind_df, _ = resolve_google_forms_checkboxes(df[stub_col])
        # Sort options by prevalence descending
        sorted_opts = ind_df.sum().sort_values(ascending=False).index.tolist()

        for opt in sorted_opts:
            row_definitions.append({
                "label": opt,
                "is_net": False,
                "evaluator": lambda s, opt=opt: ind_df.loc[s.index, opt].astype(bool)
            })

    elif is_rating_scale:
        # P3-03: Strict scale-based Top-2-Box and exclude missing codes
        top2 = [float(scale_hi), float(scale_hi - 1)]
        row_definitions.append({
            "label": f"NET: Top-2-Box ({scale_hi-1}-{scale_hi})",
            "is_net": True,
            "evaluator": lambda s, t2=top2: s.astype(float).isin(t2)
        })
        for v in range(scale_hi, scale_lo - 1, -1):
            row_definitions.append({
                "label": f"{v} - Rating",
                "is_net": False,
                "evaluator": lambda s, v=float(v): s.astype(float) == v
            })
        # If missing codes are present, display them as distinct categories
        pres_missing = sorted(list(set(stub_series.astype(float)).intersection(missing_codes)))
        for mc in pres_missing:
            row_definitions.append({
                "label": f"{int(mc)} - Don't know / Refused",
                "is_net": False,
                "is_missing_row": True,
                "evaluator": lambda s, mc=mc: s.astype(float) == mc
            })

    else:
        # Categorical single-select (P3-12: handle capping with Other category)
        cat_counts = stub_series.value_counts()
        MAX_CATS = 12
        if len(cat_counts) > MAX_CATS:
            shown_cats = cat_counts.index[:MAX_CATS]
            rest_cats = cat_counts.index[MAX_CATS:]
            for cat_val in shown_cats:
                row_definitions.append({
                    "label": str(cat_val),
                    "is_net": False,
                    "evaluator": lambda s, cat_val=cat_val: s.astype(str) == str(cat_val)
                })
            row_definitions.append({
                "label": f"Other ({len(rest_cats)} categories)",
                "is_net": False,
                "evaluator": lambda s, r_set=set(map(str, rest_cats)): s.astype(str).isin(r_set)
            })
        else:
            for cat_val in cat_counts.index:
                row_definitions.append({
                    "label": str(cat_val),
                    "is_net": False,
                    "evaluator": lambda s, cat_val=cat_val: s.astype(str) == str(cat_val)
                })

    # If metric is "mean" and variable is numeric, add Mean Rating row (P3-02)
    if metric == "mean" and (is_numeric or is_rating_scale):
        row_definitions = [{
            "label": f"Mean {stub_col}",
            "is_net": True,
            "is_mean": True,
            "evaluator": None
        }]
    elif metric == "t2b":
        # P3-26: Filter to NET rows only when metric is t2b
        row_definitions = [r for r in row_definitions if r.get("is_net")]

    # 5. Compute Proportions, Means, and Dual Significance Testing
    alpha_hi = 1.0 - confidence_level if confidence_level > 0.5 else 0.05
    num_banners = len(sub_banner_names)
    computed_rows = []

    for r_idx, r_def in enumerate(row_definitions):
        is_mean_row = r_def.get("is_mean", False)

        row_vals_str = []
        row_vals_num = []
        col_sds = []
        row_benchmarks = ["-"]

        # Calculate values per column
        for c_idx, mask in enumerate(all_col_masks):
            valid = mask & df[stub_col].notna()
            if is_rating_scale and not r_def.get("is_missing_row"):
                valid = valid & ~pd.to_numeric(df[stub_col], errors='coerce').isin(missing_codes)
            w_sub = w_all[valid.to_numpy()]
            w_sum = w_sub.sum()

            if is_mean_row:
                vals_numeric = df.loc[valid, stub_col].astype(float).to_numpy()
                # Exclude missing codes from mean calculation (P3-03)
                non_miss = ~np.isin(vals_numeric, list(missing_codes))
                vals_clean = vals_numeric[non_miss]
                w_clean = w_sub[non_miss]
                w_clean_sum = w_clean.sum()

                if len(vals_clean) > 0 and w_clean_sum > 0:
                    mean_val = float(np.average(vals_clean, weights=w_clean))
                    var_val = float(np.average((vals_clean - mean_val) ** 2, weights=w_clean) * (len(vals_clean) / (len(vals_clean) - 1))) if len(vals_clean) > 1 else 0.0
                    sd_val = math.sqrt(max(0.0, var_val))
                else:
                    mean_val = 0.0
                    sd_val = 0.0

                row_vals_num.append(mean_val)
                col_sds.append(sd_val)
                row_vals_str.append(f"{mean_val:.2f}")

            else:
                evaluator = r_def["evaluator"]
                matches = evaluator(df.loc[valid, stub_col]).to_numpy()
                matched_w = w_sub[matches].sum() if len(w_sub) > 0 else 0.0
                prop = float(matched_w / w_sum) if w_sum > 0 else 0.0
                row_vals_num.append(prop)
                row_vals_str.append(f"{prop * 100.0:.1f}%")

        # Benchmark vs. Total
        for j in range(1, num_banners + 1):
            if is_mean_row:
                # vs rest for means (P4-08)
                mask_col = all_col_masks[j]
                valid_col = mask_col & df[stub_col].notna()
                valid_rest = ~mask_col & df[stub_col].notna()

                vals_col = df.loc[valid_col, stub_col].astype(float).to_numpy()
                vals_col = vals_col[~np.isin(vals_col, list(missing_codes))]
                w_c = w_all[valid_col.to_numpy()][~np.isin(df.loc[valid_col, stub_col].astype(float).to_numpy(), list(missing_codes))]

                vals_rest = df.loc[valid_rest, stub_col].astype(float).to_numpy()
                vals_rest = vals_rest[~np.isin(vals_rest, list(missing_codes))]
                w_r = w_all[valid_rest.to_numpy()][~np.isin(df.loc[valid_rest, stub_col].astype(float).to_numpy(), list(missing_codes))]

                if len(vals_col) > 1 and len(vals_rest) > 1 and w_c.sum() > 0 and w_r.sum() > 0:
                    m_c = float(np.average(vals_col, weights=w_c))
                    v_c = float(np.average((vals_col - m_c)**2, weights=w_c) * len(vals_col)/(len(vals_col)-1))
                    sd_c = math.sqrt(max(0.0, v_c))
                    neff_c = calculate_kish_neff(w_c)

                    m_r = float(np.average(vals_rest, weights=w_r))
                    v_r = float(np.average((vals_rest - m_r)**2, weights=w_r) * len(vals_rest)/(len(vals_rest)-1))
                    sd_r = math.sqrt(max(0.0, v_r))
                    neff_r = calculate_kish_neff(w_r)

                    t_val, p_val, is_sm = test_means_significance(m_c, sd_c, neff_c, m_r, sd_r, neff_r)
                    if is_sm:
                        bm_marker = ""
                    elif p_val < 0.05 and t_val > 0:
                        bm_marker = "++"
                    elif p_val < 0.10 and t_val > 0:
                        bm_marker = "+"
                    elif p_val < 0.05 and t_val < 0:
                        bm_marker = "--"
                    elif p_val < 0.10 and t_val < 0:
                        bm_marker = "-"
                    else:
                        bm_marker = ""
                else:
                    bm_marker = ""
            else:
                pj = row_vals_num[j]
                p_tot = row_vals_num[0]
                nj = unweighted_bases[j]
                ntot = unweighted_bases[0]
                neff_j = effective_bases[j]
                neff_tot = effective_bases[0]

                bm_marker = test_vs_total_benchmark(
                    p_col=pj,
                    p_total=p_tot,
                    n_col=nj,
                    n_total=ntot,
                    neff_col=neff_j,
                    neff_total=neff_tot
                )
            row_benchmarks.append(bm_marker)

        # Pairwise column comparison letters (P3-01, P3-02)
        pairs = []
        pvals = []

        for j in range(1, num_banners + 1):
            for m in range(j + 1, num_banners + 1):
                neff_j = effective_bases[j]
                neff_m = effective_bases[m]

                if is_mean_row:
                    t_stat, p_val, is_small = test_means_significance(
                        float(row_vals_num[j]),
                        float(col_sds[j]),
                        float(neff_j),
                        float(row_vals_num[m]),
                        float(col_sds[m]),
                        float(neff_m)
                    )
                    z_dir = t_stat
                else:
                    pj = row_vals_num[j]
                    pm = row_vals_num[m]
                    z_val, p_val, is_small = test_pairwise_proportions(pj, pm, neff_j, neff_m)
                    z_dir = z_val

                pairs.append((j, m, z_dir, is_small))
                pvals.append(p_val)

        # Apply Benjamini-Hochberg FDR to the row's pairwise tests (P3-01)
        if fdr_enabled and len(pvals) > 0:
            adj_pvals = scipy.stats.false_discovery_control(pvals, method='bh')
        else:
            adj_pvals = pvals

        col_letters_won = {col_idx: [] for col_idx in range(1, num_banners + 1)}
        for (j, m, z_dir, is_small), pa in zip(pairs, adj_pvals):
            if is_small:
                continue
            hi, lo = (j, m) if z_dir > 0 else (m, j)
            target_let = col_letters[lo]
            if pa < alpha_hi:
                col_letters_won[hi].append(target_let.upper())
            elif pa < 0.10:
                col_letters_won[hi].append(target_let.lower())

        row_sig_letters = ["-"] + [" ".join(col_letters_won[j]) for j in range(1, num_banners + 1)]

        computed_rows.append({
            "label": r_def["label"],
            "values": row_vals_str,
            "sig_letters": row_sig_letters,
            "sig_benchmarks": row_benchmarks,
            "is_net": r_def.get("is_net", False)
        })

    # If mean row, calculate one-way ANOVA across banner groups (P3-02, P4-08)
    anova_info = None
    if metric == "mean" and (is_numeric or is_rating_scale) and num_banners >= 2:
        groups = []
        group_weights = []
        for c in range(1, num_banners + 1):
            valid_c = all_col_masks[c] & df[stub_col].notna()
            vals_c = df.loc[valid_c, stub_col].astype(float).to_numpy()
            non_miss = ~np.isin(vals_c, list(missing_codes))
            vals_c = vals_c[non_miss]
            w_c = w_all[valid_c.to_numpy()][non_miss]
            if len(vals_c) > 0:
                groups.append(vals_c)
                group_weights.append(w_c)
        if len(groups) >= 2:
            is_weighted_sample = any(not np.allclose(w, 1.0) for w in group_weights)
            if is_weighted_sample:
                all_vals = np.concatenate(groups)
                all_w = np.concatenate(group_weights)
                w_grand_mean = np.average(all_vals, weights=all_w)
                k_groups = len(groups)
                ss_between = sum(
                    w_i.sum() * (np.average(g_i, weights=w_i) - w_grand_mean) ** 2
                    for g_i, w_i in zip(groups, group_weights)
                )
                df1 = k_groups - 1
                ms_between = ss_between / df1 if df1 > 0 else 0.0

                ss_within = sum(
                    np.sum(w_i * (g_i - np.average(g_i, weights=w_i)) ** 2)
                    for g_i, w_i in zip(groups, group_weights)
                )
                df2 = sum(len(g) for g in groups) - k_groups
                ms_within = ss_within / df2 if df2 > 0 else 1.0
                f_stat = ms_between / ms_within if ms_within > 0 else 0.0
                f_p = float(scipy.stats.f.sf(f_stat, df1, df2))
                anova_info = {
                    "f_stat": float(round(f_stat, 4)),
                    "p_val": float(round(f_p, 4)),
                    "df1": df1,
                    "df2": df2,
                    "weighted": True
                }
            else:
                f_stat, f_p = scipy.stats.f_oneway(*groups)
                anova_info = {
                    "f_stat": float(round(f_stat, 4)),
                    "p_val": float(round(f_p, 4)),
                    "df1": len(groups) - 1,
                    "df2": sum(len(g) for g in groups) - len(groups),
                    "weighted": False
                }

    return {
        "title": f"Tabulation: {stub_col}",
        "stub_label": stub_col,
        "banner_cols": banner_cols_display,
        "clean_banner_cols": ["Total"] + sub_banner_names,
        "col_letters": col_letters,
        "unweighted_bases": unweighted_bases,
        "weighted_bases": weighted_bases,
        "effective_bases": effective_bases,
        "small_base": small_base,
        "anova": anova_info,
        "rows": computed_rows
    }
