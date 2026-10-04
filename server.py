"""
ClearSight Analytics - Local Desktop Backend Server
Zero-cloud execution. Runs on localhost:8540 with zero external data transmission.
Threaded, hardened against path traversal, DNS rebinding, and CSRF.
"""

import os
import sys
import re
import json
import logging
import mimetypes
import tempfile
import subprocess
import numpy as np
import pandas as pd
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

SESSION_LOCK = threading.Lock()

# Add current directory to path
CURR_DIR = os.path.dirname(os.path.abspath(__file__))
if CURR_DIR not in sys.path:
    sys.path.insert(0, CURR_DIR)

from engine.ingestion import autodetect_schema, run_hygiene_audit, read_survey_file, resolve_google_forms_checkboxes
from engine.stats_engine import (
    calculate_rim_weights,
    test_pairwise_proportions,
    test_vs_total_benchmark,
    test_means_significance,
    apply_fdr_benjamini_hochberg,
    apply_fdr_benjamini_yekutieli,
    calculate_kish_neff
)
from engine.driver_analysis import compute_johnsons_relative_weights
from engine.taglish_nlp import batch_code_open_ends, scrub_pii
from engine.codeframe_loader import CodeframeError, list_codeframes, load_codeframe, load_codeframe_from_dict, validate_codeframe

# Coder feature flag: "v2" (default; beat v1 on the held-out client test set, see
# Coder_Improvement_Plan.md) or "v1" (legacy rule coder). Per request: {"coder": "v1"|"v2"}.
CODER_DEFAULT = os.environ.get("CLEARSIGHT_CODER", "v2").strip().lower()
if CODER_DEFAULT not in ("v1", "v2"):
    CODER_DEFAULT = "v2"
_FEEDBACK_STORE = None


def get_feedback_store():
    """Local analyst-correction store (/coder_corrections.json); created lazily."""
    global _FEEDBACK_STORE
    if _FEEDBACK_STORE is None:
        from engine.coder_feedback import FeedbackStore
        _FEEDBACK_STORE = FeedbackStore()
    return _FEEDBACK_STORE


def pick_codeframe(req_data: dict) -> str:
    """Codeframe by *name* only (no paths: CWE-22); falls back to the category hint."""
    name = req_data.get("codeframe")
    if isinstance(name, str) and name:
        return name
    cat = str(req_data.get("category") or "").lower()
    return "governance_default" if any(w in cat for w in ("govern", "public", "politic", "election")) else "consumer_default"
from engine.export_engine import (
    generate_excel_banner_book,
    generate_customer_voice_snapshot_html,
    generate_thesis_chapter_4_package,
    generate_thesis_excel_tables
)

PORT = 8540
ALLOWED_HOSTS = {"127.0.0.1:8540", "localhost:8540", "127.0.0.1", "localhost"}
# CWE-400 / CS-N15: cap request bodies (uploads) and idle connections.
MAX_BODY_BYTES = int(float(os.environ.get("CLEARSIGHT_MAX_UPLOAD_MB", "200")) * 1024 * 1024)
REQUEST_TIMEOUT_SECONDS = 60

# In-Memory Active Survey Session State
SESSION = {
    "df": None,
    "filename": "No dataset loaded",
    "schema": {},
    "weights": None,
    "weight_diagnostics": None,
    "hygiene_audit": [],
    "last_tabulation": None,
    "open_feedback_analysis": None,
    "custom_codeframe": None,
    "quarantine_straight_liners": True,
    "quarantine_speeders": True
}


def get_downloads_dir() -> str:
    """Resolves the user's Downloads directory portably."""
    user_downloads = Path.home() / "Downloads"
    if user_downloads.exists():
        return str(user_downloads)
    return str(Path.home())


def safe_reveal_in_finder(filepath: str):
    """Safely reveals file in OS file explorer without shell interpolation."""
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", filepath], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{filepath}"], check=False)


def load_bundled_sample():
    """Loads bundled sample Philippine consumer survey into memory."""
    sample_csv = os.path.join(CURR_DIR, "data", "sample_survey.csv")
    if os.path.exists(sample_csv):
        import pandas as pd
        df = pd.read_csv(sample_csv)
        schema = autodetect_schema(df)
        df_audited, audit_log = run_hygiene_audit(df, time_col="Survey_Duration_Sec")
        
        # Calculate default initial weights
        targets = {
            "Region": {
                "National Capital Region (NCR)": 0.14,
                "Balance Luzon": 0.45,
                "Visayas": 0.20,
                "Mindanao": 0.21
            }
        }
        try:
            weights, diag = calculate_rim_weights(df, targets, trim_percentile=95.0)
        except Exception:
            weights = None
            diag = None

        SESSION["df"] = df_audited
        SESSION["filename"] = "sample_survey.csv"
        SESSION["schema"] = schema
        SESSION["weights"] = weights
        SESSION["weight_diagnostics"] = diag
        SESSION["hygiene_audit"] = audit_log
        SESSION["last_tabulation"] = None
        SESSION["open_feedback_analysis"] = None
        return True
    return False



def compute_csat(df, weights=None):
    """Top-2-Box satisfaction for the snapshot: weighted when weights exist, DK/refused (97/98/99)
    excluded from the base, top two points of the scale (P5-15)."""
    if df is None:
        return None
    w_all = np.ones(len(df)) if weights is None else np.asarray(weights, dtype=float)
    for c in df.columns:
        if any(k in c.lower() for k in ["csat", "satisfaction"]):
            vals = pd.to_numeric(df[c], errors="coerce")
            keep = (vals.notna() & ~vals.isin([97, 98, 99])).to_numpy()
            s_vals = vals[keep]
            if len(s_vals) > 0 and s_vals.max() <= 5:
                w = w_all[keep]
                if w.sum() <= 0:
                    return None
                return f"{float(w[(s_vals >= 4).to_numpy()].sum() / w.sum()) * 100:.1f}%"
    return None


def build_snapshot_data():
    """Unifies snapshot data building for both preview and export from active session."""
    df = SESSION.get("df")
    n = len(df) if df is not None else 0
    diag = SESSION.get("weight_diagnostics") or {}
    neff = diag.get("kish_n_eff", float(n))
    eff = diag.get("weighting_efficiency_pct", 100.0)
    csat_val = compute_csat(df, SESSION.get("weights")) or "n/a"

    delights = []
    frictions = []
    if SESSION.get("open_feedback_analysis"):
        cframe = SESSION["open_feedback_analysis"].get("codeframe", [])
        for item in cframe:
            t_name = item.get("theme", "")
            quotes = item.get("evidence_samples", [])
            if quotes:
                q_text = quotes[0].get("quote", "")
                if any(w in t_name for w in ["Sulit", "Service", "Affordable", "Affinity", "Fragrance", "Softness", "Protection", "Ayuda"]):
                    delights.append({"quote": q_text, "author": f"Respondent ({t_name.split('/')[0].strip()})"})
                elif not any(w in t_name for w in ["General Feedback", "Non-Substantive"]):
                    frictions.append({"quote": q_text, "author": f"Respondent ({t_name.split('/')[0].strip()})"})

    return {
        "project_title": SESSION.get("filename", "Customer Voice Analysis"),
        "sample_n": n,
        "eff_n": neff,
        "csat_score": csat_val,
        "weighting_eff": f"{eff}%",
        "findings": [],
        "delights": delights if delights else None,
        "frictions": frictions if frictions else None,
        "action_matrix": []
    }


class ClearSightRequestHandler(BaseHTTPRequestHandler):
    server_version = "ClearSight/1.0"
    # socketserver applies this to every accepted connection (settimeout), so a client that
    # announces a large Content-Length and never sends it no longer pins a thread forever.
    timeout = REQUEST_TIMEOUT_SECONDS

    def log_message(self, format, *args):
        # Clean production logging
        pass

    def validate_host_header(self) -> bool:
        """Protects against DNS Rebinding attacks by validating Host header."""
        host = self.headers.get("Host", "").strip()
        if host not in ALLOWED_HOSTS:
            self.send_error(400, "Bad Request: Invalid Host header.")
            return False
        return True

    def validate_origin_header(self) -> bool:
        """Validates Origin/Referer header on state-changing endpoints to prevent CSRF."""
        origin = self.headers.get("Origin", "")
        referer = self.headers.get("Referer", "")
        allowed = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
        # Exact origin match: a prefix test also accepted e.g. "http://127.0.0.1:85401" (P5-09).
        if origin and origin.rstrip("/") not in allowed:
            self.send_error(403, "Forbidden: Invalid cross-origin request.")
            return False
        ref = urlparse(referer) if referer else None
        if not origin and referer and f"{ref.scheme}://{ref.netloc}" not in allowed:
            self.send_error(403, "Forbidden: Invalid cross-origin referer.")
            return False
        return True

    def send_json_response(self, data: dict, status: int = 200):
        content = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self';")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def serve_file(self, filepath: str, mime_type: str):
        """Serves file safely, strictly checking for path traversal."""
        real_filepath = os.path.realpath(filepath)
        real_static_dir = os.path.realpath(os.path.join(CURR_DIR, "static"))

        # Strictly confine to the static directory (CS-007 resolution)
        if not (real_filepath == real_static_dir or real_filepath.startswith(real_static_dir + os.sep)):
            self.send_error(404, "Resource not found.")
            return
        if not os.path.isfile(real_filepath):
            self.send_error(404, "Resource not found.")
            return

        try:
            with open(real_filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self';")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(500, "Internal server error reading file.")

    def do_GET(self):
        if not self.validate_host_header():
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html"]:
            self.serve_file(os.path.join(CURR_DIR, "static", "index.html"), "text/html; charset=utf-8")
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):].lstrip("/")
            local_path = os.path.join(CURR_DIR, "static", rel_path)
            mime, _ = mimetypes.guess_type(local_path)
            self.serve_file(local_path, mime or "application/octet-stream")
        elif path == "/preview-snapshot":
            try:
                data = build_snapshot_data()
                with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp_f:
                    tmp_path = tmp_f.name
                try:
                    generate_customer_voice_snapshot_html(tmp_path, data)
                    with open(tmp_path, "rb") as f:
                        snap_bytes = f.read()
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(snap_bytes)))
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self';")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(snap_bytes)
            except Exception as e:
                logging.exception("Failed to generate preview snapshot")
                self.send_error(500, f"Snapshot preview error: {e}")
        elif path == "/api/dataset-status":
            has_data = SESSION["df"] is not None
            resp = {
                "loaded": has_data,
                "filename": SESSION["filename"],
                "total_rows": len(SESSION["df"]) if has_data else 0,
                "columns": list(SESSION["df"].columns) if has_data else [],
                "weighted": SESSION["weights"] is not None,
                "diagnostics": SESSION["weight_diagnostics"]
            }
            self.send_json_response(resp)
        elif path == "/api/coder/review-queue":
            self.coder_review_queue()
        elif path == "/api/coder/codeframes":
            self.send_json_response({"status": "success", "default_coder": CODER_DEFAULT, "codeframes": list_codeframes()})
        elif path == "/api/coder/telemetry":
            from engine.coder_v2 import telemetry_snapshot
            store = get_feedback_store()
            self.send_json_response({"status": "success", "local_only": True, "counters": telemetry_snapshot(), "feedback": store.stats()})
        elif path == "/api/export/excel":
            self.stream_export_file("ClearSight_Agency_Banner_Book.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        elif path == "/api/export/snapshot-download":
            self.stream_export_file("ClearSight_Customer_Voice_Snapshot_A4.html", "text/html; charset=utf-8")
        elif path == "/api/export/thesis-download":
            self.stream_export_file("ClearSight_Thesis_Chapter_4_Package.html", "text/html; charset=utf-8")
        else:
            self.send_error(404, "Endpoint not found.")

    def do_POST(self):
        if not self.validate_host_header() or not self.validate_origin_header():
            return

        parsed = urlparse(self.path)
        path = parsed.path

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > MAX_BODY_BYTES:
                self.close_connection = True
                self.send_json_response({"status": "error", "message": f"Request too large: limit is {MAX_BODY_BYTES // (1024 * 1024)} MB."}, 413)
                return
            body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
            if len(body_bytes) < content_length:
                raise ValueError("Truncated request body.")
        except Exception:
            self.send_json_response({"status": "error", "message": "Failed to read request body."}, 400)
            return

        if path == "/api/load-sample":
            success = load_bundled_sample()
            if success:
                self.send_json_response({
                    "status": "success",
                    "message": "Sample Philippine Consumer Survey loaded into RAM.",
                    "total_respondents": len(SESSION["df"]),
                    "columns": list(SESSION["df"].columns),
                    "schema": SESSION["schema"],
                    "flagged_hygiene": len(SESSION["hygiene_audit"]),
                    "diagnostics": SESSION["weight_diagnostics"]
                })
            else:
                self.send_json_response({"status": "error", "message": "Bundled sample dataset not found."}, 404)

        elif path == "/api/upload":
            filename = self.headers.get("X-Filename", "survey_data.csv")
            try:
                df, meta = read_survey_file(body_bytes, filename)
                schema = autodetect_schema(df)
                df_audited, audit_log = run_hygiene_audit(df)
                
                SESSION["df"] = df_audited
                SESSION["filename"] = filename
                SESSION["schema"] = schema
                SESSION["weights"] = None
                SESSION["weight_diagnostics"] = None
                SESSION["hygiene_audit"] = audit_log
                SESSION["last_tabulation"] = None
                SESSION["open_feedback_analysis"] = None
                SESSION["custom_codeframe"] = None

                self.send_json_response({
                    "status": "success",
                    "filename": filename,
                    "total_respondents": len(df),
                    "columns": list(df.columns),
                    "schema": schema,
                    "flagged_hygiene": len(audit_log)
                })
            except Exception as e:
                self.send_json_response({"status": "error", "message": str(e)}, 400)

        elif path == "/api/weight":
            if SESSION["df"] is None:
                load_bundled_sample()

            try:
                req_data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                req_data = {}

            targets = req_data.get("targets")
            trim_pct = req_data.get("trim_percentile", 95.0)

            if not targets:
                # Identify if default demographic columns exist (CS-N04)
                if SESSION.get("df") is not None and "Region" in SESSION["df"].columns:
                    targets = {
                        "Region": {
                            "National Capital Region (NCR)": 0.14,
                            "Balance Luzon": 0.45,
                            "Visayas": 0.20,
                            "Mindanao": 0.21
                        }
                    }
                else:
                    self.send_json_response({
                        "status": "error",
                        "message": "No 'Region' column found. Please provide explicit weighting targets for dataset columns."
                    }, 400)
                    return

            try:
                weights, diagnostics = calculate_rim_weights(
                    SESSION["df"], 
                    targets, 
                    trim_percentile=trim_pct
                )
                SESSION["weights"] = weights
                SESSION["weight_diagnostics"] = diagnostics
                self.send_json_response({
                    "status": "success",
                    "diagnostics": diagnostics
                })
            except Exception as e:
                self.send_json_response({"status": "error", "message": str(e)}, 400)

        elif path == "/api/hygiene-filter":
            try:
                req_data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                req_data = {}
            with SESSION_LOCK:
                SESSION["quarantine_straight_liners"] = bool(req_data.get("filter_straight_liners", True))
                SESSION["quarantine_speeders"] = bool(req_data.get("filter_speeders", True))
                df = SESSION.get("df")
                total_n = len(df) if df is not None else 0
                active_n = total_n
                if df is not None and "__is_flagged" in df.columns:
                    cond = pd.Series(True, index=df.index)
                    if SESSION["quarantine_straight_liners"]:
                        cond &= ~df["__flag_reasons"].str.contains("Straight-liner", na=False)
                    if SESSION["quarantine_speeders"]:
                        cond &= ~df["__flag_reasons"].str.contains("Speeder", na=False)
                    active_n = int(cond.sum())
            self.send_json_response({"status": "success", "active_respondents": active_n, "total_respondents": total_n})

        elif path == "/api/set-codeframe":
            try:
                req_data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                req_data = {}
            custom_codeframe = req_data.get("codeframe")
            if not custom_codeframe or not isinstance(custom_codeframe, list):
                self.send_json_response({"status": "error", "message": "Codeframe must be a non-empty list of category definitions."}, 400)
                return
            with SESSION_LOCK:
                SESSION["custom_codeframe"] = custom_codeframe
            self.send_json_response({
                "status": "success", 
                "message": f"Registered custom codeframe with {len(custom_codeframe)} categories.",
                "categories_count": len(custom_codeframe)
            })

        elif path == "/api/tabulate":
            if SESSION["df"] is None:
                load_bundled_sample()

            try:
                req_data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                req_data = {}

            with SESSION_LOCK:
                df = SESSION["df"]
            # CS-088: validate request types and never drop the connection on bad input.
            banner_cols = req_data.get("banner_cols", ["Total", "NCR (A)", "Balance Luzon (B)", "Visayas (C)", "Mindanao (D)"])
            stubs = req_data.get("stubs", ["Brand Preference"])
            metric = req_data.get("metric", "pct")
            try:
                confidence = int(req_data.get("confidence", 95))
            except (TypeError, ValueError):
                confidence = None
            fdr_raw = req_data.get("fdr_enabled", True)
            if (not isinstance(banner_cols, list) or not all(isinstance(b, str) for b in banner_cols)
                    or not isinstance(stubs, list) or not stubs or not all(isinstance(x, str) for x in stubs)
                    or confidence not in (90, 95, 99) or metric not in ("pct", "mean", "t2b")
                    or not isinstance(fdr_raw, bool)):
                self.send_json_response({"status": "error", "message": "Invalid tabulation request: banner_cols/stubs must be lists of strings, confidence 90/95/99, fdr_enabled true/false, metric pct/mean/t2b."}, 400)
                return
            fdr_enabled = fdr_raw

            try:
                result = self.execute_tabulation(df, banner_cols, stubs, confidence, fdr_enabled, metric=metric)
            except Exception as e:
                logging.exception(f"Tabulation error: {e}")
                self.send_json_response({"status": "error", "message": f"Tabulation failed: {e}"}, 500)
                return
            # P4-09: tables that only carry an error (e.g. the UI's placeholder stub) do not count as built.
            with SESSION_LOCK:
                if any(not t.get("error") for t in result):
                    SESSION["last_tabulation"] = [t for t in result if not t.get("error")]
                    SESSION["fdr_enabled"] = fdr_enabled
            self.send_json_response({"status": "success", "table": result})

        elif path == "/api/code-open-ends":
            if SESSION["df"] is None:
                load_bundled_sample()

            df = SESSION["df"]
            try:
                req_data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                req_data = {}

            try:
                req_col = req_data.get("column")
                open_cols = [c for c, v in SESSION.get("schema", {}).items() if v.get("type") == "open_ended"]

                open_col = None
                if req_col and req_col in df.columns:
                    open_col = req_col
                elif open_cols:
                    open_col = open_cols[0]
                else:
                    for col in df.columns:
                        c_low = col.lower()
                        # P5-13: pandas >= 3 stores text as the "str" dtype, so `dtype == object` never matched.
                        is_text = df[col].dtype == object or pd.api.types.is_string_dtype(df[col])
                        if re.search(r'\b(?:open|feedback|comment|verbatim)\b', c_low) or (is_text and df[col].dropna().astype(str).str.len().mean() > 20):
                            open_col = col
                            break

                if not open_col:
                    # Not an error: many files have no open-ends. A 400 here printed a console error in the UI (P5-10).
                    self.send_json_response({"status": "empty", "message": "No open-ended feedback column found in dataset."})
                    return

                verbatims = df[open_col].dropna().astype(str).tolist()
                coder = str(req_data.get("coder") or CODER_DEFAULT).lower()
                if coder not in ("v1", "v2"):
                    self.send_json_response({"status": "error", "message": "coder must be 'v1' or 'v2'."}, 400)
                    return

                with SESSION_LOCK:
                    custom_codeframe = SESSION.get("custom_codeframe")

                if coder == "v2":
                    from engine.coder_v2 import Coder, CoderConfig, batch_code_v2
                    try:
                        if custom_codeframe and isinstance(custom_codeframe, list):
                            from engine.codeframe_loader import validate_codeframe
                            cf = validate_codeframe({"schema_version": 1, "id": "custom", "name": "Custom Uploaded Codeframe", "topics": custom_codeframe})
                        elif custom_codeframe and isinstance(custom_codeframe, dict):
                            from engine.codeframe_loader import load_codeframe_from_dict
                            cf = load_codeframe_from_dict(custom_codeframe)
                        else:
                            cf = load_codeframe(pick_codeframe(req_data))
                    except CodeframeError as e:
                        self.send_json_response({"status": "error", "message": f"Invalid codeframe: {e}"}, 400)
                        return
                    coding_results = batch_code_v2(verbatims, coder=Coder(cf, CoderConfig(feedback=get_feedback_store())))
                else:
                    coding_results = batch_code_open_ends(
                        verbatims,
                        category=req_data.get("category"),
                        apply_lumping=bool(req_data.get("apply_lumping", req_data.get("lump", False))),
                        codeframe=custom_codeframe
                    )
                    coding_results["coder_version"] = "1"

                with SESSION_LOCK:
                    SESSION["open_feedback_analysis"] = coding_results

                self.send_json_response({
                    "status": "success",
                    "column": open_col,
                    "coder": coder,
                    "coder_version": coding_results.get("coder_version"),
                    "codeframe_id": coding_results.get("codeframe_id"),
                    "total_analyzed": coding_results.get("total_analyzed", len(verbatims)),
                    "codeframe": coding_results.get("codeframe", []),
                    "records": coding_results.get("records", [])[:50],
                    "review_queue_count": len(coding_results.get("review_queue", [])),
                    "sentiment_counts": coding_results.get("sentiment_counts", {}),
                })
            except Exception as e:
                logging.exception(f"Error coding open ends: {e}")
                self.send_json_response({"status": "error", "message": str(e)}, 500)

        elif path == "/api/coder/feedback":
            self.handle_coder_feedback(body_bytes)
        elif path in ["/api/export/save-to-downloads", "/api/export/save-snapshot-to-downloads", "/api/export/save-thesis-to-downloads"]:
            self.handle_save_to_downloads(path)
        else:
            self.send_error(404, "Endpoint not found.")

    # ---------------------------------------------------------------- coder v2
    def handle_coder_feedback(self, body_bytes: bytes):
        """Analyst correction: {"response_id": int} (from the last coding run) or {"text": str},
        plus "sentiment" (pos/neg/neutral/mixed) and/or "code_ids" (list). Stored locally only."""
        try:
            req = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            req = None
        if not isinstance(req, dict):
            self.send_json_response({"status": "error", "message": "Body must be a JSON object."}, 400)
            return
        analysis = SESSION.get("open_feedback_analysis") or {}
        rec = None
        text = req.get("text")
        rid = req.get("response_id")
        if rid is not None:
            if not isinstance(rid, int) or isinstance(rid, bool):
                self.send_json_response({"status": "error", "message": "response_id must be an integer."}, 400)
                return
            rec = next((r for r in analysis.get("records", []) if r.get("response_id") == rid), None)
            if rec is None:
                self.send_json_response({"status": "error", "message": "Unknown response_id."}, 404)
                return
            text = rec.get("raw_text", "")
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            self.send_json_response({"status": "error", "message": "text must be a non-empty string (max 5000 chars)."}, 400)
            return
        sentiment = req.get("sentiment")
        code_ids = req.get("code_ids", [])
        if sentiment is not None and sentiment not in ("pos", "neg", "neutral", "mixed"):
            self.send_json_response({"status": "error", "message": "sentiment must be pos, neg, neutral or mixed."}, 400)
            return
        if not isinstance(code_ids, list) or len(code_ids) > 10 or not all(isinstance(c, (int, str)) and not isinstance(c, bool) for c in code_ids):
            self.send_json_response({"status": "error", "message": "code_ids must be a list (max 10) of ids."}, 400)
            return
        if sentiment is None and not code_ids:
            self.send_json_response({"status": "error", "message": "Give a sentiment and/or code_ids."}, 400)
            return
        cf_id = analysis.get("codeframe_id") or pick_codeframe(req)
        themes = []
        if code_ids:
            try:
                cf = load_codeframe(cf_id)
            except CodeframeError as e:
                self.send_json_response({"status": "error", "message": f"Invalid codeframe: {e}"}, 400)
                return
            labels = {str(c["code_id"]): c["label"] for t in cf["topics"] for c in t["codes"].values()}
            labels.update({str(c["code_id"]): c["label"] for c in cf["special"].values()})
            unknown = [c for c in code_ids if str(c) not in labels]
            if unknown:
                self.send_json_response({"status": "error", "message": "Unknown code_ids for this codeframe."}, 400)
                return
            themes = [labels[str(c)] for c in code_ids]
        try:
            saved = get_feedback_store().add(text, sentiment=sentiment, code_ids=code_ids, themes=themes, codeframe=cf_id)
        except (ValueError, OSError) as e:
            self.send_json_response({"status": "error", "message": str(e)}, 400)
            return
        if rec is not None:
            rec.update(assigned_themes=themes or rec.get("assigned_themes"), assigned_codes=code_ids or rec.get("assigned_codes"),
                       sentiment=sentiment or rec.get("sentiment"), needs_review=False, corrected=True)
            if rid in analysis.get("review_queue", []):
                analysis["review_queue"].remove(rid)
        self.send_json_response({"status": "success", "saved": saved, "corrections": len(get_feedback_store())})

    def coder_review_queue(self):
        analysis = SESSION.get("open_feedback_analysis") or {}
        queue = set(analysis.get("review_queue", []))
        items = [{"response_id": r["response_id"], "text": r.get("raw_text", ""), "themes": r.get("assigned_themes", []),
                  "sentiment": r.get("sentiment"), "confidence": r.get("confidence"), "reasons": r.get("reasons", [])}
                 for r in analysis.get("records", []) if r.get("response_id") in queue][:200]
        options = []
        cf_id = analysis.get("codeframe_id")
        if cf_id:
            try:
                cf = load_codeframe(cf_id)
                options = [{"code_id": c["code_id"], "label": c["label"], "subnet": t["subnet"]}
                           for t in cf["topics"] for c in t["codes"].values()]
            except CodeframeError:
                options = []
        self.send_json_response({"status": "success", "codeframe_id": cf_id, "count": len(queue), "items": items, "options": options})

    def stream_export_file(self, filename: str, mime_type: str):
        """Streams generated file fresh on demand, eliminating stale caching (CS-N03)."""
        suffix = os.path.splitext(filename)[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_f:
            tmp_path = tmp_f.name

        try:
            self.generate_export_artifacts(filename, tmp_path)
            if os.path.exists(tmp_path):
                with open(tmp_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(500, f"Failed to generate export file: {filename}")
        except NotImplementedError as nie:
            self.send_error(501, str(nie))
        except ValueError as ve:
            self.send_error(400, str(ve))
        except Exception as e:
            logging.exception(f"Export error: {e}")
            self.send_error(500, f"Export error: {e}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def generate_export_artifacts(self, filename: str, target_path: str):
        """Generates export file from current session data."""
        if SESSION["df"] is None:
            load_bundled_sample()

        diag = SESSION["weight_diagnostics"] or {}
        n = len(SESSION["df"]) if SESSION["df"] is not None else 0
        neff = diag.get("kish_n_eff", float(n))
        eff = diag.get("weighting_efficiency_pct", 100.0)
        weighted_n = round(float(SESSION["weights"].sum()), 1) if SESSION.get("weights") is not None else float(n)

        if "Banner_Book" in filename:
            tables = SESSION.get("last_tabulation")
            if not tables:
                raise ValueError("Build at least one table first.")
            fdr_mode = "Benjamini-Hochberg False Discovery Rate (FDR)" if SESSION.get("fdr_enabled", True) else "None (Uncorrected)"
            metadata = {
                "date_range": SESSION.get("field_dates") or "N/A",
                "unweighted_n": n,
                "weighted_n": weighted_n,
                "effective_n": neff,
                "efficiency_pct": eff,
                "fdr_correction": fdr_mode
            }
            generate_excel_banner_book(target_path, SESSION.get("filename", "Consumer Study"), tables, metadata)
        elif "Snapshot" in filename:
            data = build_snapshot_data()
            generate_customer_voice_snapshot_html(target_path, data)
        elif "Thesis" in filename:
            raise NotImplementedError("Thesis Chapter 4 Package is currently under calibration and disabled until dynamic inference is certified.")

    def handle_save_to_downloads(self, path: str):
        """Handles saving deliverable files directly to user's ~/Downloads directory."""
        downloads_dir = get_downloads_dir()

        if path == "/api/export/save-to-downloads":
            if not SESSION.get("last_tabulation"):
                self.send_json_response({"status": "error", "message": "Build at least one table first."}, 400)
                return
            target_file = os.path.join(downloads_dir, "ClearSight_Agency_Banner_Book.xlsx")
            self.generate_export_artifacts("ClearSight_Agency_Banner_Book.xlsx", target_file)
            safe_reveal_in_finder(target_file)
            self.send_json_response({
                "status": "success",
                "message": "Banner Book saved to Downloads folder.",
                "path": target_file,
                "filename": "ClearSight_Agency_Banner_Book.xlsx"
            })
        elif path == "/api/export/save-snapshot-to-downloads":
            target_file = os.path.join(downloads_dir, "ClearSight_Customer_Voice_Snapshot_A4.html")
            self.generate_export_artifacts("ClearSight_Customer_Voice_Snapshot_A4.html", target_file)
            safe_reveal_in_finder(target_file)
            self.send_json_response({
                "status": "success",
                "message": "A4 Snapshot saved to Downloads folder.",
                "path": target_file,
                "filename": "ClearSight_Customer_Voice_Snapshot_A4.html"
            })
        elif path == "/api/export/save-thesis-to-downloads":
            self.send_json_response({
                "status": "error",
                "message": "Thesis Chapter 4 Package is currently under calibration and disabled until dynamic inference is certified."
            }, 501)
            return
            target_html = os.path.join(downloads_dir, "ClearSight_Thesis_Chapter_4_Package.html")
            target_xlsx = os.path.join(downloads_dir, "ClearSight_Thesis_Chapter_4_Tables.xlsx")
            self.generate_export_artifacts("ClearSight_Thesis_Chapter_4_Package.html", target_html)
            self.generate_export_artifacts("ClearSight_Thesis_Chapter_4_Tables.xlsx", target_xlsx)
            safe_reveal_in_finder(target_html)
            self.send_json_response({
                "status": "success",
                "message": "Thesis Chapter 4 Package saved to Downloads folder.",
                "path": target_html,
                "filename": "ClearSight_Thesis_Chapter_4_Package.html"
            })

    def execute_tabulation(self, df, banner_cols, stubs, confidence=95, fdr_enabled=True, metric="pct"):
        """Computes cross-tabulation table with rigorous dual significance testing on real microdata."""
        from engine.tabulation_engine import build_crosstab_table

        conf_float = 0.95 if int(confidence) == 95 else (0.90 if int(confidence) == 90 else 0.99)
        weights = SESSION.get("weights")

        # Apply active hygiene quarantine filters to analytical sample (CS-045)
        flag_col = "__is_flagged" if df is not None and "__is_flagged" in df.columns else ("_is_flagged" if df is not None and "_is_flagged" in df.columns else None)
        reason_col = "__flag_reasons" if df is not None and "__flag_reasons" in df.columns else ("_flag_reasons" if df is not None and "_flag_reasons" in df.columns else None)

        if df is not None and flag_col and reason_col:
            cond = pd.Series(True, index=df.index)
            if SESSION.get("quarantine_straight_liners", True):
                cond &= ~df[reason_col].str.contains("Straight-liner", na=False)
            if SESSION.get("quarantine_speeders", True):
                cond &= ~df[reason_col].str.contains("Speeder", na=False)
            if not cond.all():
                df = df[cond].copy()
                if weights is not None:
                    weights = weights[cond.to_numpy()]

        tables = []
        for stub_name in stubs:
            t = build_crosstab_table(
                df=df,
                stub_name=stub_name,
                banner_cols_input=banner_cols,
                weights=weights,
                confidence_level=conf_float,
                fdr_enabled=fdr_enabled,
                metric=metric
            )
            tables.append(t)
        return tables

    def build_default_tables(self):
        """Constructs default agency tables using real dataset metrics."""
        from engine.tabulation_engine import build_crosstab_table
        df = SESSION.get("df")
        if df is None:
            load_bundled_sample()
            df = SESSION.get("df")

        weights = SESSION.get("weights")
        banner_var = "Region" if "Region" in df.columns else (df.columns[1] if len(df.columns) > 1 else df.columns[0])
        candidate_stubs = [
            c for c in df.columns 
            if not str(c).startswith("__") 
            and not re.search(r'(?i)(?:id|_id|timestamp|submitted|date|duration)$', str(c))
            and SESSION.get("schema", {}).get(c, {}).get("type") in ("single_select", "rating_scale", "multi_select")
        ]
        stub_var = "Brand_Preference" if "Brand_Preference" in df.columns else (candidate_stubs[0] if candidate_stubs else df.columns[0])

        return [
            build_crosstab_table(df, stub_var, ["Total", banner_var], weights=weights)
        ]


def run_server():
    # Load sample on server boot
    load_bundled_sample()
    server_address = ('127.0.0.1', PORT)
    httpd = ThreadingHTTPServer(server_address, ClearSightRequestHandler)
    print(f"[*] ClearSight Analytical Server active on http://127.0.0.1:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server shutdown cleanly.")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
