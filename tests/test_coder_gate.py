"""Coder evaluation harness as a CI gate.

* Always: the synthetic set (tests/data/coder_synthetic_eval.csv, invented sentences) must clear
  sanity thresholds, and v2 must beat v1 on it.
* When CLEARSIGHT_CODER_TESTSET points at the labelled client set (kept off the repo), the
  held-out split is scored and v2 must not regress below the frozen held-out baseline
  recorded in Coder_Improvement_Plan.md. Set CLEARSIGHT_CODER_STRICT_GATE=1 to require the full
  release gate (Other <= 15 %, theme >= 80 %, kappa >= 0.70, sentiment >= 85 %).
* No-verbatim-leak: no file in the repo shares a 6-word sequence with the client test set.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from scripts import eval_coder_gate as gate

ROOT = Path(__file__).resolve().parent.parent
SYN = ROOT / "tests" / "data" / "coder_synthetic_eval.csv"
REAL = os.environ.get("CLEARSIGHT_CODER_TESTSET", "")

# frozen held-out floors for the client set (v2 S5 at freeze minus a 2-point tolerance)
HELDOUT_FLOORS = {"other_pct_max": 17.0, "theme_agree_pct": 80.0, "theme_kappa": 0.70, "sent_acc_pct": 58.0}


def test_synthetic_gate():
    res = gate.main(["--testset", str(SYN), "--split", "all", "--steps", "S0,S5"])
    v1 = res["steps"]["S0"]["groups"]["Overall"]
    v2 = res["steps"]["S5"]["groups"]["Overall"]
    assert v2["other_pct"] <= 10.0
    assert v2["theme_agree_pct"] >= 85.0
    assert v2["sent_acc_pct"] >= 85.0
    assert v2["sent_acc_pct"] > v1["sent_acc_pct"] and v2["other_pct"] < v1["other_pct"]


def test_split_is_deterministic_and_stratified():
    rows = gate.load_rows(str(SYN))
    a, b = gate.split_rows(rows)
    c, d = gate.split_rows(list(reversed(rows)))
    assert [r["id"] for r in a] == [r["id"] for r in c]
    assert not {r["id"] for r in a} & {r["id"] for r in b}
    assert len(a) + len(b) == len(rows)


def test_extra_slice_loader(tmp_path):
    p = tmp_path / "fgd.csv"
    p.write_text("id,text,sentiment,split,theme_ids\n1,Walang nagawa sa bayan,negative,dev,track_record\n"
                 "2,Matulungin siya,positive,heldout,helpful\n3,x y z,,dev,ext_unknown\n")
    rows = gate.load_extra(str(p))
    assert [r["split"] for r in rows] == ["dev", "heldout", "dev"]
    out = gate.eval_extra(str(p), ["S0", "S5"], None)
    h = out["splits"]["heldout"]["S5"]
    assert h["sent_acc_pct"] == 100.0 and h["topic_agree_pct"] == 100.0
    d = out["splits"]["dev"]["S5"]
    assert d["sent_n"] == 1 and d["topic_n"] == 1 and d["n"] == 2


@pytest.mark.skipif(not REAL or not os.path.exists(REAL), reason="client test set not available (kept off the repo)")
def test_client_heldout_gate():
    res = gate.main(["--testset", REAL, "--split", "heldout", "--steps", "S0,S5"])
    v1 = res["steps"]["S0"]["groups"]["Overall"]
    v2 = res["steps"]["S5"]["groups"]["Overall"]
    assert v2["sent_acc_pct"] > v1["sent_acc_pct"] and v2["other_pct"] < v1["other_pct"]
    assert v2["other_pct"] <= HELDOUT_FLOORS["other_pct_max"]
    assert v2["theme_agree_pct"] >= HELDOUT_FLOORS["theme_agree_pct"]
    assert v2["theme_kappa"] >= HELDOUT_FLOORS["theme_kappa"]
    assert v2["sent_acc_pct"] >= HELDOUT_FLOORS["sent_acc_pct"]
    if os.environ.get("CLEARSIGHT_CODER_STRICT_GATE") == "1":
        assert all(v2["gate"].values()), v2["gate"]


def _ngrams(text, n=6):
    toks = re.findall(r"[a-zñ0-9]+", text.lower())
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


@pytest.mark.skipif(not REAL or not os.path.exists(REAL), reason="client test set not available (kept off the repo)")
def test_no_client_verbatim_leaks_into_repo():
    grams = set()
    rows = gate.load_rows(REAL)          # skips the "#" provenance header line
    for r in rows:
        grams |= _ngrams(r.get("verbatim", ""))
    assert len(rows) > 100 and grams, "leak check would be vacuous"
    leaks = []
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".json", ".csv", ".md", ".js", ".html", ".yml", ".yaml", ".txt") \
                and ".git" not in p.parts and "__pycache__" not in p.parts:
            hit = _ngrams(p.read_text(encoding="utf-8", errors="ignore")) & grams
            if hit:
                leaks.append((str(p.relative_to(ROOT)), sorted(hit)[:2]))
    assert not leaks, leaks
