"""Train the optional sentiment head for the local-model fallback (step 5).

Trains ONLY on public CC BY 4.0 corpora (never on client data):
  * SentiTaglish: Products and Services (ccosme/SentiTaglishProductsAndServices), labels
    1=Negative 2=Neutral 3=Positive 4=Mixed.
  * FiReCS (ccosme/FiReCS) train split, labels 0=Negative 1=Neutral 2=Positive.
Attribution: C. Cosme & M. De Leon, CC BY 4.0. FiReCS test split is held out for reporting.

Usage:
  python scripts/train_sentiment_head.py --model <model2vec dir> --sentitaglish <csv> \
      [--firecs-train <csv>] [--firecs-test <csv>] --out head.npz
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.local_model import SENT_CLASSES  # noqa: E402
from engine.taglish_nlp import scrub_pii  # noqa: E402


def read(path, text_col, label_col, mapping):
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            lab = mapping.get(str(r[label_col]).strip())
            if lab and r[text_col].strip():
                out.append((scrub_pii(r[text_col].strip()), lab))
    return out


def train(X, Y, k, l2=1e-3, epochs=300, lr=0.5):
    W = np.zeros((X.shape[1], k))
    b = np.zeros(k)
    Yo = np.eye(k)[Y]
    for _ in range(epochs):
        Z = X @ W + b
        Z -= Z.max(1, keepdims=True)
        P = np.exp(Z)
        P /= P.sum(1, keepdims=True)
        G = (P - Yo) / len(X)
        W -= lr * (X.T @ G + l2 * W)
        b -= lr * G.sum(0)
    return W, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--sentitaglish", required=True)
    ap.add_argument("--firecs-train")
    ap.add_argument("--firecs-test")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261004)
    a = ap.parse_args()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from model2vec import StaticModel
    m = StaticModel.from_pretrained(a.model)
    st = {"1": "neg", "2": "neutral", "3": "pos", "4": "mixed"}
    fi = {"0": "neg", "0.0": "neg", "1": "neutral", "1.0": "neutral", "2": "pos", "2.0": "pos"}
    data = read(a.sentitaglish, "review", "sentiment", st)
    if a.firecs_train:
        data += read(a.firecs_train, "review", "label", fi)
    test = read(a.firecs_test, "review", "label", fi) if a.firecs_test else []
    test_keys = {t.lower() for t, _ in test}
    seen, dedup = set(), []
    for t, l in data:  # dedupe and drop anything that also appears in FiReCS test
        key = t.lower()
        if key in seen or key in test_keys:
            continue
        seen.add(key)
        dedup.append((t, l))
    rng = np.random.default_rng(a.seed)
    rng.shuffle(dedup)
    X = m.encode([t for t, _ in dedup])
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    Y = np.array([SENT_CLASSES.index(l) for _, l in dedup])
    W, b = train(X, Y, len(SENT_CLASSES))
    np.savez(a.out, W=W, b=b, classes=np.array(SENT_CLASSES))
    rep = {"train_rows": len(dedup), "train_acc": float(((X @ W + b).argmax(1) == Y).mean())}
    if test:
        Xt = m.encode([t for t, _ in test])
        Xt /= np.linalg.norm(Xt, axis=1, keepdims=True) + 1e-9
        Z = Xt @ W + b
        Z[:, SENT_CLASSES.index("mixed")] = -1e9  # FiReCS has no Mixed class
        pred = Z.argmax(1)
        yt = np.array([SENT_CLASSES.index(l) for _, l in test])
        rep.update(firecs_test_rows=len(test), firecs_test_acc=float((pred == yt).mean()))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
