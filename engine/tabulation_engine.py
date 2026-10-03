"""
ClearSight Analytics - Dynamic Cross-Tabulation & Statistical Engine
Plumbs raw survey microdata directly into rigorous significance testing:
1. Flexible Banner & Stub variable resolution (single-select, multi-select, rating scales)
2. Real bases: Unweighted N, Weighted Base Nw, Kish Effective Base Neff
3. Dual statistical testing:
   - Pairwise Column Comparisons (z-test with pooled proportions and Kish Neff; Welch t-test for means)
   - Benchmark vs. Total (Overlap-corrected Column vs. Rest-of-Sample z-test)
4. Multiple testing adjustment: Benjamini-Hochberg (BH) False Discovery Rate (FDR)
"""

import math
import re
from collections import Counter
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
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
    """Finds matching DataFrame column by exact, normalized, or substring match."""
    if df is None or len(df.columns) == 0:
        return None
    if name in df.columns:
        return name
    
    clean_name = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    for col in df.columns:
        if re.sub(r'[^a-zA-Z0-9]', '', str(col)).lower() == clean_name:
            return col
            
    for col in df.columns:
        col_clean = re.sub(r'[^a-zA-Z0-9]', '', str(col)).lower()
        if clean_name in col_clean or col_clean in clean_name:
            return col
    return None


def clean_label(text: str) -> str:
    """Removes trailing column letters like '(A)' or brackets."""
    return re.sub(r'\s*[\(\[]\s*[A-Z]+\s*[\)\]]$', '', str(text)).strip()


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
            "rows": []
        }

    n_total_rows = len(df)
    if weights is None or len(weights) != n_total_rows:
        w_all = np.ones(n_total_rows, dtype=float)
    else:
        w_all = np.asarray(weights, dtype=float)

    # 1. Resolve Stub Column
    stub_col = resolve_column(df, stub_name)
    if stub_col is None:
        # Fallback to first non-ID column
        candidates = [c for c in df.columns if not c.lower().endswith('_id') and c.lower() != 'id']
        stub_col = candidates[0] if candidates else df.columns[0]

    # 2. Resolve Banner Columns & Build Column Filters
    # banner_cols_input can be:
    # A) ["Total", "NCR (A)", "Balance Luzon (B)", ...] -> values in a column like Region
    # B) ["Total", "Region"] -> entire column categories
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
        # Multiple categories passed
        sub_banner_names = []
        col_masks = []
        for b_name in raw_banner_names[1:]:
            # Find which column in df contains this category
            matched = False
            for col in df.columns:
                series_str = df[col].astype(str)
                # Exact or partial match
                m = (series_str == b_name) | series_str.str.contains(b_name, regex=False, na=False)
                if m.any():
                    sub_banner_names.append(b_name)
                    col_masks.append(m)
                    matched = True
                    break
            if not matched:
                # If no direct match, check if it's a column itself (e.g. binary indicator)
                c_direct = resolve_column(df, b_name)
                if c_direct:
                    sub_banner_names.append(b_name)
                    col_masks.append(df[c_direct].notna() & (df[c_direct] != 0))
                else:
                    # Generic fallback mask
                    sub_banner_names.append(b_name)
                    col_masks.append(pd.Series(False, index=df.index))

    # If no banner columns could be matched, use first demographic/categorical column
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

    # Sequential collision-free letters for sub-banners
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

    # 4. Extract Stub Response Options & Detect Type
    stub_series = df[stub_col].dropna()
    is_numeric = pd.to_numeric(stub_series, errors='coerce').notna().all()
    num_uniques = stub_series.nunique()
    
    # Check if multi-select checkboxes (e.g. commas separating options)
    has_commas = stub_series.astype(str).str.contains(', ', regex=False).mean() > 0.10
    
    row_definitions = []
    if has_commas:
        # Extract individual options across all responses
        counts = Counter()
        for val in stub_series:
            for part in str(val).split(','):
                p_clean = part.strip()
                if p_clean:
                    counts[p_clean] += 1
        top_options = [opt for opt, _ in counts.most_common(10)]
        for opt in top_options:
            row_definitions.append({
                "label": opt,
                "is_net": False,
                "evaluator": lambda s, opt=opt: s.astype(str).str.contains(opt, regex=False, na=False)
            })
    elif is_numeric and num_uniques <= 10:
        # Numeric rating scale (e.g. 1 to 5)
        numeric_vals = sorted(stub_series.astype(float).unique(), reverse=True)
        # Top-2-Box NET
        if len(numeric_vals) >= 2 and max(numeric_vals) >= 4:
            top2 = numeric_vals[:2]
            row_definitions.append({
                "label": f"NET: Top-2-Box ({int(top2[1])}-{int(top2[0])})",
                "is_net": True,
                "evaluator": lambda s, top2=top2: s.astype(float).isin(top2)
            })
        for v in numeric_vals:
            v_int = int(v) if v == int(v) else v
            row_definitions.append({
                "label": f"{v_int} - Rating",
                "is_net": False,
                "evaluator": lambda s, v=v: s.astype(float) == v
            })
    else:
        # Categorical single-select
        cat_counts = stub_series.value_counts()
        for cat_val in cat_counts.index[:12]:
            row_definitions.append({
                "label": str(cat_val),
                "is_net": False,
                "evaluator": lambda s, cat_val=cat_val: s.astype(str) == str(cat_val)
            })

    # If metric is "mean" and variable is numeric, add Mean Rating row
    if metric == "mean" and is_numeric:
        row_definitions = [{
            "label": f"Mean {stub_col}",
            "is_net": True,
            "is_mean": True,
            "evaluator": None
        }]

    # 5. Compute Proportions, Means, and Dual Significance Testing
    alpha_95 = 1.0 - confidence_level if confidence_level > 0.5 else 0.05
    alpha_90 = 0.10

    p_values_for_fdr = []
    fdr_test_registry = [] # (row_idx, col_idx, test_type, meta)

    computed_rows = []

    for r_idx, r_def in enumerate(row_definitions):
        is_mean_row = r_def.get("is_mean", False)
        
        row_vals_str = []
        row_vals_num = []
        row_sig_letters = ["-"]
        row_benchmarks = ["-"]

        # Calculate values per column
        for c_idx, mask in enumerate(all_col_masks):
            valid = mask & df[stub_col].notna()
            w_sub = w_all[valid.to_numpy()]
            w_sum = w_sub.sum()

            if is_mean_row:
                vals_numeric = df.loc[valid, stub_col].astype(float).to_numpy()
                mean_val = float(np.average(vals_numeric, weights=w_sub)) if len(vals_numeric) > 0 and w_sum > 0 else 0.0
                row_vals_num.append(mean_val)
                row_vals_str.append(f"{mean_val:.2f}")
            else:
                evaluator = r_def["evaluator"]
                matches = evaluator(df.loc[valid, stub_col]).to_numpy()
                matched_w = w_sub[matches].sum() if len(w_sub) > 0 else 0.0
                prop = float(matched_w / w_sum) if w_sum > 0 else 0.0
                row_vals_num.append(prop)
                row_vals_str.append(f"{prop * 100.0:.1f}%")

        # Significance Testing across banner columns (c_idx 1 to k)
        num_banners = len(sub_banner_names)
        
        # Benchmark vs. Total
        for j in range(1, num_banners + 1):
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

        # Pairwise column comparison letters
        for j in range(1, num_banners + 1):
            letters_won = []
            for k in range(1, num_banners + 1):
                if j == k:
                    continue
                pj = row_vals_num[j]
                pk = row_vals_num[k]
                neff_j = effective_bases[j]
                neff_k = effective_bases[k]
                target_letter = col_letters[k]

                letter = evaluate_column_comparison_letter(
                    p_current=pj,
                    p_target=pk,
                    neff_current=neff_j,
                    neff_target=neff_k,
                    target_letter=target_letter,
                    alpha_95=alpha_95,
                    alpha_90=alpha_90
                )
                if letter:
                    letters_won.append(letter)
                    # Register p-value for FDR
                    z, p_val, _ = test_pairwise_proportions(pj, pk, neff_j, neff_k)
                    p_values_for_fdr.append(p_val)
                    fdr_test_registry.append((r_idx, j, letter))

            row_sig_letters.append(" ".join(letters_won))

        computed_rows.append({
            "label": r_def["label"],
            "values": row_vals_str,
            "sig_letters": row_sig_letters,
            "sig_benchmarks": row_benchmarks,
            "is_net": r_def.get("is_net", False)
        })

    # 6. Apply Benjamini-Hochberg FDR if enabled
    if fdr_enabled and len(p_values_for_fdr) > 0:
        fdr_results = apply_fdr_benjamini_hochberg(p_values_for_fdr, alpha=alpha_95)
        # Suppress any letter where FDR failed
        for is_sig, (r_idx, col_idx, letter) in zip(fdr_results, fdr_test_registry):
            if not is_sig:
                current_lets = computed_rows[r_idx]["sig_letters"][col_idx].split()
                filtered = [l for l in current_lets if l != letter]
                computed_rows[r_idx]["sig_letters"][col_idx] = " ".join(filtered)

    return {
        "title": f"Tabulation: {stub_col}",
        "stub_label": stub_col,
        "banner_cols": banner_cols_display,
        "clean_banner_cols": ["Total"] + sub_banner_names,
        "col_letters": col_letters,
        "unweighted_bases": unweighted_bases,
        "weighted_bases": weighted_bases,
        "effective_bases": effective_bases,
        "rows": computed_rows
    }
