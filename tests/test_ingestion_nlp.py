"""
Unit tests for ClearSight Ingestion, Hygiene, and Taglish NLP engines.
Verifies all known QA Audit edge cases, plus real-world FMCG (Harmony W3)
and Civic/Public Opinion (Frontier 2022) coding requirements.
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
    normalize_taglish_text,
    normalize_taglish_affixes,
    split_into_semantic_clauses,
    batch_code_open_ends,
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


def test_taglish_orthographic_and_dialect_normalization():
    """Verifies SMS shortcut expansion and Visayan/Cebuano dialect handling (Frontier 2022)."""
    raw = "diko gusto kc mahal man gud ang presyo ra gyod"
    norm = normalize_taglish_text(raw)
    assert "hindi ko" in norm
    assert "kasi" in norm
    assert "lang talaga" in norm

    # Loanword affix normalizer
    assert normalize_taglish_affixes("na-expose") == "expose"
    assert normalize_taglish_affixes("nag t-trigger") == "trigger"


def test_taglish_compound_clause_multi_coding():
    """Verifies semantic chunking and multi-coding on compound verbatims (Harmony W3)."""
    # Verbatim expressing: Fragrance + Softness + Sachet packaging
    compound = "Mabango ang amoy at malambot sa damit, pwedeng bilhin sa tingi-tingi sachet"
    matches = analyze_taglish_verbatim(compound)
    themes = [m["theme"] for m in matches]

    assert any("Fragrance" in t for t in themes)
    assert any("Softness" in t for t in themes)
    assert any("Sachet" in t or "Tingi" in t for t in themes)
    assert len(matches) >= 3


def test_cultural_collocations_kulob_hiyang_ayuda():
    """Verifies non-translatable Philippine cultural & sensory primitives."""
    # 1. Iwas kulob (odor protection = positive) vs amoy kulob (negative)
    anti_kulob = analyze_taglish_verbatim("Iwas kulob kahit hindi naarawan")
    assert any("Anti-Kulob" in m["theme"] or "Odor Protection" in m["theme"] for m in anti_kulob)

    has_kulob = analyze_taglish_verbatim("Nagkukulob ang damit pag maulan")
    assert any("Musty Odor" in m["theme"] for m in has_kulob)

    # 2. Hiyang (suitability)
    hiyang_match = analyze_taglish_verbatim("Hiyang sa balat ng baby ko at hindi makati")
    assert any("Hiyang" in m["theme"] or "Skin Suitability" in m["theme"] for m in hiyang_match)

    # 3. Ayuda & Tambay (Frontier 2022)
    civic = analyze_taglish_verbatim("Maraming tambay sa kalsada pero may ayuda naman galing sa barangay")
    civic_themes = [m["theme"] for m in civic]
    assert any("Ayuda" in t or "Assistance" in t for t in civic_themes)
    assert any("Enforcement" in t or "Loitering" in t for t in civic_themes)


def test_dynamic_lumping():
    """Verifies consolidation of granular sub-codes into parent codes."""
    verbatim = "Mura at available sa tingi-tingi sachet"
    # Unlumped: Tingi is code 130
    unlumped = analyze_taglish_verbatim(verbatim, apply_lumping=False)
    assert any(m["code_id"] == 130 for m in unlumped)

    # Lumped: Tingi (130) rolls up into Affordability (110)
    lumped = analyze_taglish_verbatim(verbatim, apply_lumping=True)
    assert all(m["code_id"] != 130 for m in lumped)
    assert any(m["code_id"] == 110 for m in lumped)


def test_category_guardrail_and_reask():
    """Verifies domain constraints (Harmony W3) and non-answer filtering."""
    # Fabric conditioner guardrail: ignore whitening claims
    fabcon = analyze_taglish_verbatim("Mabango at nakakaputi", category="fabcon")
    assert any("Fragrance" in m["theme"] for m in fabcon)

    # Reask detection
    reask = analyze_taglish_verbatim("Wala lang")
    assert len(reask) == 1
    assert reask[0]["code_id"] == 999
    assert "Reask" in reask[0]["theme"]


def test_human_agreement_and_kappa():
    """CS-075: Evaluates agreement, multi-label Jaccard similarity, and Cohen's kappa."""
    h = ["Positive", "Negative", "Neutral", "Positive"]
    a = ["Positive", "Negative", "Negative", "Positive"]
    res = compute_human_agreement(h, a)
    assert res["observed_agreement_pct"] == 75.0
    assert "cohens_kappa" in res
    assert "jaccard_mean_pct" in res
