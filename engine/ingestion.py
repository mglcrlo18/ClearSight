"""
ClearSight Analytics - Data Ingestion & Hygiene Engine
Handles multi-format reading (CSV, Excel, SPSS), Google Forms delimiter resolution,
schema profiling, and immutable hygiene auditing.
"""

import io
import re
import datetime
from pathlib import Path
import pandas as pd
import numpy as np

try:
    import pyreadstat
    HAS_PYREADSTAT = True
except ImportError:
    HAS_PYREADSTAT = False


# ---------------------------------------------------------------------------
# 1. Multi-Format Survey Ingestion (CSV, Excel, SPSS .sav)
# ---------------------------------------------------------------------------

def read_survey_file(file_bytes: bytes, filename: str) -> tuple[pd.DataFrame, dict]:
    """
    Reads survey data from raw bytes supporting:
    - CSV (.csv): with automatic encoding fallback (utf-8, utf-8-sig, latin-1, cp1252)
    - Excel (.xlsx, .xls): via openpyxl/xlrd
    - SPSS (.sav): via pyreadstat with value labels applied and user-missing mapping
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
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
                metadata["encoding"] = enc
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        if df is None:
            raise ValueError(f"Could not parse CSV file '{filename}' with supported encodings.")

    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(io.BytesIO(file_bytes))
        metadata["encoding"] = "binary"

    elif ext == ".sav":
        if HAS_PYREADSTAT:
            # Use pyreadstat to read SAV and apply value formats
            df, meta = pyreadstat.read_sav(
                io.BytesIO(file_bytes),
                apply_value_formats=True,
                user_missing=True
            )
            metadata["variable_labels"] = getattr(meta, "column_names_to_labels", {}) or getattr(meta, "variable_to_label", {}) or {}
            metadata["value_labels"] = getattr(meta, "variable_value_labels", {}) or {}
        else:
            raise ImportError(
                "SPSS (.sav) file reading requires the 'pyreadstat' package. "
                "Please install pyreadstat or upload data in CSV or Excel (.xlsx) format."
            )
    else:
        raise ValueError(f"Unsupported file format '{ext}'. ClearSight supports .csv, .xlsx, .xls, and .sav.")

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
        # Build candidate frequency map of comma-delimited tokens
        token_counts = {}
        for item in raw_strings:
            parts = [p.strip() for p in item.split(",") if p.strip()]
            for p in parts:
                token_counts[p] = token_counts.get(p, 0) + 1
        # Options appearing in at least 2 respondents or unique if small sample
        known_options = [k for k, v in token_counts.items() if v >= 2 or len(raw_strings) < 10]

    # Clean whitespace and sort by length descending (greedy longest-match first)
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

        # Match known options using boundary-aware regex to prevent substring collisions
        for opt in sorted_options:
            escaped_opt = re.escape(opt)
            # Match opt as a distinct segment bounded by commas or string ends
            pattern = rf"(?:^|,\s*){escaped_opt}(?:\s*,|$)"
            if re.search(pattern, text):
                row_dict[opt] = 1
                # Remove matched token
                text = re.sub(pattern, ", ", text).strip(", ")

        # If any unmatched text remains (e.g. "Other: customized answer")
        if text:
            other_part = text.strip()

        records.append(row_dict)
        other_texts.append(other_part)

    indicator_df = pd.DataFrame(records, index=series.index)
    other_series = pd.Series(other_texts, index=series.index, name=f"{series.name}_other")
    return indicator_df, other_series


# ---------------------------------------------------------------------------
# 3. Survey Schema Autodetection
# ---------------------------------------------------------------------------

def autodetect_schema(df: pd.DataFrame) -> dict:
    """
    Profiles columns into validated survey data types:
    - 'rating_scale': Bounded numeric matrix questions (1-5, 1-7, 0-10 NPS)
    - 'open_ended': Long text verbatims or high lexical diversity
    - 'multi_select': Delimiter-separated selections
    - 'single_select': Categorical / discrete response
    - 'numeric': Continuous numeric
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

        # 1. Check numeric / rating scales
        numeric_series = pd.to_numeric(series, errors='coerce')
        valid_numeric_ratio = numeric_series.notna().mean()

        if valid_numeric_ratio > 0.85:
            min_val = float(numeric_series.min())
            max_val = float(numeric_series.max())
            uniques = int(numeric_series.nunique())

            # Bounded rating batteries (1-5 Likert, 1-7, or 0-10 NPS)
            if (min_val in [0.0, 1.0] and max_val in [5.0, 7.0, 10.0]) or (uniques <= 10 and max_val <= 10.0 and min_val >= 0.0):
                schema[col] = {
                    "type": "rating_scale",
                    "scale_min": int(min_val),
                    "scale_max": int(max_val),
                    "mean": float(round(numeric_series.mean(), 2)),
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

        # 2. String Analysis: Open-ended vs. Multi-select vs. Single-select
        str_series = series.astype(str).str.strip()
        avg_len = float(str_series.str.len().mean())
        comma_ratio = float((str_series.str.contains(",", regex=False)).mean())
        unique_ratio = float(str_series.nunique() / max(1, len(str_series)))

        # High average length or high uniqueness indicates qualitative open-ends
        if avg_len > 45 or (avg_len > 25 and unique_ratio > 0.70):
            schema[col] = {
                "type": "open_ended",
                "avg_char_length": round(avg_len, 1),
                "sample": sample_vals
            }
        elif comma_ratio > 0.25:
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
# 4. Data Hygiene Audit & Immutable Logging
# ---------------------------------------------------------------------------

def run_hygiene_audit(
    df: pd.DataFrame, 
    time_col: str = None, 
    rating_cols: list = None,
    log_filepath: str = "cleaning_audit_trail.log"
) -> tuple[pd.DataFrame, list]:
    """
    Identifies straight-liners and speeders without destructive deletion.
    Writes audit records to cleaning_audit_trail.log.
    Returns (annotated_df, audit_log_records).
    """
    audit_log = []
    df = df.copy()

    # Determine rating battery columns BEFORE creating helper flag columns!
    if not rating_cols:
        rating_cols = [
            c for c in df.columns 
            if not str(c).startswith("__") 
            and pd.to_numeric(df[c], errors='coerce').notna().mean() > 0.85 
            and df[c].nunique() <= 7 
            and pd.to_numeric(df[c], errors='coerce').max() <= 7
        ]

    # Initialize helper columns
    df["__is_flagged"] = False
    df["__flag_reasons"] = ""

    # 1. Straight-Liner Detection (0 variance across >= 3 Likert items)
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

    # 2. Speeder Detection (< 1/3 of median completion duration)
    # Autodetect time column if not provided
    if not time_col:
        for c in df.columns:
            lower = str(c).lower()
            if any(k in lower for k in ["duration", "elapsed", "completion_time", "time_taken", "survey_time"]):
                time_col = c
                break

    if time_col and time_col in df.columns:
        durations = pd.to_numeric(df[time_col], errors='coerce')
        valid_durations = durations[durations > 0]
        if len(valid_durations) > 0:
            median_time = float(valid_durations.median())
            speeder_threshold = median_time / 3.0
            speeder_indices = durations[durations < speeder_threshold].index
            for idx in speeder_indices:
                df.loc[idx, "__is_flagged"] = True
                df.loc[idx, "__flag_reasons"] += f"Speeder (duration {durations.loc[idx]:.1f}s < 1/3 median {median_time:.1f}s); "
                audit_log.append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "row_index": int(idx),
                    "type": "SPEEDER",
                    "details": f"Duration {durations.loc[idx]:.1f}s is below 1/3 median threshold ({speeder_threshold:.1f}s)."
                })

    # 3. Demographic Duplicate Check
    demo_cols = [c for c in df.columns if df[c].nunique() < 20 and not str(c).startswith("__")]
    if len(demo_cols) >= 3:
        dup_mask = df.duplicated(subset=demo_cols, keep=False)
        for idx in df[dup_mask].index:
            df.loc[idx, "__is_flagged"] = True
            df.loc[idx, "__flag_reasons"] += "Duplicate demographic profile; "
            audit_log.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "row_index": int(idx),
                "type": "DEMOGRAPHIC_DUPLICATE",
                "details": f"Identical demographic responses across {', '.join(demo_cols[:4])}."
            })

    # 4. Write Immutable Audit Trail Log
    if log_filepath:
        try:
            with open(log_filepath, "a", encoding="utf-8") as f:
                f.write(f"\n--- CLEARIGHT HYGIENE AUDIT: {datetime.datetime.now().isoformat()} ---\n")
                f.write(f"Evaluated rows: {len(df)} | Total flagged: {int(df['__is_flagged'].sum())}\n")
                for entry in audit_log:
                    f.write(f"[{entry['timestamp']}] Row {entry['row_index']} | {entry['type']} | {entry['details']}\n")
        except Exception:
            pass

    return df, audit_log
