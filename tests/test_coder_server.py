"""Coder v2 server endpoints over real HTTP on an ephemeral port (synthetic data only)."""
from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pandas as pd
import pytest

import server
from engine.ingestion import autodetect_schema


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEARSIGHT_DATA", str(tmp_path))
    monkeypatch.setenv("CLEARSIGHT_CODER_TELEMETRY", "0")
    monkeypatch.setattr(server, "_FEEDBACK_STORE", None)
    df = pd.DataFrame({"Respondent_ID": [f"R{i}" for i in range(6)],
                       "Open_End_Feedback": ["Sobrang sulit at mabango", "Ang mahal na ng presyo",
                                             "<script>alert(1)</script> asdf qwer", "Hindi mabango",
                                             "Tawagan 09171234567 mabango", "zxcv lkjh poiu"]})
    server.SESSION["df"] = df
    server.SESSION["schema"] = autodetect_schema(df)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ClearSightRequestHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def req(port, method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    data = json.dumps(body).encode() if body is not None else None
    c.request(method, path, body=data, headers={"Host": "127.0.0.1", "Content-Type": "application/json"})
    r = c.getresponse()
    out = r.status, json.loads(r.read() or b"{}")
    c.close()
    return out


def test_code_open_ends_v2_default_and_v1_flag(live):
    st, d = req(live, "POST", "/api/code-open-ends", {"column": "Open_End_Feedback"})
    assert st == 200 and d["status"] == "success" and d["coder"] == server.CODER_DEFAULT
    assert d["coder_version"].startswith("2") and d["codeframe_id"] == "consumer_default"
    assert "09171234567" not in json.dumps(d)
    assert d["review_queue_count"] >= 1
    st, d1 = req(live, "POST", "/api/code-open-ends", {"column": "Open_End_Feedback", "coder": "v1"})
    assert st == 200 and d1["coder"] == "v1" and d1["codeframe"]
    st, _ = req(live, "POST", "/api/code-open-ends", {"coder": "v9"})
    assert st == 400


@pytest.mark.parametrize("cf", ["../../etc/passwd", "/etc/passwd", "..", "nope_missing"])
def test_codeframe_param_rejects_paths(live, cf):
    st, d = req(live, "POST", "/api/code-open-ends", {"column": "Open_End_Feedback", "codeframe": cf})
    assert st == 400 and d["status"] == "error"


def test_governance_codeframe_by_name(live):
    st, d = req(live, "POST", "/api/code-open-ends", {"column": "Open_End_Feedback", "codeframe": "governance_default"})
    assert st == 200 and d["codeframe_id"] == "governance_default"


def test_review_queue_and_feedback_roundtrip(live, tmp_path):
    req(live, "POST", "/api/code-open-ends", {"column": "Open_End_Feedback"})
    st, q = req(live, "GET", "/api/coder/review-queue")
    assert st == 200 and q["count"] >= 1 and q["options"]
    item = q["items"][0]
    code_id = q["options"][0]["code_id"]
    st, f = req(live, "POST", "/api/coder/feedback", {"response_id": item["response_id"], "sentiment": "neg", "code_ids": [code_id]})
    assert st == 200 and f["status"] == "success" and f["corrections"] == 1
    st, q2 = req(live, "GET", "/api/coder/review-queue")
    assert q2["count"] == q["count"] - 1
    assert (tmp_path / "coder_corrections.json").exists()
    # the correction is applied on the next run
    st, d = req(live, "POST", "/api/code-open-ends", {"column": "Open_End_Feedback"})
    rec = next(r for r in d["records"] if r["response_id"] == item["response_id"])
    assert rec["assigned_codes"] == [code_id] and rec["sentiment"] == "neg"


@pytest.mark.parametrize("body", [
    {"response_id": "1", "sentiment": "pos"}, {"response_id": 99999, "sentiment": "pos"},
    {"text": "ok", "sentiment": "great"}, {"text": "ok", "code_ids": "110"}, {"text": "ok"},
    {"text": "ok", "code_ids": [123456]}, {"text": "x" * 6000, "sentiment": "pos"}, [1, 2],
])
def test_feedback_validation(live, body):
    req(live, "POST", "/api/code-open-ends", {"column": "Open_End_Feedback"})
    st, d = req(live, "POST", "/api/coder/feedback", body)
    assert st in (400, 404) and d["status"] == "error"


def test_codeframes_and_telemetry_endpoints(live):
    st, d = req(live, "GET", "/api/coder/codeframes")
    assert st == 200 and "governance_default" in d["codeframes"] and "common_price" not in d["codeframes"]
    st, t = req(live, "GET", "/api/coder/telemetry")
    assert st == 200 and t["local_only"] is True and "counters" in t


def test_feedback_csrf_origin_rejected(live):
    c = http.client.HTTPConnection("127.0.0.1", live, timeout=30)
    c.request("POST", "/api/coder/feedback", body=b'{"text":"ok","sentiment":"pos"}',
              headers={"Host": "127.0.0.1", "Origin": "http://evil.example", "Content-Type": "application/json"})
    assert c.getresponse().status == 403
