"""
Analyst corrections -> coder v2 (step 6).

* Corrections are stored locally in ``$CLEARSIGHT_DATA/coder_corrections.json`` (never sent anywhere).
* Text is PII-scrubbed before anything is stored. The store keeps a salted hash of the normalised
  text (exact-match lookup), the stemmed tokens (for the learnt model), and the analyst's labels;
  it does not keep the raw verbatim.
* ``lookup``: an exact re-occurrence of a corrected answer gets the analyst's labels back.
* ``predict``: once at least ``min_examples`` corrections exist, a multinomial naive Bayes on stems
  proposes a sentiment for answers the rules left neutral / untopiced. It only fills gaps; it never
  overrides a rule decision.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

from engine.taglish_nlp import scrub_pii
from engine.tl_morph import normalize_text, stem, tokenize

SENTIMENTS = ("pos", "neg", "neutral", "mixed")
MAX_CORRECTIONS = 50_000
_SALT = "clearsight-feedback-v1"


def text_key(text: str) -> str:
    norm = " ".join(tokenize(normalize_text(scrub_pii(str(text or "")))))
    return hashlib.sha256((_SALT + norm).encode("utf-8")).hexdigest()[:32]


def default_path() -> Path:
    base = Path(os.environ.get("CLEARSIGHT_DATA") or (Path.home() / ".clearsight"))
    return base / "coder_corrections.json"


class FeedbackStore:
    def __init__(self, path: Optional[os.PathLike] = None, min_examples: int = 20, persist: bool = True):
        self.path = Path(path) if path else default_path()
        self.min_examples = min_examples
        self.persist = persist
        self._lock = threading.Lock()
        self._items: dict = {}
        self._model = None
        if persist and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for it in data.get("items", [])[:MAX_CORRECTIONS]:
                    if isinstance(it, dict) and isinstance(it.get("key"), str):
                        self._items[it["key"]] = it
            except (OSError, ValueError):
                self._items = {}

    # ------------------------------------------------------------------ write
    def add(self, text: str, sentiment: Optional[str] = None, code_ids: Iterable = (), themes: Iterable = (),
            codeframe: str = "") -> dict:
        if sentiment is not None and sentiment not in SENTIMENTS:
            raise ValueError("sentiment must be one of " + ", ".join(SENTIMENTS))
        code_ids = [str(c)[:16] for c in code_ids][:10]
        themes = [str(t)[:160] for t in themes][:10]
        stems = [stem(t) for t in tokenize(scrub_pii(str(text or "")))][:200]
        if not stems:
            raise ValueError("empty text")
        item = {"key": text_key(text), "stems": stems, "sentiment": sentiment, "code_ids": code_ids,
                "themes": themes, "codeframe": str(codeframe)[:64]}
        with self._lock:
            if len(self._items) >= MAX_CORRECTIONS and item["key"] not in self._items:
                raise ValueError("correction store is full")
            self._items[item["key"]] = item
            self._model = None
            self._save()
        return {k: v for k, v in item.items() if k != "stems"}

    def _save(self) -> None:
        if not self.persist:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "items": list(self._items.values())}), encoding="utf-8")
        os.replace(tmp, self.path)

    def __len__(self) -> int:
        return len(self._items)

    # ------------------------------------------------------------------- read
    def lookup(self, text: str) -> Optional[dict]:
        return self._items.get(text_key(text))

    def _train(self):
        docs = [(it["stems"], it["sentiment"]) for it in self._items.values() if it.get("sentiment")]
        if len(docs) < self.min_examples:
            return None
        prior, counts, totals, vocab = Counter(), defaultdict(Counter), Counter(), set()
        for st, lab in docs:
            prior[lab] += 1
            for s in set(st):
                counts[lab][s] += 1
                totals[lab] += 1
                vocab.add(s)
        return prior, counts, totals, len(vocab), len(docs)

    def predict(self, stems: list) -> Optional[dict]:
        with self._lock:
            if self._model is None:
                self._model = self._train() or False
            model = self._model
        if not model:
            return None
        prior, counts, totals, V, n = model
        known = [s for s in set(stems) if any(s in counts[l] for l in prior)]
        if not known:
            return None
        scores = {}
        for lab in prior:
            lp = math.log(prior[lab] / n)
            for s in known:
                lp += math.log((counts[lab][s] + 1) / (totals[lab] + V))
            scores[lab] = lp
        best = max(scores, key=scores.get)
        m = max(scores.values())
        z = sum(math.exp(v - m) for v in scores.values())
        return {"sentiment": best, "score": round(1.0 / z, 3)}

    def stats(self) -> dict:
        return {"corrections": len(self._items),
                "by_sentiment": dict(Counter(it.get("sentiment") for it in self._items.values())),
                "model_active": len([1 for it in self._items.values() if it.get("sentiment")]) >= self.min_examples}
