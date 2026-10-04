"""
Pass 7 Regression Suite for ClearSight.
Tests the 5 residual audit items identified in Pass 7:
1. CS-005: Eigenvalue-based second-order Rao-Scott RS2 test with respondent_matrix in tabulation_engine.
2. CS-045: Active hygiene quarantine filtering on sample and weights during tabulation in server.py.
3. GATE-01 / P3-25: Session-isolated custom codeframe support in batch_code_open_ends and server.py.
4. CS-N04: Fallback target weighting on datasets without Region column.
5. CS-023: Single-word and compound lowercase name scrubbing with dialect false-positive protection.
"""

import math
import numpy as np
import pandas as pd
import pytest

import server
from engine.ingestion import resolve_google_forms_checkboxes, run_hygiene_audit
from engine.stats_engine import rao_scott_second_order_mrcv, calculate_rim_weights
from engine.tabulation_engine import build_crosstab_table
from engine.taglish_nlp import scrub_pii, batch_code_open_ends, analyze_taglish_verbatim


# ---------------------------------------------------------------------------
# 1. CS-005: Multi-Select MRCV Rao-Scott RS2 Test with respondent_matrix
# ---------------------------------------------------------------------------

def test_cs005_rao_scott_rs2_with_respondent_matrix():
    """Verify that rao_scott_second_order_mrcv with respondent_matrix adjusts for design effect."""
    # Synthetic respondent data: 100 respondents, 3 options
    np.random.seed(42)
    N = 100
    K = 3
    # Correlated binary responses
    base = np.random.binomial(1, 0.4, size=(N, 1))
    resp_matrix = np.hstack([base, base, np.random.binomial(1, 0.3, size=(N, 1))])

    # 3 options x 2 banner columns
    mention_table = np.array([
        [float(resp_matrix[:50, 0].sum()), float(resp_matrix[50:, 0].sum())],
        [float(resp_matrix[:50, 1].sum()), float(resp_matrix[50:, 1].sum())],
        [float(resp_matrix[:50, 2].sum()), float(resp_matrix[50:, 2].sum())],
    ])

    # Without respondent_matrix (fallback)
    f_fallback, df_fallback, p_fallback = rao_scott_second_order_mrcv(mention_table, n_eff=100.0)
    
    # With respondent_matrix (true eigenvalue adjustment)
    f_adj, df_adj, p_adj = rao_scott_second_order_mrcv(mention_table, n_eff=100.0, respondent_matrix=resp_matrix)

    assert f_adj > 0
    assert 0.0 <= p_adj <= 1.0
    # Because options 0 and 1 are perfectly correlated, design effect delta_bar != 1.0
    assert f_adj != f_fallback or p_adj != p_fallback or df_adj != df_fallback

    # Tabulation engine integration
    df = pd.DataFrame({
        "Respondent_ID": range(1, 101),
        "Region": ["NCR"] * 50 + ["Visayas"] * 50,
        "Channels": [
            "Shopee, Lazada" if r[0] and r[1] else ("Shopee" if r[0] else ("Lazada" if r[1] else "Tiktok"))
            for r in resp_matrix
        ]
    })
    table = build_crosstab_table(df, "Channels", ["Total", "Region"])
    assert table is not None
    assert "mrcv" in table
    assert table["mrcv"] is not None
    assert "f_stat" in table["mrcv"]
    assert "p_val" in table["mrcv"]
    assert table["mrcv"]["p_val"] >= 0.0


# ---------------------------------------------------------------------------
# 2. CS-045: Active Hygiene Quarantine Filtering in Tabulation
# ---------------------------------------------------------------------------

def test_cs045_hygiene_quarantine_filtering():
    """Verify that execute_tabulation filters out straight-liners and speeders when active."""
    handler = server.ClearSightRequestHandler.__new__(server.ClearSightRequestHandler)

    # 10 respondents: 2 straight-liners, 2 speeders, 6 clean
    df = pd.DataFrame({
        "Respondent_ID": range(1, 11),
        "Region": ["NCR"] * 5 + ["Visayas"] * 5,
        "CSAT": [5, 5, 5, 5, 4, 3, 2, 5, 4, 3],
        "__is_flagged": [True, True, True, True, False, False, False, False, False, False],
        "__flag_reasons": [
            "Straight-liner (zero variance across Likert battery); ",
            "Straight-liner (zero variance across Likert battery); ",
            "Speeder (duration 10s < 1/3 median 60s); ",
            "Speeder (duration 12s < 1/3 median 60s); ",
            "", "", "", "", "", ""
        ]
    })
    weights = np.ones(10)

    with server.SESSION_LOCK:
        server.SESSION["df"] = df
        server.SESSION["weights"] = weights
        server.SESSION["quarantine_straight_liners"] = True
        server.SESSION["quarantine_speeders"] = True

    tables = handler.execute_tabulation(df, ["Total", "Region"], ["CSAT"])
    assert len(tables) == 1
    # Clean respondents = 6. Unweighted base of Total should be 6, not 10.
    assert tables[0]["unweighted_bases"][0] == 6

    # Test toggling straight-liners OFF
    with server.SESSION_LOCK:
        server.SESSION["quarantine_straight_liners"] = False
        server.SESSION["quarantine_speeders"] = True
    tables_no_sl = handler.execute_tabulation(df, ["Total", "Region"], ["CSAT"])
    # 6 clean + 2 straight-liners = 8
    assert tables_no_sl[0]["unweighted_bases"][0] == 8

    # Reset
    with server.SESSION_LOCK:
        server.SESSION["quarantine_straight_liners"] = True
        server.SESSION["quarantine_speeders"] = True


# ---------------------------------------------------------------------------
# 3. GATE-01: Custom Codeframe Isolation & Ingestion
# ---------------------------------------------------------------------------

def test_gate01_custom_codeframe_pipeline():
    """Verify that a custom codeframe can be passed and isolated per session."""
    custom_cf = [
        {
            "code_id": 801,
            "net": "Pricing",
            "subnet": "Subsidized Price",
            "theme": "Benteng Bigas Accessibility",
            "keywords": ["bente", "benteng bigas", "murang bigas", "20 pesos"],
            "lump_into": None
        },
        {
            "code_id": 802,
            "net": "Supply",
            "subnet": "Queuing Friction",
            "theme": "Long Lines / Limited Stocks",
            "keywords": ["pila", "mahaba ang pila", "ubos agad", "quota"],
            "lump_into": None
        }
    ]

    verbatims = [
        "Mura nga yung benteng bigas kaso sobrang haba ng pila sa Kadiwa center.",
        "Sana araw-araw may 20 pesos na bigas para sa mahihirap.",
        "Mabilis maubos ang quota kaya maaga pa lang pumipila na kami."
    ]

    # Batch code with custom codeframe
    res = batch_code_open_ends(verbatims, codeframe=custom_cf)
    assert res["total_analyzed"] == 3
    assert len(res["codeframe"]) >= 1
    theme_names = [item["theme"] for item in res["codeframe"]]
    assert "Benteng Bigas Accessibility" in theme_names or "Long Lines / Limited Stocks" in theme_names

    # Check that individual verbatim returns custom codes
    matches = analyze_taglish_verbatim("Ang ganda ng benteng bigas promo", codeframe=custom_cf)
    assert any(m["code_id"] == 801 for m in matches)


# ---------------------------------------------------------------------------
# 4. CS-N04: Fallback Target Weighting for Datasets Without Region
# ---------------------------------------------------------------------------

def test_csn04_fallback_weighting():
    """Verify rim weighting on datasets with custom categorical demographics."""
    df = pd.DataFrame({
        "Respondent_ID": range(1, 101),
        "Staging_Distribution_Site": ["Site Alpha"] * 60 + ["Site Beta"] * 40,
        "CSAT": [4] * 100
    })

    # Weight against Staging_Distribution_Site (equal 50/50 targets)
    targets = {
        "Staging_Distribution_Site": {
            "Site Alpha": 0.50,
            "Site Beta": 0.50
        }
    }

    weights, diag = calculate_rim_weights(df, targets)
    assert weights is not None
    assert diag["converged"] is True
    assert len(weights) == 100
    # Site Alpha was 60% in sample, weighted down to 50%; Site Beta was 40%, weighted up to 50%
    mean_alpha_w = weights[:60].mean()
    mean_beta_w = weights[60:].mean()
    assert mean_alpha_w < 1.0
    assert mean_beta_w > 1.0


# ---------------------------------------------------------------------------
# 5. CS-023: Single-Word Lowercase Names & False-Positive Dialect Protection
# ---------------------------------------------------------------------------

def test_cs023_single_word_lowercase_names():
    """Verify single-word lowercase names after honorific markers are redacted without false positives."""
    # Single-word lowercase names
    assert "[NAME_REDACTED]" in scrub_pii("Kausap ko si juan kanina sa opisina.")
    assert "juan" not in scrub_pii("Kausap ko si juan kanina sa opisina.")

    assert "[NAME_REDACTED]" in scrub_pii("Inutusan ni maria ang delivery rider.")
    assert "maria" not in scrub_pii("Inutusan ni maria ang delivery rider.")

    assert "[NAME_REDACTED]" in scrub_pii("Ibigay mo kay pedro ang bayad.")
    assert "pedro" not in scrub_pii("Ibigay mo kay pedro ang bayad.")

    # Compound lowercase names
    assert "[NAME_REDACTED]" in scrub_pii("Kausap ko si maria santos kahapon.")
    assert "maria" not in scrub_pii("Kausap ko si maria santos kahapon.")
    assert "santos" not in scrub_pii("Kausap ko si maria santos kahapon.")

    # Compound Spanish surnames
    assert "[NAME_REDACTED]" in scrub_pii("Dumating si Juan dela Cruz kanina.")
    assert "dela Cruz" not in scrub_pii("Dumating si Juan dela Cruz kanina.")

    # Regional dialect false-positive protection (Bisaya/Cebuano conjunction "kay")
    assert "kay barato" in scrub_pii("Nindot kaayo ang bugas kay barato ra ug lami pa.")
    assert "kay lami" in scrub_pii("Dili nako ilisan kay lami gyud kaayo.")
    assert "kay mahal" in scrub_pii("Wala nako gipalit kay mahal ra kaayo.")
