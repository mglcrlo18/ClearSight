"""
ClearSight Analytics - Survey Data Ingestion & Hygiene Engine
Supports:
1. Multi-Format Ingestion: CSV, Excel (.xlsx/.xls), and SPSS (.sav) with metadata preservation
2. Google Forms Checkbox & Comma-Delimiter Collision Resolution
3. Survey Schema Autodetection (IDs, Datetime, Rating batteries, Single/Multi-select, Categorical)
4. Survey Hygiene Auditing (Straight-liners, Speeders, Invalid Durations, Duplicate IDs, Demographic Duplicates)
5. Audit logging in ~/.clearsight/cleaning_audit_trail.log
"""

import io
import os
import re
import datetime
from pathlib import Path
from typing import Optional, Union, Tuple
import numpy as np
import pandas as pd

try:
    import pyreadstat
    HAS_PYREADSTAT = True
except ImportError:
    HAS_PYREADSTAT = False


# App Data Directory for Persistent Audit Trail (CS-066, CS-087)
LOG_DIR = Path(os.environ.get('CLEARSIGHT_DATA', Path.home() / '.clearsight'))
LOG_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LOG_FILEPATH = str(LOG_DIR / "cleaning_audit_trail.log")


# ---------------------------------------------------------------------------
# 1. Multi-Format Survey Ingestion (CSV, Excel, SPSS .sav)
# ---------------------------------------------------------------------------

def read_survey_file(file_bytes: bytes, filename: str) -> tuple[pd.DataFrame, dict]:
    """
    Reads survey data from raw bytes supporting:
    - CSV (.csv): with automatic encoding fallback, preserving leading zeros (P3-20)
    - Excel (.xlsx, .xls): via openpyxl/xlrd, preserving leading zeros
    - SPSS (.sav): via pyreadstat with value labels applied and user-missing mapping to NaN (CS-003)
    Returns (df, metadata_dict).
    """
    ext = Path(filename).suffix.lower()
    metadata = {
        "filename": filename,
        "format": ext,
        "variable_labels": {},
        "value_labels": {}
    }

    if ext == ".csv":
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        df = None
        for enc in encodings:
            try:
                # P3-20: Read as string first to preserve leading zeros in codes/stubs
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, dtype=str, keep_default_na=False, na_values=[''])
                metadata["encoding"] = enc
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        if df is None:
            raise ValueError(f"Could not parse CSV file '{filename}' with supported encodings.")

    elif ext in [".xlsx", ".xls"]:
        # P3-20: Read as string first to preserve leading zeros
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
        metadata["encoding"] = "binary"

    elif ext == ".sav":
        if HAS_PYREADSTAT:
            # CS-003: Read with apply_value_formats=False and map missing ranges to NaN
            df, meta = pyreadstat.read_sav(
                io.BytesIO(file_bytes),
                apply_value_formats=False,
                user_missing=True
            )
            # Map declared missing ranges to NaN
            missing_ranges = getattr(meta, "missing_ranges", None) or {}
            for col, rng_list in missing_ranges.items():
                if col in df.columns:
                    for rng in rng_list:
                        lo = rng.get("lo", float("-inf"))
                        hi = rng.get("hi", float("inf"))
                        df.loc[df[col].between(lo, hi), col] = np.nan

            var_val_labels = getattr(meta, "variable_value_labels", {}) or {}
            for col, labels in var_val_labels.items():
                if col in df.columns and not re.search(r'_(\d+)to(\d+)$', col, re.IGNORECASE):
                    df[col] = df[col].map(lambda v: labels.get(v, v) if pd.notna(v) else v)

            metadata["variable_labels"] = getattr(meta, "column_names_to_labels", {}) or getattr(meta, "variable_to_label", {}) or {}
            metadata["value_labels"] = var_val_labels
        else:
            raise ImportError(
                "SPSS (.sav) file reading requires the 'pyreadstat' package. "
                "Please install pyreadstat or upload data in CSV or Excel (.xlsx) format."
            )
    else:
        raise ValueError(f"Unsupported file format '{ext}'. ClearSight supports .csv, .xlsx, .xls, and .sav.")

    # P3-20: Convert purely numeric columns without leading zeros to numeric
    if ext in [".csv", ".xlsx", ".xls"]:
        for c in df.columns:
            s = df[c].dropna()
            # Do not convert if column has numbers with leading zero (e.g. '0042')
            has_leading_zero = s.astype(str).str.match(r'^0\d+').any()
            if len(s) > 0 and not has_leading_zero:
                conv = pd.to_numeric(s, errors='coerce')
                if conv.notna().all():
                    df[c] = pd.to_numeric(df[c])

    return df, metadata


# ---------------------------------------------------------------------------
# 2. Google Forms Checkbox Resolution with Boundary Tokenization
# ---------------------------------------------------------------------------

def resolve_google_forms_checkboxes(series: pd.Series, known_options: list = None) -> tuple[pd.DataFrame, pd.Series]:
    """
    Parses comma-separated checkbox responses from Google Forms with boundary awareness.
    Prevents splitting on commas embedded inside option labels (e.g. 'National Capital Region (NCR), Metro Manila').
    Extracts 'Other (specify)' free-text if present.
    Returns (binary_indicator_df, other_text_series).
    """
    raw_strings = series.dropna().astype(str).tolist()

    if not known_options:
        token_counts = {}
        for item in raw_strings:
            parts = [p.strip() for p in item.split(",") if p.strip()]
            for p in parts:
                token_counts[p] = token_counts.get(p, 0) + 1
        known_options = [k for k, v in token_counts.items() if v >= 2 or len(raw_strings) < 10]

    clean_options = [opt.strip() for opt in known_options if opt.strip()]
    sorted_options = sorted(clean_options, key=len, reverse=True)

    records = []
    other_texts = []

    for item in series:
        row_dict = {opt: 0 for opt in clean_options}
        if pd.isna(item):
            records.append(row_dict)
            other_texts.append("")
            continue

        text = str(item).strip()
        other_part = ""

        for opt in sorted_options:
            escaped_opt = re.escape(opt)
            pattern = rf"(?:^|,\s*){escaped_opt}(?:\s*,|$)"
            if re.search(pattern, text):
                row_dict[opt] = 1
                text = re.sub(pattern, ", ", text).strip(", ")

        if text and text != ",":
            cleaned_other = re.sub(r"^Other:\s*", "", text).strip(", ")
            if cleaned_other:
                other_part = cleaned_other

        records.append(row_dict)
        other_texts.append(other_part)

    df_indicators = pd.DataFrame(records, index=series.index)
    series_other = pd.Series(other_texts, index=series.index, name=f"{series.name}_other_text")

    return df_indicators, series_other


# ---------------------------------------------------------------------------
# 3. Survey Schema Autodetection (P3-23, CS-061)
# ---------------------------------------------------------------------------

def autodetect_schema(df: pd.DataFrame) -> dict:
    """
    Profiles columns into validated survey data types:
    - 'id': Respondent ID or row index
    - 'datetime': Timestamp
    - 'binary': 0/1 binary indicator
    - 'rating_scale': Bounded numeric matrix questions (1-5, 1-7, 0-10 NPS)
    - 'open_ended': Long text verbatims or qualitative feedback
    - 'multi_select': Delimiter-separated selections
    - 'single_select': Categorical / discrete response
    - 'numeric': Continuous numeric (counts, wait hours, age)
    """
    schema = {}
    for col in df.columns:
        if str(col).startswith("__"):
            continue

        series = df[col].dropna()
        if len(series) == 0:
            schema[col] = {"type": "empty", "sample": []}
            continue

        sample_vals = [str(x)[:60] for x in series.head(3).tolist()]
        str_series = series.astype(str).str.strip()

        # 1. ID Column detection (P3-23)
        if (str_series.nunique() / len(str_series) > 0.95 and re.search(r'(?i)(?:respondent|resp)?_?id$|^id$|_no$', str(col))) or re.search(r'(?i)^row_?no$', str(col)):
            schema[col] = {"type": "id", "sample": sample_vals}
            continue

        # 2. Datetime detection (P3-23)
        try:
            if not pd.to_numeric(series, errors='coerce').notna().all():
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    dt_conv = pd.to_datetime(series, errors='coerce', format='mixed')
                if dt_conv.notna().mean() > 0.85:
                    schema[col] = {"type": "datetime", "sample": sample_vals}
                    continue
        except Exception:
            pass

        # 3. Numeric & Rating Scales
        numeric_series = pd.to_numeric(series, errors='coerce')
        valid_numeric_ratio = numeric_series.notna().mean()

        if valid_numeric_ratio > 0.85:
            # Check for binary 0/1
            num_set = set(numeric_series.dropna().unique())
            if num_set <= {0, 1} or num_set <= {0.0, 1.0}:
                schema[col] = {"type": "binary", "sample": sample_vals}
                continue

            min_val = float(numeric_series.min())
            max_val = float(numeric_series.max())
            uniques = int(numeric_series.nunique())

            # Bounded rating batteries (explicit naming _1to5, _0to10, _1to7 or battery pattern)
            m_scale_name = re.search(r'_(\d+)to(\d+)$', str(col), re.IGNORECASE)
            is_explicit_rating = bool(m_scale_name)

            if is_explicit_rating:
                lo_b = int(m_scale_name.group(1))
                hi_b = int(m_scale_name.group(2))
                schema[col] = {
                    "type": "rating_scale",
                    "scale_min": lo_b,
                    "scale_max": hi_b,
                    "mean": float(round(numeric_series.mean(), 2)),
                    "sample": sample_vals
                }
            elif any(k in str(col).lower() for k in ["sat_", "_sat", "satisfaction", "rating", "nps", "likert"]) and 0.0 <= min_val <= 3.0 and max_val in [4.0, 5.0, 6.0, 7.0, 10.0]:
                s_max = 5 if max_val <= 5.0 else (7 if max_val <= 7.0 else 10)
                s_min = 0 if (min_val == 0.0 or "nps" in str(col).lower()) else 1
                schema[col] = {
                    "type": "rating_scale",
                    "scale_min": s_min,
                    "scale_max": s_max,
                    "mean": float(round(numeric_series.mean(), 2)),
                    "sample": sample_vals
                }
            elif (series.astype(str).str.match(r'^0\d+$').mean() > 0.3 or re.search(r'(?i)_(?:code|stub|no)$', str(col))) and uniques <= 500:
                schema[col] = {
                    "type": "single_select",
                    "categories": [str(x) for x in series.unique()[:20]],
                    "sample": sample_vals
                }
            else:
                schema[col] = {
                    "type": "numeric",
                    "min": min_val,
                    "max": max_val,
                    "sample": sample_vals
                }
            continue

        # 4. Multi-select vs Open-ended vs Single-select (P4-02, P3-23)
        # Check comma not followed by 3 digits to ignore money formats like '10,000'
        has_comma_delim = str_series.str.contains(r',\s*(?!\d{3}\b)', regex=True).mean() > 0.20
        avg_len = float(str_series.str.len().mean())
        unique_ratio = float(str_series.nunique() / max(1, len(str_series)))
        parts = str_series.str.split(r',\s*').explode().str.strip()
        token_reuse = float(parts.value_counts().head(30).sum() / max(1, len(parts)))

        # P4-02: Open-ended free text detection BEFORE multi-select
        is_open_text = (
            (avg_len > 45 and (unique_ratio > 0.50 or token_reuse < 0.60)) or
            (avg_len > 20 and unique_ratio > 0.70 and token_reuse < 0.50) or
            any(k in str(col).lower() for k in ["open", "feedback", "comment", "verbatim", "_other"])
        )
        if is_open_text:
            schema[col] = {
                "type": "open_ended",
                "avg_char_length": round(avg_len, 1),
                "sample": sample_vals
            }
        elif has_comma_delim and token_reuse >= 0.50:
            schema[col] = {
                "type": "multi_select",
                "delimiter_detected": ",",
                "sample": sample_vals
            }
        else:
            schema[col] = {
                "type": "single_select",
                "categories": [str(x) for x in str_series.unique()[:20]],
                "sample": sample_vals
            }

    return schema


# ---------------------------------------------------------------------------
# 4. Data Hygiene Audit & Immutable Logging (P3-21, P3-22, CS-064, CS-065, CS-066)
# ---------------------------------------------------------------------------

def run_hygiene_audit(
    df: pd.DataFrame, 
    time_col: str = None, 
    rating_cols: list = None,
    log_filepath: str = None
) -> tuple[pd.DataFrame, list]:
    """
    Identifies straight-liners, speeders, invalid durations, duplicate IDs, and demographic duplicates.
    Writes audit records to persistent app-data log path (~/.clearsight/cleaning_audit_trail.log).
    Returns (annotated_df, audit_log_records).
    """
    audit_log = []
    df = df.copy()
    if log_filepath is None:
        log_filepath = DEFAULT_LOG_FILEPATH

    # Initialize helper columns
    df["__is_flagged"] = False
    df["__flag_reasons"] = ""

    # 1. Duplicate Respondent ID Check (P3-21)
    id_cols = [c for c in df.columns if re.search(r'(?i)(?:respondent|resp)?_?id$|^id$', str(c)) and not str(c).startswith("__")]
    if id_cols:
        id_col = id_cols[0]
        id_keys = df[id_col].astype(str).str.strip().str.upper()
        dup_ids = id_keys.duplicated(keep=False)
        for idx in df.index[dup_ids]:
            df.loc[idx, "__is_flagged"] = True
            df.loc[idx, "__flag_reasons"] += f"Duplicate Respondent ID: {id_keys.loc[idx]}; "
            audit_log.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "row_index": int(idx),
                "type": "DUPLICATE_ID",
                "details": f"Respondent ID '{id_keys.loc[idx]}' appears multiple times in dataset."
            })

    # 2. Straight-Liner Detection across Likert Rating Battery (CS-064)
    if not rating_cols:
        from collections import Counter
        temp_schema = autodetect_schema(df)
        scales = [(v.get('scale_min'), v.get('scale_max')) for c, v in temp_schema.items() if v.get('type') == 'rating_scale']
        if scales:
            most_common = Counter(scales).most_common(1)[0][0]
            rating_cols = [c for c, v in temp_schema.items() if v.get('type') == 'rating_scale' and (v.get('scale_min'), v.get('scale_max')) == most_common]
        else:
            rating_cols = [
                c for c in df.columns 
                if not str(c).startswith("__")
                and re.search(r'_(?:[01]to[57]|sat|rating)', str(c), re.IGNORECASE)
            ]

    if len(rating_cols) >= 3:
        sub_df = df[rating_cols].apply(pd.to_numeric, errors='coerce')
        variances = sub_df.var(axis=1)
        straight_liners = variances[variances == 0.0].index
        for idx in straight_liners:
            df.loc[idx, "__is_flagged"] = True
            df.loc[idx, "__flag_reasons"] += "Straight-liner (zero variance across Likert battery); "
            audit_log.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "row_index": int(idx),
                "type": "STRAIGHT_LINER",
                "details": f"Zero variance across {len(rating_cols)} rating columns: {', '.join(rating_cols[:4])}."
            })

    # 3. Speeder & Invalid Duration Detection (P3-22)
    if not time_col:
        for c in df.columns:
            lower = str(c).lower()
            if any(k in lower for k in ["duration", "elapsed", "completion_time", "time_taken", "survey_time"]):
                time_col = c
                break

    if time_col and time_col in df.columns:
        durations = pd.to_numeric(df[time_col], errors='coerce')

        # Flag non-positive durations as INVALID_DURATION (P3-22)
        invalid_mask = durations.isna() | (durations <= 0)
        for idx in durations.index[invalid_mask]:
            df.loc[idx, "__is_flagged"] = True
            df.loc[idx, "__flag_reasons"] += f"Invalid survey duration ({durations.loc[idx]}); "
            audit_log.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "row_index": int(idx),
                "type": "INVALID_DURATION",
                "details": f"Survey duration is non-positive or missing: {durations.loc[idx]}"
            })

        valid_durations = durations[durations > 0]
        if len(valid_durations) > 0:
            median_time = float(valid_durations.median())
            speeder_threshold = median_time / 3.0
            speeder_indices = durations[(durations > 0) & (durations < speeder_threshold)].index
            for idx in speeder_indices:
                df.loc[idx, "__is_flagged"] = True
                df.loc[idx, "__flag_reasons"] += f"Speeder (duration {durations.loc[idx]:.1f}s < 1/3 median {median_time:.1f}s); "
                audit_log.append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "row_index": int(idx),
                    "type": "SPEEDER",
                    "details": f"Duration {durations.loc[idx]:.1f}s is below 1/3 median threshold ({speeder_threshold:.1f}s)."
                })

    # 4. Duplicate Record Check across substantive columns (CS-065)
    temp_schema = autodetect_schema(df)
    sub_cols = [
        c for c, v in temp_schema.items() 
        if v.get('type') not in ('id', 'datetime', 'empty') 
        and not str(c).startswith('__') 
        and not any(k in str(c).lower() for k in ['duration', 'elapsed', 'time_taken', 'survey_time'])
    ]
    if len(sub_cols) >= 4:
        dup_mask = df.duplicated(subset=sub_cols, keep=False)
        for idx in df[dup_mask].index:
            df.loc[idx, "__is_flagged"] = True
            df.loc[idx, "__flag_reasons"] += "Duplicate response record; "
            audit_log.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "row_index": int(idx),
                "type": "DUPLICATE_RECORD",
                "details": f"Identical substantive responses across {len(sub_cols)} columns."
            })

    # 5. Write Immutable Audit Trail Log (CS-066, CS-087, P4-11)
    if log_filepath:
        try:
            # Rotate if log exceeds 5MB (P4-11)
            p = Path(log_filepath)
            if p.exists() and p.stat().st_size > 5_000_000:
                backup = p.with_suffix('.log.1')
                if backup.exists():
                    try:
                        backup.unlink()
                    except Exception:
                        pass
                p.rename(backup)

            with open(log_filepath, "a", encoding="utf-8") as f:
                f.write(f"\n--- CLEARSIGHT HYGIENE AUDIT: {datetime.datetime.now().isoformat()} ---\n")
                f.write(f"Evaluated rows: {len(df)} | Total flagged: {int(df['__is_flagged'].sum())}\n")
                for entry in audit_log:
                    f.write(f"[{entry['timestamp']}] Row {entry['row_index']} | {entry['type']} | {entry['details']}\n")
        except Exception:
            pass

    return df, audit_log
