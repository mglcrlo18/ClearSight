#!/usr/bin/env python3
"""
Coder evaluation harness + release gate (coder v1 vs v2, with an ablation ladder).

The labelled test set is client-derived and is NOT in the repo. Point the harness at it with
``--testset PATH`` or ``CLEARSIGHT_CODER_TESTSET``. Without it, CI runs the synthetic set in
``tests/data/coder_synthetic_eval.csv`` (invented sentences, safe to publish).

Overfitting guard: rows are split 70/30 into dev / held-out, stratified by language group x domain
x sentiment, using a fixed salted SHA-256 order of the row id (no RNG state, reproducible
anywhere). Tune on ``--split dev`` only; report ``--split heldout``.

Gate thresholds are the prior passes' release gate: Other <= 15 %, in-scope theme agreement >= 80 %,
theme kappa >= 0.70, sentiment accuracy >= 85 %.

Output is aggregate only: no verbatim is written unless ``--rows-out`` is given (keep that file
internal).
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEED = "clearsight-coder-v2-20261004"
GATE = {"other_pct": ("<=", 15.0), "theme_agree_pct": (">=", 80.0), "theme_kappa": (">=", 0.70), "sent_acc_pct": (">=", 85.0)}
OTHER = "General Feedback / Other"
UNCODED_LABELS = {OTHER, "Needs Review", "General Favorable Comment", "General Unfavorable Comment"}
NEG_RX = re.compile(r"\b(hindi|di|wala|walang|not|never|ayaw|kulang|dili|indi|hnd|wla)\b", re.I)


def load_rows(path: str) -> list[dict]:
    lines = open(path, encoding="utf-8-sig").read().splitlines(True)
    return list(csv.DictReader(io.StringIO("".join(l for l in lines if not l.startswith("#")))))


def lang_group(lg: str) -> str:
    return "Tagalog" if lg == "Tagalog" else "Taglish" if "Taglish" in lg else "Bisaya" if "Bisaya" in lg else "English"


def split_rows(rows: list[dict], frac: float = 0.7):
    strata = collections.defaultdict(list)
    for r in rows:
        strata[(lang_group(r.get("language_mix", "")), r.get("domain", ""), r.get("sentiment", ""))].append(r)
    dev, ho = [], []
    for _, L in sorted(strata.items()):
        L = sorted(L, key=lambda r: hashlib.sha256((SEED + r["id"]).encode()).hexdigest())
        n = round(len(L) * frac)
        dev += L[:n]
        ho += L[n:]
    return dev, ho


def expected_theme(r: dict) -> str:
    """Same in-scope mapping as the prior passes' eval_coder.py (price / delivery / packaging)."""
    if r.get("expected_theme"):
        return r["expected_theme"]
    lab = r.get("expected_label", "").lower()
    sub = r.get("expected_subnet", "").lower()
    if re.search(r"reduce prices|increasing prices|rising prices|high price", lab):
        return "Affordable / High Value (Sulit)" if r["sentiment"] == "pos" else "Expensive / High Pricing Friction"
    if re.search(r"not too expensive|not expensive|cheap|affordab|meets the budget|saves|savings|value for money|sulit|budget-friendly|lower price|discount|promo|for less", lab) and not re.search(r"not affordable|no budget|no promo|rarely offers promo", lab):
        return "Affordable / High Value (Sulit)"
    if re.search(r"expensive|not affordable|does not suit budget|increasing prices|high (taxes|fines|transportation fares|prices|electricity|estate)|costly|no money to buy|no budget", lab) or (("expensive" in sub) and "cheap" not in lab):
        return "Expensive / High Pricing Friction"
    if re.search(r"takes too long to be delivered|deliver(ed|y) (is )?(slow|late)", lab):
        return "Slow Logistics / Delivery Delay"
    if re.search(r"cap easily gets broken|damaged packag|leak", lab):
        return "Damaged / Defective Packaging"
    return "OUT_OF_SCOPE"


def kappa(a, b):
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / n / n
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


# ---------------------------------------------------------------------------
# Coders under test
# ---------------------------------------------------------------------------
def v1_predict(text: str, domain: str):
    from engine.taglish_nlp import analyze_taglish_verbatim
    ms = analyze_taglish_verbatim(text)
    themes = [m["theme"] for m in ms]
    pols = {("pos" if m["net"].startswith("Positive") else "neg" if m["net"].startswith("Negative") else None) for m in ms} - {None}
    sent = "neutral" if not pols else "mixed" if pols == {"pos", "neg"} else pols.pop()
    return themes, sent, False


STEPS = {
    "S0": "coder v1 (b9bad0c + Pass 5 patch)",
    "S1": "v2 engine + normaliser/stemmer, v1 themes (legacy_v1 codeframe), no negation scope, no general lexicon",
    "S2": "S1 + negation scope with idiom exceptions",
    "S3": "S2 + decoupled sentiment lexicon (TL/EN/Bisaya) + contrast weighting + mixed detection",
    "S4": "S3 + default consumer / governance codeframes loaded from files",
    "S5": "S4 + confidence + Needs-review queue (routing only; Needs review counts as uncoded)",
    "S6": "S5 + optional local embedding fallback (only if the extra is installed)",
    "REF_PRIOR": "REFERENCE ONLY: S5, and every neutral answer is relabelled with the dev split's majority polar class",
    "S7": "S5 + feedback model trained on the dev split's labels as simulated analyst corrections (optimistic)",
}


def make_v2(step: str, fallback=None, feedback=None, prior=None):
    from engine.coder_v2 import Coder, CoderConfig
    base = "S5" if step in ("REF_PRIOR", "S7") else step
    cfg = dict(stem=True, negation=base >= "S2", contrast=base >= "S3", sentiment_lexicon=base >= "S3",
               review_queue=base >= "S5")
    coders = {}

    def predict(text, domain):
        cf = "legacy_v1" if base < "S4" else ("governance_default" if "governance" in domain else "consumer_default")
        if cf not in coders:
            c = CoderConfig(**cfg)
            if step == "S6" and fallback is not None:
                c.fallback = fallback
            if step == "S7" and feedback is not None:
                c.feedback = feedback
            coders[cf] = Coder(cf, c)
        r = coders[cf].code(text)
        sent = r["sentiment"]
        if step == "REF_PRIOR" and sent == "neutral" and prior:
            sent = prior
        return [t["theme"] for t in r["themes"]], sent, r["needs_review"]
    return predict


def build_feedback(dev_rows):
    """Simulated analyst corrections from the dev split (sentiment labels only)."""
    from engine.coder_feedback import FeedbackStore
    fs = FeedbackStore(persist=False, min_examples=20)
    for r in dev_rows:
        try:
            fs.add(r["verbatim"], sentiment=r["sentiment"] if r["sentiment"] in ("pos", "neg", "neutral", "mixed") else None)
        except ValueError:
            pass
    fs.lookup = lambda text: None   # measure the learnt model only, not exact-text recall
    return fs


# ---------------------------------------------------------------------------
# Extra slices (separate from the client held-out headline)
# ---------------------------------------------------------------------------
_TEXT_COLS = ("verbatim", "text", "masked_text", "verbatim_masked", "segment_text", "utterance", "review")
_SENT_COLS = ("sentiment", "sentiment_label", "polarity", "label")
_SENT_MAP = {"pos": "pos", "positive": "pos", "favorable": "pos", "neg": "neg", "negative": "neg", "unfavorable": "neg",
             "neutral": "neutral", "neu": "neutral", "mixed": "mixed", "mix": "mixed"}


def load_extra(path: str) -> list[dict]:
    """Tolerant loader for an extra labelled slice (e.g. the masked FGD governance set).

    Needs a text column; a sentiment column is optional per row (blank = not scored for sentiment).
    Uses a ``split`` column (dev / heldout) when present, and a ``theme_ids`` column (``|``-separated
    codeframe topic ids; ``ext_<id>`` matches topic ``<id>`` when the codeframe has it)."""
    rows = load_rows(path)
    if not rows:
        return []
    cols = {c.lower(): c for c in rows[0].keys()}
    tc = next((cols[c] for c in _TEXT_COLS if c in cols), None)
    sc = next((cols[c] for c in _SENT_COLS if c in cols), None)
    th_c = next((cols[c] for c in ("theme_ids", "theme_label") if c in cols), None)
    if not tc:
        raise SystemExit(f"extra slice {path}: needs a text column {_TEXT_COLS}")
    out = []
    for i, r in enumerate(rows):
        if not str(r[tc]).strip():
            continue
        s = _SENT_MAP.get(str(r[sc]).strip().lower(), "") if sc else ""
        th_val = r.get(th_c, "") if th_c else ""
        out.append({"id": r.get(cols.get("id", ""), "") or f"x{i}", "verbatim": r[tc], "sentiment": s, "domain": "governance",
                    "language_mix": r.get(cols.get("language_mix", ""), "") or r.get(cols.get("language", ""), "") or "Taglish",
                    "expected_theme": r.get(cols.get("expected_theme", ""), "") or "OUT_OF_SCOPE",
                    "theme_ids": [t for t in (th_val or "").split("|") if t],
                    "split": (r.get(cols.get("split", ""), "") or "heldout").strip().lower()})
    return out


def extra_metrics(rows, step, fb, codeframe="governance_default"):
    """Uncoded share on all rows; sentiment on labelled rows only; topic agreement on rows whose
    question topic is in the codeframe (a match = any predicted theme from that topic)."""
    from engine.codeframe_loader import load_codeframe
    cf = load_codeframe(codeframe)
    topic_of = {c["label"]: t["id"] for t in cf["topics"] for c in t["codes"].values()}
    known = set(topic_of.values())
    pred = v1_predict if step == "S0" else make_v2(step, fb)
    n = unc = 0
    sent = []
    th, th_ext = [], []
    for r in rows:
        themes, s, _ = pred(r["verbatim"], "governance")
        n += 1
        unc += all(t in UNCODED_LABELS for t in themes)
        if r["sentiment"]:
            sent.append((r["sentiment"], s))
        got = {topic_of.get(t) for t in themes}
        core = {t for t in r["theme_ids"] if not t.startswith("ext_")} & known
        ext = {t[4:] for t in r["theme_ids"] if t.startswith("ext_")} & known
        if core:
            th.append(bool(got & core))
        if ext:
            th_ext.append(bool(got & ext))
    k_s = sum(a == b for a, b in sent)
    rec = {c: (round(100 * sum(1 for a, b in sent if a == c and b == c) / max(1, sum(1 for a, _ in sent if a == c)), 1),
               sum(1 for a, _ in sent if a == c)) for c in ("pos", "neg")}
    return {"n": n, "uncoded_pct": round(100 * unc / n, 1) if n else None, "uncoded_ci": wilson(unc, n),
            "sent_n": len(sent), "sent_acc_pct": round(100 * k_s / len(sent), 1) if sent else None, "sent_ci": wilson(k_s, len(sent)),
            "sent_recall": rec, "topic_n": len(th), "topic_agree_pct": round(100 * sum(th) / len(th), 1) if th else None,
            "topic_ci": wilson(sum(th), len(th)),
            "ext_topic_n": len(th_ext), "ext_topic_agree_pct": round(100 * sum(th_ext) / len(th_ext), 1) if th_ext else None}


def eval_extra(path, steps, fb):
    rows = load_extra(path)
    out = {"file": os.path.basename(path), "n": len(rows), "splits": {}}
    for sp in ("dev", "heldout"):
        sel = [r for r in rows if r["split"] == sp]
        if not sel:
            continue
        out["splits"][sp] = {}
        for st in steps:
            if st in ("REF_PRIOR", "S7", "S1", "S2", "S3") or (st == "S6" and fb is None):
                continue
            out["splits"][sp][st] = extra_metrics(sel, st, fb)
    return out


def eval_firecs(path, fb):
    """Public FiReCS test split (CC BY 4.0, Cosme & De Leon): 3-class sentiment accuracy, reported separately."""
    fi = {"0": "neg", "0.0": "neg", "1": "neutral", "1.0": "neutral", "2": "pos", "2.0": "pos"}
    rows = [{"id": str(i), "verbatim": r["review"], "sentiment": fi[str(r["label"]).strip()], "domain": "consumer",
             "language_mix": "Taglish"} for i, r in enumerate(load_rows(path)) if str(r["label"]).strip() in fi]
    out = {"file": os.path.basename(path), "n": len(rows), "note": "3-class (no Mixed gold); v2 mixed counts as wrong"}
    for st in ("S0", "S5") + (("S6",) if fb is not None else ()):
        pred = v1_predict if st == "S0" else make_v2(st, fb)
        m = metrics(evaluate(rows, pred))
        out[st] = {k: m[k] for k in ("sent_acc_pct", "sent_ci", "sent_kappa", "sent_recall", "precision_when_polar")}
    return out


def evaluate(rows, predict, rows_out=None):
    res = []
    for r in rows:
        themes, sent, needs = predict(r["verbatim"], r.get("domain", ""))
        et = expected_theme(r)
        prim = et if et in themes else next((t for t in themes if t not in UNCODED_LABELS), OTHER)
        res.append(dict(id=r["id"], g=lang_group(r.get("language_mix", "")), dom=r.get("domain", ""), es=r["sentiment"], s=sent,
                        themes=themes, et=et, prim=prim, needs=needs,
                        uncoded=all(t in UNCODED_LABELS for t in themes),
                        other_only=themes == [OTHER],
                        hum_other=bool(re.search(r"\bother|none|no answer|don.t know|no particular", r.get("expected_label", ""), re.I)),
                        neg=bool(NEG_RX.search(r["verbatim"])), v=r["verbatim"]))
    if rows_out:
        with open(rows_out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "group", "domain", "expected_sent", "pred_sent", "expected_theme", "themes", "needs_review", "verbatim"])
            for x in res:
                w.writerow([x["id"], x["g"], x["dom"], x["es"], x["s"], x["et"], "; ".join(x["themes"]), x["needs"], x["v"]])
    return res


def metrics(L):
    n = len(L)
    if n == 0:
        return {"n": 0}
    ins = [x for x in L if x["et"] != "OUT_OF_SCOPE"]
    k_unc = sum(x["uncoded"] for x in L)
    k_s = sum(x["s"] == x["es"] for x in L)
    k_t = sum(x["prim"] == x["et"] for x in ins)
    rec = {k: (round(100 * sum(1 for x in L if x["es"] == k and x["s"] == k) / max(1, sum(1 for x in L if x["es"] == k)), 1),
               sum(1 for x in L if x["es"] == k)) for k in ("pos", "neg", "neutral", "mixed")}
    polar = [x for x in L if x["s"] != "neutral"]
    negr = [x for x in L if x["neg"]]
    return dict(
        n=n,
        other_pct=round(100 * k_unc / n, 1), other_ci=wilson(k_unc, n),
        other_label_only_pct=round(100 * sum(x["other_only"] for x in L) / n, 1),
        needs_review_pct=round(100 * sum(x["needs"] for x in L) / n, 1),
        human_other_pct=round(100 * sum(x["hum_other"] for x in L) / n, 1),
        theme_n=len(ins), theme_agree_pct=round(100 * k_t / len(ins), 1) if ins else None, theme_ci=wilson(k_t, len(ins)),
        theme_kappa=kappa([x["et"] for x in ins], [x["prim"] for x in ins]),
        sent_acc_pct=round(100 * k_s / n, 1), sent_ci=wilson(k_s, n),
        sent_kappa=kappa([x["es"] for x in L], [x["s"] for x in L]),
        sent_recall=rec,
        precision_when_polar=(len(polar), round(100 * sum(x["s"] == x["es"] for x in polar) / len(polar), 1) if polar else None),
        negator_rows=(len(negr), round(100 * sum(x["s"] == x["es"] for x in negr) / len(negr), 1) if negr else None),
    )


def gate(m):
    out = {}
    for k, (op, t) in GATE.items():
        v = m.get(k)
        out[k] = v is not None and (v <= t if op == "<=" else v >= t)
    return out


def report(res):
    groups = {"Overall": res}
    for g in ("Tagalog", "Taglish", "Bisaya", "English"):
        groups[g] = [x for x in res if x["g"] == g]
    for d in sorted({x["dom"] for x in res}):
        groups["domain:" + d] = [x for x in res if x["dom"] == d]
    out = {}
    for k, L in groups.items():
        m = metrics(L)
        if m.get("n"):
            m["gate"] = gate(m)
        out[k] = m
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--testset", default=os.environ.get("CLEARSIGHT_CODER_TESTSET") or str(ROOT / "tests/data/coder_synthetic_eval.csv"))
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="heldout")
    ap.add_argument("--steps", default="S0,S1,S2,S3,S4,S5")
    ap.add_argument("--fallback", default="", help="optional: 'model2vec:<local model dir>' for step S6")
    ap.add_argument("--out", default="")
    ap.add_argument("--rows-out", default="", help="INTERNAL: per-row CSV (contains verbatims)")
    ap.add_argument("--extra", action="append", default=[], help="NAME=PATH extra labelled slice (e.g. fgd_governance=...csv)")
    ap.add_argument("--firecs-test", default="", help="optional public FiReCS test CSV, reported separately")
    a = ap.parse_args(argv)
    rows = load_rows(a.testset)
    dev, ho = split_rows(rows)
    sel = {"dev": dev, "heldout": ho, "all": rows}[a.split]
    fb = None
    if a.fallback:
        from engine.local_model import build_fallback
        fb = build_fallback(a.fallback)
    results = {"testset": os.path.basename(a.testset), "split": a.split, "n": len(sel), "seed": SEED, "gate": GATE, "steps": {}}
    for st in a.steps.split(","):
        st = st.strip()
        if st == "S6" and fb is None:
            continue
        if st == "REF_PRIOR":
            c = collections.Counter(r["sentiment"] for r in dev if r["sentiment"] in ("pos", "neg"))
            pred = make_v2(st, prior=c.most_common(1)[0][0] if c else None)
        elif st == "S7":
            pred = make_v2(st, feedback=build_feedback(dev))
        else:
            pred = v1_predict if st == "S0" else make_v2(st, fb)
        res = evaluate(sel, pred, rows_out=(a.rows_out.replace(".csv", f"_{st}.csv") if a.rows_out else None))
        results["steps"][st] = {"desc": STEPS[st], "groups": report(res)}
        o = results["steps"][st]["groups"]["Overall"]
        print(f"{st}: other={o['other_pct']} theme={o['theme_agree_pct']} (n={o['theme_n']}) tk={o['theme_kappa']} "
              f"sent={o['sent_acc_pct']} sk={o['sent_kappa']} rec={o['sent_recall']} ppol={o['precision_when_polar']} neg={o['negator_rows']}")
    steps = [x.strip() for x in a.steps.split(",")]
    for spec in a.extra:
        name, _, path = spec.partition("=")
        if path and os.path.exists(path):
            results.setdefault("extra", {})[name] = eval_extra(path, steps, fb)
            for sp, d in results["extra"][name]["splits"].items():
                for st, m in d.items():
                    print(f"extra {name} [{sp}] {st}: n={m['n']} uncoded={m['uncoded_pct']} sent={m['sent_acc_pct']} (n={m['sent_n']}) "
                          f"rec={m['sent_recall']} topic={m['topic_agree_pct']} (n={m['topic_n']}) ext_topic={m['ext_topic_agree_pct']} (n={m['ext_topic_n']})")
        else:
            results.setdefault("extra", {})[name] = {"status": "pending: file not found", "file": os.path.basename(path)}
            print(f"extra {name}: pending (file not found)")
    if a.firecs_test:
        results["firecs_test"] = eval_firecs(a.firecs_test, fb)
        print("firecs_test:", {k: v["sent_acc_pct"] for k, v in results["firecs_test"].items() if isinstance(v, dict)})
    if a.out:
        Path(a.out).write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    return results


if __name__ == "__main__":
    main()
