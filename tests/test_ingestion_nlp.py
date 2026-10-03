"""
Unit tests for ClearSight Ingestion, Hygiene, and Taglish NLP engines.
Verifies all known QA Audit edge cases.
"""

import pandas as pd
try:
    import pytest
except ImportError:
    pytest = None

from engine.ingestion import (
    resolve_google_forms_checkboxes,
    autodetect_schema,
    run_hygiene_audit
)
from engine.taglish_nlp import (
    scrub_pii,
    analyze_taglish_verbatim,
    normalize_taglish_affixes,
    compute_human_agreement
)


def test_pii_scrubbing_formats():
    """CS-022, CS-024: Verifies masking of all Philippine mobile formats, landlines, and Gov IDs."""
    test_cases = [
        ("+63 917 123 4567", "[PHONE_REDACTED]"),
        ("+63-917-123-4567", "[PHONE_REDACTED]"),
        ("0917 123 4567", "[PHONE_REDACTED]"),
        ("(0917) 123 4567", "[PHONE_REDACTED]"),
        ("0917.123.4567", "[PHONE_REDACTED]"),
        ("0917 1234 567", "[PHONE_REDACTED]"),
        ("(02) 8123 4567", "[PHONE_REDACTED]"),
        ("TIN: 123-456-789-000", "TIN: [TIN_REDACTED]"),
        ("SSS: 34-1234567-8", "SSS: [SSS_REDACTED]")
    ]
    for raw, expected in test_cases:
        assert expected in scrub_pii(raw)


def test_google_forms_checkbox_resolution():
    """CS-019, CS-059: Delimiter collision resolution on known options with internal commas."""
    options = ["National Capital Region (NCR), Metro Manila", "Visayas", "Mindanao"]
    series = pd.Series([
        "National Capital Region (NCR), Metro Manila, Visayas",
        "Mindanao",
        "Visayas"
    ])
    df_indicators, df_other = resolve_google_forms_checkboxes(series, known_options=options)
    assert df_indicators.shape == (3, 3)
    assert df_indicators.loc[0, "National Capital Region (NCR), Metro Manila"] == 1
    assert df_indicators.loc[0, "Visayas"] == 1
    assert df_indicators.loc[0, "Mindanao"] == 0


def test_straight_liner_detection():
    """CS-020: Identifies respondents with 0 variance across rating matrix."""
    df = pd.DataFrame({
        "Q1_Rating": [5, 4, 3],
        "Q2_Rating": [5, 2, 4],
        "Q3_Rating": [5, 3, 2],
        "Q4_Rating": [5, 1, 5]
    })
    df_audited, audit_log = run_hygiene_audit(df)
    # Row 0 has variance 0 (all 5s)
    assert bool(df_audited.loc[0, "__is_flagged"]) is True
    assert bool(df_audited.loc[1, "__is_flagged"]) is False


def test_speeder_detection():
    """CS-021: Identifies speeders completing in < 1/3 of median duration."""
    df = pd.DataFrame({
        "Q1": [1, 2, 3, 4, 5, 6, 7],
        "Duration": [250, 300, 240, 260, 280, 40, 290]  # Row 5 (40s) < 260/3 (~86s)
    })
    df_audited, audit_log = run_hygiene_audit(df, time_col="Duration")
    assert bool(df_audited.loc[5, "__is_flagged"]) is True
    assert "Speeder" in df_audited.loc[5, "__flag_reasons"]


def test_taglish_polysemy_mahal():
    """CS-025, CS-069: Polysemy and negation handling for 'mahal'."""
    # Affinity
    aff = analyze_taglish_verbatim("Mahal ko talaga ang serbisyo nila")
    assert any(m["theme"] == "Strong Brand Affinity / Loyalty" for m in aff)
    assert not any(m["theme"] == "Expensive / High Pricing Friction" for m in aff)

    # Expensive
    exp = analyze_taglish_verbatim("Masyadong mahal ang shipping fee")
    assert any(m["theme"] == "Expensive / High Pricing Friction" for m in exp)

    # Negated expensive -> affordable
    neg = analyze_taglish_verbatim("Hindi mahal, sulit pa nga")
    assert any(m["theme"] == "Affordable / High Value (Sulit)" for m in neg)


def test_human_agreement_and_kappa():
    """CS-075: Evaluates agreement and Cohen's kappa."""
    h = ["Positive", "Negative", "Neutral", "Positive"]
    a = ["Positive", "Negative", "Negative", "Positive"]
    res = compute_human_agreement(h, a)
    assert res["observed_agreement_pct"] == 75.0
    assert "cohens_kappa" in res
