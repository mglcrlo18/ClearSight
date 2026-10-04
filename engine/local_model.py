"""
Optional local-model fallback for coder v2 (step 5).

Design constraints
------------------
* No heavy default dependencies: nothing here is imported by the default coder path. The
  embedding backend (``model2vec``) is imported lazily, only when a fallback is explicitly built.
* Offline only: the model is loaded from a local directory with ``HF_HUB_OFFLINE=1``; text never
  leaves the machine.
* PII is scrubbed by ``Coder.code`` *before* the fallback sees any text.
* The fallback is consulted only when the rules produced no topic or a neutral sentiment.

Spec strings accepted by :func:`build_fallback`::

    "none" | ""                                   -> None (rules only)
    "model2vec:<model_dir>"                       -> topic centroids only
    "model2vec:<model_dir>|head=<weights.npz>"    -> topic centroids + sentiment head

The sentiment head is a multinomial logistic regression over L2-normalised embeddings, trained by
``scripts/train_sentiment_head.py`` on public CC BY 4.0 data (SentiTaglish Products and Services;
FiReCS, Cosme & De Leon). Client data is never used to train it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

SENT_CLASSES = ("neg", "neutral", "pos", "mixed")


@runtime_checkable
class LocalClassifier(Protocol):
    def predict(self, text: str, coder) -> Optional[dict]:
        """Return ``{"sentiment", "sentiment_score", "topic", "topic_score"}`` or ``None``."""


class NullClassifier:
    """Explicit no-op fallback."""

    def predict(self, text: str, coder) -> Optional[dict]:
        return None


def _safe_dir(p: str) -> Path:
    path = Path(os.path.realpath(os.path.expanduser(p)))
    if not path.is_dir():
        raise ValueError(f"model directory not found: {p}")
    return path


class EmbeddingFallback:
    """Nearest-centroid topics + optional linear sentiment head over static embeddings."""

    def __init__(self, embed, head: Optional[dict] = None, min_topic_sim: float = 0.35):
        self._embed = embed          # callable: list[str] -> np.ndarray (n, d)
        self._head = head
        self._min_topic_sim = min_topic_sim
        self._centroids: dict = {}   # codeframe id -> (topic ids, matrix)

    @staticmethod
    def _norm(m):
        import numpy as np
        return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)

    def _topic_matrix(self, coder):
        import numpy as np
        cid = coder.cf.get("id", "")
        if cid not in self._centroids:
            ids, rows = [], []
            for t in coder.cf["topics"]:
                texts = list(t.get("exemplars", [])) + [t.get("subnet", "")] + list(t.get("keywords", []))[:40]
                texts = [x for x in texts if x]
                if not texts:
                    continue
                v = self._norm(self._embed(texts)).mean(axis=0)
                ids.append(t["id"])
                rows.append(v)
            self._centroids[cid] = (ids, self._norm(np.vstack(rows)) if rows else None)
        return self._centroids[cid]

    def predict(self, text: str, coder) -> Optional[dict]:
        import numpy as np
        if not text or not text.strip():
            return None
        e = self._norm(self._embed([text]))
        out: dict = {}
        ids, mat = self._topic_matrix(coder)
        if mat is not None:
            sims = mat @ e[0]
            k = int(np.argmax(sims))
            if sims[k] >= self._min_topic_sim:
                out.update(topic=ids[k], topic_score=float(sims[k]))
        if self._head is not None:
            z = e @ self._head["W"] + self._head["b"]
            z = z - z.max(axis=1, keepdims=True)
            p = np.exp(z)[0]
            p /= p.sum()
            k = int(np.argmax(p))
            out.update(sentiment=self._head["classes"][k], sentiment_score=float(p[k]))
        return out or None


def load_head(path: str) -> dict:
    import numpy as np
    p = Path(os.path.realpath(os.path.expanduser(path)))
    if p.suffix != ".npz" or not p.is_file():
        raise ValueError("sentiment head must be an existing .npz file")
    with np.load(p, allow_pickle=False) as z:   # no pickle: CWE-502
        return {"W": z["W"], "b": z["b"], "classes": [str(c) for c in z["classes"]]}


def build_fallback(spec: Optional[str]):
    """Build a fallback from a spec string; returns ``None`` for rules-only."""
    if not spec or spec.strip().lower() in ("none", "off", "0"):
        return None
    kind, _, rest = spec.partition(":")
    if kind != "model2vec":
        raise ValueError(f"unknown fallback kind: {kind!r}")
    parts = rest.split("|")
    model_dir = _safe_dir(parts[0])
    head = None
    for extra in parts[1:]:
        k, _, v = extra.partition("=")
        if k == "head":
            head = load_head(v)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    try:
        from model2vec import StaticModel  # optional dependency
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("model2vec is not installed; pip install model2vec to enable the fallback") from exc
    model = StaticModel.from_pretrained(str(model_dir))
    return EmbeddingFallback(lambda texts: model.encode(list(texts)), head=head)
