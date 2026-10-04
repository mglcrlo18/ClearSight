"""
ClearSight Pass 5: tests added because the corresponding single-line mutants survived the repo's
own suite (see Pass5_Report.md, "Mutation testing"). Each test names the mutant it kills.
"""
import io
import json
import os
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import pytest

import server
from server import ClearSightRequestHandler, SESSION
from engine.ingestion import read_survey_file, autodetect_schema, run_hygiene_audit
from engine.tabulation_engine import build_crosstab_table
from engine.taglish_nlp import analyze_taglish_verbatim

from test_pass5_regressions import _FakeHandler  # noqa: E402  (same in-process handler driver)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv("CLEARSIGHT_NO_AUDIT_LOG", "1")
    saved = dict(SESSION)
    yield
    SESSION.clear()
    SESSION.update(saved)


def _letters(t):
    return [r["sig_letters"] for r in t["rows"]]


# M04: FDR flag ignored when building column letters
def test_fdr_never_adds_letters_and_sometimes_removes_them():
    removed = False
    for seed in range(200):
        r = np.random.default_rng(seed)
        g = r.choice(list("abcdef"), 600)
        y = np.where(r.random(600) < np.where(g == "a", 0.62, 0.5), "yes", "no")
        df = pd.DataFrame({"G": g, "Buy": y})
        on = _letters(build_crosstab_table(df, "Buy", ["Total", "G"], fdr_enabled=True))
        off = _letters(build_crosstab_table(df, "Buy", ["Total", "G"], fdr_enabled=False))
        for row_on, row_off in zip(on, off):
            for a, b in zip(row_on, row_off):
                assert set(a.split()) <= set(b.split())
        removed = removed or on != off
        if removed:
            break
    assert removed, "BH-FDR never changed a letter in 200 random tables"


# M05: Top-2-Box from the two highest OBSERVED values instead of the top of the scale
def test_t2b_uses_scale_top_even_if_nobody_chose_it():
    df = pd.DataFrame({"G": ["x", "y"] * 50, "Sat_1to5": [1, 2, 3, 4] * 25})
    net = build_crosstab_table(df, "Sat_1to5", ["Total", "G"])["rows"][0]
    assert net["label"] == "NET: Top-2-Box (4-5)" and net["values"][0] == "25.0%"


# M06 / M27 / M28: small-base flag and suppression of letters on small bases
def test_small_base_flag_and_letter_suppression():
    df = pd.DataFrame({"G": ["tiny"] * 12 + ["big"] * 200,
                       "Buy": ["yes"] * 12 + ["yes"] * 40 + ["no"] * 160})
    t = build_crosstab_table(df, "Buy", ["Total", "G"])
    idx = [i for i, c in enumerate(t["banner_cols"]) if c.startswith("tiny")][0]
    assert t["small_base"][idx] is True
    assert all(r["sig_letters"][j] == "" for r in t["rows"] for j in range(1, len(t["banner_cols"])))


# M12: duplicate respondent IDs no longer flagged
def test_duplicate_respondent_ids_flagged():
    df = pd.DataFrame({"Respondent_ID": ["R1", "R1", "R2", "R3"], "Gender": ["M", "F", "M", "F"]})
    _, log = run_hygiene_audit(df, log_filepath=False)
    assert sorted(e["row_index"] for e in log if e["type"] == "DUPLICATE_ID") == [0, 1]


# M19: duplicate-record (same substantive answers) check disabled
def test_duplicate_records_flagged():
    base = {"Respondent_ID": ["R1", "R2", "R3", "R4"], "Gender": ["M", "M", "F", "M"], "Region": ["NCR", "NCR", "Vis", "Min"],
            "Q1_1to5": [4, 4, 2, 3], "Q2_1to5": [5, 5, 1, 2], "Q3": ["a", "a", "b", "c"]}
    _, log = run_hygiene_audit(pd.DataFrame(base), log_filepath=False)
    assert sorted(e["row_index"] for e in log if e["type"] == "DUPLICATE_RECORD") == [0, 1]


# M13: leading zeros lost on CSV import
def test_csv_leading_zeros_kept():
    df, _ = read_survey_file(b"id,Zip\n0001,0400\n0002,1100\n", "x.csv")
    assert list(df["Zip"]) == ["0400", "1100"] and list(df["id"]) == ["0001", "0002"]


# M16: P4-02 ordering (comma-rich free text typed multi_select)
def test_comma_rich_free_text_is_open_ended():
    texts = [f"Maayos naman, pero sana mas mabilis ang pila, lalo na sa umaga, salamat po ({i})" for i in range(60)]
    sc = autodetect_schema(pd.DataFrame({"Remarks": texts}))
    assert sc["Remarks"]["type"] == "open_ended"


# M17: P4-03 SPSS value labels dropped for categorical variables
def test_spss_value_labels_applied(tmp_path):
    pyreadstat = pytest.importorskip("pyreadstat")
    df = pd.DataFrame({"Gender": [1.0, 2.0, 1.0, 2.0], "Sat_1to5": [5.0, 4.0, 3.0, 2.0]})
    p = tmp_path / "t.sav"
    pyreadstat.write_sav(df, str(p), variable_value_labels={"Gender": {1.0: "Male", 2.0: "Female"},
                                                           "Sat_1to5": {5.0: "Very satisfied", 1.0: "Very dissatisfied"}})
    out, _ = read_survey_file(p.read_bytes(), "t.sav")
    assert set(out["Gender"]) == {"Male", "Female"}
    assert set(pd.to_numeric(out["Sat_1to5"], errors="coerce").dropna()) == {5.0, 4.0, 3.0, 2.0}


# M20: P4-09 export guard in generate_export_artifacts (GET /api/export/excel)
def test_get_excel_without_table_is_400():
    SESSION["df"] = pd.DataFrame({"Gender": ["M", "F"] * 5})
    SESSION["last_tabulation"] = None
    h = _FakeHandler("GET", "/api/export/excel")
    h.do_GET()
    assert h.status == 400


# M18: P4-12 weighted base printed unrounded in the Methodology sheet
def test_methodology_weighted_base_rounded(tmp_path):
    df = pd.DataFrame({"Gender": ["M", "F"] * 50, "Sat_1to5": [1, 2, 3, 4, 5] * 20})
    SESSION.update(df=df, schema=autodetect_schema(df), filename="t.csv", weight_diagnostics={},
                   weights=np.full(100, 10.750000000000002))
    SESSION["last_tabulation"] = [build_crosstab_table(df, "Sat_1to5", ["Total", "M", "F"])]
    h = _FakeHandler("GET", "/")
    out = tmp_path / "ClearSight_Agency_Banner_Book.xlsx"
    h.generate_export_artifacts("ClearSight_Agency_Banner_Book.xlsx", str(out))
    cells = [str(c) for ws in openpyxl.load_workbook(out).worksheets for row in ws.iter_rows(values_only=True) for c in row if c is not None]
    assert not any("1075.0000000000" in c for c in cells)


# M24: static path containment check
@pytest.mark.parametrize("path", ["/static/../server.py", "/static/..%2fserver.py", "/static/%2e%2e/server.py"])
def test_static_path_traversal_blocked(path):
    h = _FakeHandler("GET", path)
    h.do_GET()
    assert h.status in (403, 404) and b"ClearSightRequestHandler" not in h.wfile.getvalue()


# M25 / M29: neutral particles and negation idioms
def test_neutral_short_answers_and_negation_idioms():
    assert analyze_taglish_verbatim("ok po")[0]["code_id"] == 900
    assert analyze_taglish_verbatim("Ayos lang po.")[0]["code_id"] == 900
    assert [c["code_id"] for c in analyze_taglish_verbatim("Hindi lang mura, masarap pa")] == [110]
    assert [c["code_id"] for c in analyze_taglish_verbatim("Hindi mura")] == [120]


# M32: weighted ANOVA switched back to unweighted
def test_anova_reports_weighting_and_changes_with_weights():
    r = np.random.default_rng(3)
    g = r.choice(["x", "y", "z"], 400)
    q = r.integers(1, 6, 400)
    df = pd.DataFrame({"G": g, "Q_1to5": q})
    w = np.where((g == "x") & (q == 5), 5.0, 1.0)
    a = build_crosstab_table(df, "Q_1to5", ["Total", "G"], metric="mean")["anova"]
    b = build_crosstab_table(df, "Q_1to5", ["Total", "G"], weights=w, metric="mean")["anova"]
    assert a["weighted"] is False and b["weighted"] is True and a["f_stat"] != b["f_stat"]


# M35: missing codes (99) counted as the top of an unnamed scale
def test_unnamed_scale_ignores_99_when_finding_top():
    df = pd.DataFrame({"G": ["x", "y"] * 60, "Rate": [1, 2, 3, 4, 5, 99] * 20})
    labels = [r["label"] for r in build_crosstab_table(df, "Rate", ["Total", "G"])["rows"]]
    assert "NET: Top-2-Box (4-5)" in labels


# M09: Benjamini-Yekutieli reduced to plain BH
def test_by_is_stricter_than_bh_known_answer():
    import engine.stats_engine as se
    ps = [0.01, 0.02, 0.03, 0.04, 0.05]
    assert se.apply_fdr_benjamini_hochberg(ps) == [True] * 5
    assert se.apply_fdr_benjamini_yekutieli(ps) == [False] * 5
