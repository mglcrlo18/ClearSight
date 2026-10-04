"""
ClearSight Pass 5 QA regression tests (known-answer).
Each test names the finding it guards. They exercise the real HTTP handler code paths in-process
(no socket), so deleting e.g. `import re` from server.py makes a test fail (P5-04).
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import server
from server import ClearSightRequestHandler, SESSION
from engine.ingestion import read_survey_file, autodetect_schema, run_hygiene_audit
from engine.stats_engine import calculate_rim_weights
from engine.tabulation_engine import build_crosstab_table
from engine.taglish_nlp import scrub_pii

REPO = Path(__file__).resolve().parents[1]
ORIGIN = f"http://127.0.0.1:{server.PORT}"


class _FakeHandler(ClearSightRequestHandler):
    """Drives do_POST/do_GET without a socket and records status + body."""

    def __init__(self, method, path, body=b"", headers=None):
        self.command = method
        self.path = path
        self.request_version = "HTTP/1.1"
        self.requestline = f"{method} {path} HTTP/1.1"
        self.client_address = ("127.0.0.1", 0)
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        h = {"Host": f"127.0.0.1:{server.PORT}", "Origin": ORIGIN, "Content-Length": str(len(body))}
        h.update(headers or {})
        self.headers = h
        self.status = None
        self.close_connection = False

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, *args):
        pass

    def end_headers(self):
        pass

    def send_error(self, code, message=None, explain=None):
        self.status = code
        self.wfile.write(json.dumps({"status": "error", "message": message}).encode())


def _post(path, payload=None, raw=None, headers=None):
    body = raw if raw is not None else json.dumps(payload or {}).encode()
    h = _FakeHandler("POST", path, body, headers)
    h.do_POST()
    out = h.wfile.getvalue()
    try:
        return h.status, json.loads(out.decode() or "{}")
    except ValueError:
        return h.status, {"raw": out[:200]}


@pytest.fixture(autouse=True)
def _isolated_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEARSIGHT_NO_AUDIT_LOG", "1")
    saved = dict(SESSION)
    yield
    SESSION.clear()
    SESSION.update(saved)


def _load(df):
    SESSION["df"] = df
    SESSION["schema"] = autodetect_schema(df)
    SESSION["weights"] = None
    SESSION["last_tabulation"] = None


# ---------------------------------------------------------------- P5-01 / P5-03 (static UI)
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_p5_01_app_js_parses():
    r = subprocess.run(["node", "--check", str(REPO / "static" / "app.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_p5_03_no_unescaped_interpolation_into_innerhtml():
    js = (REPO / "static" / "app.js").read_text(encoding="utf-8")
    for m in re.finditer(r"innerHTML\s*=\s*`([^`]*)`", js):
        for expr in re.findall(r"\$\{([^}]*)\}", m.group(1)):
            assert expr.strip().startswith("escapeHtml("), f"unescaped ${{{expr}}} in innerHTML template"


def test_p5_14_anova_footnote_never_prints_p_equals_zero():
    js = (REPO / "static" / "app.js").read_text(encoding="utf-8")
    body = js[js.index("table-anova-note"):]
    assert "p < 0.0001" in body


def test_p5_15_snapshot_csat_weighted_and_excludes_dk():
    df = pd.DataFrame({"Overall_Satisfaction_1to5": [5, 4, 3, 2, 1, 99] * 10})
    assert server.compute_csat(df) == "40.0%"
    df2 = pd.DataFrame({"Overall_Satisfaction_1to5": [5] * 10 + [1] * 90})
    w = np.r_[np.full(10, 9.0), np.full(90, 1.0)]
    assert server.compute_csat(df2, w) == f"{90 / 180 * 100:.1f}%"


# ---------------------------------------------------------------- P5-02 (Python 3.10-3.13 import)
def test_p5_02_engine_imports_in_fresh_interpreter():
    code = "import engine.stats_engine, engine.tabulation_engine, engine.ingestion, engine.taglish_nlp, server"
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True,
                       env={**os.environ, "CLEARSIGHT_NO_AUDIT_LOG": "1"})
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------- P5-04 / P4-01 / P5-10 (code-open-ends handler)
def test_p5_04_code_open_ends_regex_fallback_runs_in_handler():
    df = pd.DataFrame({"Respondent_ID": [f"R{i}" for i in range(30)],
                       "Remarks": ["Medyo mahal pero sulit naman ang bigas, salamat po sa programa"] * 30})
    _load(df)
    SESSION["schema"] = {c: {"type": "single_select"} for c in df.columns}  # force the re.search fallback
    status, j = _post("/api/code-open-ends", {})
    assert status == 200 and j["status"] == "success" and j["column"] == "Remarks", j


def test_p5_10_no_open_end_column_is_not_an_http_error():
    _load(pd.DataFrame({"Gender": ["M", "F"] * 20, "Sat_1to5": [1, 2, 3, 4, 5] * 8}))
    status, j = _post("/api/code-open-ends", {})
    assert status == 200 and j["status"] == "empty"


# ---------------------------------------------------------------- CS-088 (tabulate input validation)
@pytest.mark.parametrize("payload", [
    {"confidence": "abc"},
    {"confidence": 80},
    {"fdr_enabled": "false"},
    {"banner_cols": "Total"},
    {"stubs": "Gender"},
    {"metric": "median"},
])
def test_cs_088_bad_tabulate_input_gets_json_400(payload):
    _load(pd.DataFrame({"Gender": ["M", "F"] * 20, "Sat_1to5": [1, 2, 3, 4, 5] * 8}))
    body = {"banner_cols": ["Total", "M", "F"], "stubs": ["Sat_1to5"], "confidence": 95, "fdr_enabled": True}
    body.update(payload)
    status, j = _post("/api/tabulate", body)
    assert status == 400 and j["status"] == "error"


def test_cs_088_valid_tabulate_still_works():
    _load(pd.DataFrame({"Gender": ["M", "F"] * 20, "Sat_1to5": [1, 2, 3, 4, 5] * 8}))
    status, j = _post("/api/tabulate", {"banner_cols": ["Total", "M", "F"], "stubs": ["Sat_1to5"],
                                        "confidence": 95, "fdr_enabled": False})
    assert status == 200 and j["status"] == "success" and not j["table"][0].get("error")
    assert SESSION["fdr_enabled"] is False


# ---------------------------------------------------------------- P4-09 (export guard)
def test_p4_09_error_only_table_does_not_unlock_banner_book():
    _load(pd.DataFrame({"Gender": ["M", "F"] * 20, "Sat_1to5": [1, 2, 3, 4, 5] * 8}))
    # what the UI sent after every upload: a demo stub that is not in the file
    status, j = _post("/api/tabulate", {"banner_cols": ["Total", "NCR"], "stubs": ["Q1: Brand Preference"],
                                        "confidence": 95, "fdr_enabled": True})
    assert status == 200 and j["table"][0]["error"]
    assert not SESSION.get("last_tabulation")
    status, j = _post("/api/export/save-to-downloads", {})
    assert status == 400 and "Build at least one table" in j["message"]


def test_p4_09_ui_shows_export_error_message():
    js = (REPO / "static" / "app.js").read_text(encoding="utf-8")
    body = js[js.index("function downloadExcel"):js.index("function downloadSnapshot")]
    assert "data.message" in body


# ---------------------------------------------------------------- P5-09 / CWE-400
def test_p5_09_origin_must_match_exactly():
    _load(pd.DataFrame({"Gender": ["M", "F"] * 5}))
    for bad in (ORIGIN + "1", "http://127.0.0.1.evil.test:%d" % server.PORT, "null"):
        status, _ = _post("/api/load-sample", {}, headers={"Origin": bad})
        assert status == 403, bad


def test_cwe_400_oversized_body_rejected_before_reading():
    h = _FakeHandler("POST", "/api/upload", b"", {"Content-Length": str(server.MAX_BODY_BYTES + 1)})
    h.do_POST()
    assert h.status == 413


def test_cwe_400_handler_has_socket_timeout():
    assert isinstance(ClearSightRequestHandler.timeout, (int, float)) and 0 < ClearSightRequestHandler.timeout <= 300


# ---------------------------------------------------------------- P4-10 / CS-023 / P5-07 (PII known answers)
@pytest.mark.parametrize("text, must_not_contain", [
    ("Kausap ko si Gng. Reyes", "Reyes"),
    ("Smart ko 0813 123 4567", "4567"),
    ("Globe 0817-123-4567", "4567"),
    ("Landline +63 2 8123 4567", "4567"),
    ("Tel no.: 8-123-4567", "4567"),
    ("Ang PhilSys number ko ay 1234 5678 9012", "9012"),
    ("PCN 1234 5678 9012 3456", "3456"),
    ("card 2221 0000 0000 0009", "0009"),
    ("Amex 3782 822463 10005", "10005"),
])
def test_p5_07_pii_masked(text, must_not_contain):
    assert must_not_contain not in scrub_pii(text)


@pytest.mark.parametrize("text", [
    "Order ref 2026 1004 0001",
    "Paid ID ref: 2026 1004 0001 0002",
    "Bumili ako sa Mang Inasal",
    "Gastos ko ₱1,250.00 noong 2025-10-04",
])
def test_p5_07_non_pii_kept(text):
    assert scrub_pii(text) == text


def test_p5_07_keyword_and_following_word_kept():
    assert scrub_pii("PhilSys 1234 5678 9012 po") == "PhilSys [PHILSYS_REDACTED] po"
    assert scrub_pii("Tawagan 0917 123 4567 salamat") == "Tawagan [PHONE_REDACTED] salamat"


# ---------------------------------------------------------------- P5-05 (count targets)
def test_p5_05_small_integer_counts_accepted_and_match_shares():
    df = pd.DataFrame({"City": ["A"] * 60 + ["B"] * 40})
    w, _ = calculate_rim_weights(df, {"City": {"A": 20, "B": 30}})
    assert abs(w[:60].sum() / w.sum() - 0.4) < 1e-6


def test_p5_05_fractional_targets_still_validated():
    df = pd.DataFrame({"City": ["A"] * 60 + ["B"] * 40})
    with pytest.raises(ValueError):
        calculate_rim_weights(df, {"City": {"A": 0.4, "B": 0.5}})
    with pytest.raises(ValueError):
        calculate_rim_weights(df, {"City": {"A": 45.5, "B": 44.5}})


# ---------------------------------------------------------------- P3-03 residual (Top-2-Box)
def test_p3_03_rating_named_scale_without_bottom_codes_gets_t2b():
    r = np.random.default_rng(1)
    df = pd.DataFrame({"G": r.choice(["x", "y"], 200), "Service_rating": r.integers(2, 6, 200)})
    t = build_crosstab_table(df, "Service_rating", ["Total", "G"])
    net = [x for x in t["rows"] if "Top-2-Box" in x["label"]]
    assert net and net[0]["label"].endswith("(4-5)")
    exp = round(float(np.isin(df.Service_rating, [4, 5]).mean() * 100), 1)
    assert net[0]["values"][0] == f"{exp:.1f}%"


def test_p3_03_dk_probe_still_375():
    df = pd.DataFrame({"G": ["x", "y"] * 50, "Sat_1to5": [4] * 30 + [3] * 30 + [2] * 20 + [99] * 20})
    t = build_crosstab_table(df, "Sat_1to5", ["Total", "G"])
    assert t["rows"][0]["values"][0] == "37.5%"


# ---------------------------------------------------------------- Ingestion (P5-08, P5-11, P5-12) and P4-11
def test_p5_08_count_columns_ending_in_no_stay_numeric():
    r = np.random.default_rng(0)
    df = pd.DataFrame({"Children_no": r.integers(0, 6, 300).astype(str),
                       "Visits_no": r.integers(0, 40, 300).astype(str)})
    sc = autodetect_schema(df)
    assert sc["Children_no"]["type"] == "numeric" and sc["Visits_no"]["type"] == "numeric"


def test_p5_11_semicolon_csv_is_split():
    df, meta = read_survey_file(b"id;Gender;Sat_1to5\n1;M;4\n2;F;5\n3;M;2\n", "x.csv")
    assert list(df.columns) == ["id", "Gender", "Sat_1to5"]


def test_p5_12_cp1252_smart_quotes_decoded():
    raw = "id,Comment\n1,\u201cSulit\u201d \u2014 salamat\u2026\n".encode("cp1252")
    df, meta = read_survey_file(raw, "x.csv")
    assert df.loc[0, "Comment"] == "\u201cSulit\u201d \u2014 salamat\u2026"


def test_p4_11_audit_log_can_be_disabled(tmp_path, monkeypatch):
    import engine.ingestion as ing
    target = tmp_path / "cleaning_audit_trail.log"
    monkeypatch.setattr(ing, "DEFAULT_LOG_FILEPATH", str(target))
    monkeypatch.setenv("CLEARSIGHT_NO_AUDIT_LOG", "1")
    df = pd.DataFrame({"Respondent_ID": ["R1", "R1", "R2"], "a_1to5": [1, 1, 2], "b_1to5": [1, 1, 2], "c_1to5": [1, 1, 2]})
    run_hygiene_audit(df)
    assert not target.exists()


def test_p4_11_audit_log_rotates(tmp_path):
    log = tmp_path / "audit.log"
    log.write_text("x" * 5_100_000)
    df = pd.DataFrame({"Respondent_ID": ["R1", "R1", "R2"], "a_1to5": [1, 1, 2], "b_1to5": [1, 1, 2], "c_1to5": [1, 1, 2]})
    run_hygiene_audit(df, log_filepath=str(log))
    assert (tmp_path / "audit.log.1").exists() and log.stat().st_size < 100_000
