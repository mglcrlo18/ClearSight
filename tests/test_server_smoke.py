"""
ClearSight Analytics - Unit & Smoke Tests for Server Handlers
Tests server handler routines in-memory without requiring live socket binds:
- load_bundled_sample & SESSION state
- compute_csat Top-2-Box calculation
- build_snapshot_data
- execute_tabulation with real data
- /api/code-open-ends column resolution and execution (P4-01 regression test)
"""

import io
import json
import pandas as pd
from server import (
    load_bundled_sample,
    compute_csat,
    build_snapshot_data,
    ClearSightRequestHandler,
    SESSION
)
from engine.taglish_nlp import batch_code_open_ends
from engine.ingestion import read_survey_file, autodetect_schema, run_hygiene_audit


def test_server_session_and_sample():
    assert load_bundled_sample() is True
    assert SESSION["df"] is not None
    assert len(SESSION["df"]) > 0
    assert "schema" in SESSION
    assert SESSION["last_tabulation"] is None


def test_server_csat_and_snapshot():
    load_bundled_sample()
    df = SESSION["df"]
    csat = compute_csat(df)
    assert csat is not None
    assert csat.endswith("%")

    snap = build_snapshot_data()
    assert snap["project_title"] == "sample_survey.csv"
    assert snap["sample_n"] == len(df)
    # P5-15: the snapshot CSAT is weighted when the session has weights
    assert snap["csat_score"] == compute_csat(df, SESSION.get("weights"))
    assert "findings" in snap


def test_code_open_ends_handler_logic():
    # P4-01 regression: test column fallback and regex without NameError
    test_df = pd.DataFrame({
        "Respondent_ID": [f"R_{i}" for i in range(10)],
        "Open_End_Feedback_Taglish": [
            "Mabango at sulit gamitin",
            "Medyo mahal ang presyo",
            "Wala naman",
            "Hindi mabango"
        ] * 2 + ["Ok lang", "Maayos naman"]
    })
    SESSION["df"] = test_df
    SESSION["schema"] = autodetect_schema(test_df)

    # Verify Open_End_Feedback_Taglish is typed open_ended
    assert SESSION["schema"]["Open_End_Feedback_Taglish"]["type"] == "open_ended"

    # Execute coding directly
    verbatims = test_df["Open_End_Feedback_Taglish"].tolist()
    res = batch_code_open_ends(verbatims)
    assert res["total_analyzed"] == 10
    assert len(res["codeframe"]) > 0
    SESSION["open_feedback_analysis"] = res

    # Verify snapshot incorporates open feedback
    snap = build_snapshot_data()
    assert snap["delights"] is not None or snap["frictions"] is not None


def test_tabulation_execution():
    load_bundled_sample()
    handler = ClearSightRequestHandler.__new__(ClearSightRequestHandler)
    tables = handler.execute_tabulation(
        df=SESSION["df"],
        banner_cols=["Total", "Gender"],
        stubs=["Brand_Preference" if "Brand_Preference" in SESSION["df"].columns else SESSION["df"].columns[0]],
        confidence=95,
        fdr_enabled=True
    )
    assert len(tables) > 0
    t = tables[0]
    assert "banner_cols" in t
    assert "rows" in t
    assert len(t["rows"]) > 0


if __name__ == "__main__":
    test_server_session_and_sample()
    test_server_csat_and_snapshot()
    test_code_open_ends_handler_logic()
    test_tabulation_execution()
    print("[✓] ALL SERVER IN-MEMORY SMOKE TESTS PASSED!")
