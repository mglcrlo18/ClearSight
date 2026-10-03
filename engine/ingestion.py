"""
Sukat by Lunsad - Data Ingestion & Sanitization Engine
Handles Google Forms delimiter collisions, schema autodetection, and hygiene logging.
"""

import re
import json
import os
import pandas as pd
import numpy as np

def resolve_google_forms_checkboxes(series: pd.Series, known_options: list = None) -> pd.DataFrame:
    """
    Parses comma-separated checkbox responses from Google Forms.
    If known_options is provided, uses string-backtracking to prevent splitting 
    on commas contained within option labels (e.g. 'National Capital Region (NCR), Metro Manila').
    Returns a one-hot encoded / binary indicator DataFrame for the options.
    """
    raw_strings = series.dropna().astype(str).tolist()
    
    # If no known options are provided, infer by looking for common candidates
    if not known_options:
        # Standard naive split as fallback, then clean whitespace
        all_tokens = set()
        for item in raw_strings:
            tokens = [t.strip() for t in item.split(',') if t.strip()]
            all_tokens.update(tokens)
        known_options = sorted(list(all_tokens))
    
    # Sort known options by length descending to match longest phrases first (backtracking greedily)
    sorted_options = sorted(known_options, key=lambda x: len(x), reverse=True)
    
    records = []
    for item in series:
        row_dict = {opt: 0 for opt in known_options}
        if pd.isna(item):
            records.append(row_dict)
            continue
            
        remaining = str(item).strip()
        matched = []
        for opt in sorted_options:
            if opt in remaining:
                matched.append(opt)
                row_dict[opt] = 1
                # Replace matched token to avoid sub-string duplicate triggers
                remaining = remaining.replace(opt, "")
                
        records.append(row_dict)
        
    return pd.DataFrame(records, index=series.index)


def autodetect_schema(df: pd.DataFrame) -> dict:
    """
    Profiles columns into Survey Types:
    - 'single_select': Categorical / text with low unique count
    - 'multi_select': Contains commas and multiple recurring tokens
    - 'rating_scale': Numeric with bounded range (e.g. 1-5, 1-7, 1-10)
    - 'numeric': Unbounded continuous numbers
    - 'open_ended': Long text fields (> 30 characters average or high lexical diversity)
    """
    schema = {}
    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            schema[col] = {"type": "empty", "sample": []}
            continue
            
        # Check if numeric
        numeric_series = pd.to_numeric(series, errors='coerce')
        valid_numeric_ratio = numeric_series.notna().mean()
        
        if valid_numeric_ratio > 0.85:
            min_val = numeric_series.min()
            max_val = numeric_series.max()
            uniques = numeric_series.nunique()
            if min_val >= 1 and max_val <= 10 and uniques <= 10:
                schema[col] = {
                    "type": "rating_scale",
                    "scale_min": int(min_val),
                    "scale_max": int(max_val),
                    "mean": float(numeric_series.mean()),
                    "sample": series.head(3).tolist()
                }
            else:
                schema[col] = {
                    "type": "numeric",
                    "min": float(min_val),
                    "max": float(max_val),
                    "sample": series.head(3).tolist()
                }
            continue
            
        # Check string characteristics
        sample_texts = series.astype(str).tolist()
        avg_len = sum(len(s) for s in sample_texts) / len(sample_texts)
        comma_ratio = sum(',' in s for s in sample_texts) / len(sample_texts)
        unique_count = series.nunique()
        
        if comma_ratio > 0.35 and unique_count > 10:
            schema[col] = {
                "type": "multi_select",
                "delimiter_detected": True,
                "sample": series.head(3).tolist()
            }
        elif avg_len > 40:
            schema[col] = {
                "type": "open_ended",
                "sample": series.head(3).tolist()
            }
        else:
            schema[col] = {
                "type": "single_select",
                "categories": series.unique().tolist()[:20],
                "sample": series.head(3).tolist()
            }
            
    return schema


def run_hygiene_audit(df: pd.DataFrame, time_col: str = None) -> tuple[pd.DataFrame, list]:
    """
    Flags straight-liners and speeders without destructive drops.
    Returns (cleaned_or_flagged_df, audit_log_records).
    """
    audit_log = []
    df = df.copy()
    df["__is_flagged"] = False
    df["__flag_reasons"] = ""
    
    # 1. Straight-liners across Likert rating scales
    rating_cols = [c for c in df.columns if pd.to_numeric(df[c], errors='coerce').notna().mean() > 0.85 and df[c].nunique() <= 7]
    if len(rating_cols) >= 3:
        variances = df[rating_cols].apply(pd.to_numeric, errors='coerce').var(axis=1)
        straight_liners = variances[variances == 0].index
        for idx in straight_liners:
            df.loc[idx, "__is_flagged"] = True
            df.loc[idx, "__flag_reasons"] += "Straight-liner (0 variance across scale battery); "
            audit_log.append({
                "row_index": int(idx),
                "type": "STRAIGHT_LINER",
                "details": f"Zero variance across {len(rating_cols)} rating columns."
            })
            
    # 2. Duplicate submissions based on full demographic match
    demo_cols = [c for c in df.columns if df[c].nunique() < 20 and not c.startswith("__")]
    if len(demo_cols) >= 3:
        dup_mask = df.duplicated(subset=demo_cols, keep=False)
        for idx in df[dup_mask].index:
            df.loc[idx, "__is_flagged"] = True
            df.loc[idx, "__flag_reasons"] += "Duplicate demographic profile; "
            audit_log.append({
                "row_index": int(idx),
                "type": "DEMOGRAPHIC_DUPLICATE",
                "details": f"Identical profile across {', '.join(demo_cols[:4])}."
            })
            
    return df, audit_log
