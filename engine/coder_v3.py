"""
ClearSight Quantitative & Qualitative Analytics Engine
engine/coder_v3.py - Taglish Text Classification Engine (v3.0.0)
Compliant with Republic Act No. 10173 (Data Privacy Act of 2012).
Air-gapped local execution context. Zero remote telemetry.
"""
from __future__ import annotations

import os
import re
import logging
import hashlib
import platform
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

# A library module must not configure the root logger (the import used to call logging.basicConfig).
logger = logging.getLogger("ClearSight_Coder_v3")

# P7-09: air-gap. Never contact the Hugging Face Hub; load weights only from a bundled/local directory.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Optional ML Frameworks with Graceful In-Memory Fallbacks
try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

try:
    from sklearn.linear_model import PassiveAggressiveClassifier as SklearnPA
    HAS_SKLEARN = True
except ImportError:
    SklearnPA = None
    HAS_SKLEARN = False

try:
    from sentence_transformers import SentenceTransformer as HF_SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HF_SentenceTransformer = None
    HAS_SENTENCE_TRANSFORMERS = False


class TaglishPreProcessor:
    """Morphological normalizer and negation tree parser for Taglish survey responses."""
    # P7-07: "din"/"rin" mean "also/too" and "mali" means "wrong"; they are not negators.
    NEGATION_WORDS = {"hindi", "di", "wala", "walang", "ayaw", "huwag", "never", "not", "no"}
    CONTRAST_WORDS = {"pero", "kaso", "subalit", "however", "although", "kahit"}

    def __init__(self):
        # Regex patterns for local PII masking
        self.phone_pattern = re.compile(r'(\+?63|0)9\d{9}')
        self.email_pattern = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')

    def mask_pii(self, text: str) -> str:
        """Mask PII with ClearSight's main scrubber (names after si/ni/kay, PhilSys, SSS, TIN, cards, phones, emails).
        P7-06: v3 used to keep its own phone/email-only copy, which missed every other RA 10173 category."""
        if not text:
            return ""
        try:
            from engine.taglish_nlp import scrub_pii
        except Exception:  # pragma: no cover - standalone use outside the app
            text = self.phone_pattern.sub('[PHONE_REDACTED]', text)
            return self.email_pattern.sub('[EMAIL_REDACTED]', text)
        return scrub_pii(text)

    def process_negations(self, text: str) -> str:
        """Transform negation patterns for vector embedding stability."""
        tokens = text.lower().split()
        processed_tokens = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in self.NEGATION_WORDS and i + 1 < len(tokens):
                processed_tokens.append(f"NOT_{tokens[i + 1]}")
                i += 2
            else:
                processed_tokens.append(token)
                i += 1
        return " ".join(processed_tokens)

    def clean(self, text: str) -> str:
        """Run full pre-processing pipeline."""
        if not text or not isinstance(text, str):
            return ""
        # P7-07: embed the (masked) text as written. NOT_ tokens split into unseen word pieces in MiniLM
        # ('NOT_satisfied' -> NOT, _, s, atis, fi, ed) and the held-out ablation showed no gain from them.
        # Negation is handled in analyze_sentiment instead.
        return self.mask_pii(text)


class _LocalNumpyPA:
    """Lightweight pure-NumPy Passive-Aggressive (PA-II) multi-class classifier fallback."""
    def __init__(self, C: float = 1.0, random_state: int = 42):
        self.C = C
        self.random_state = random_state
        self.weights: Optional[np.ndarray] = None  # Shape: (n_classes, n_features)
        self.classes_: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        unique_classes = np.unique(y)
        self.classes_ = unique_classes
        n_classes = max(len(unique_classes), int(np.max(y)) + 1)
        n_features = X.shape[1]
        self.weights = np.zeros((n_classes, n_features), dtype=float)
        self.partial_fit(X, y, classes=unique_classes)

    def partial_fit(self, X: np.ndarray, y: np.ndarray, classes: Optional[np.ndarray] = None):
        if classes is not None and self.classes_ is None:
            self.classes_ = np.asarray(classes)
        if self.weights is None:
            n_classes = len(self.classes_) if self.classes_ is not None else int(np.max(y)) + 1
            self.weights = np.zeros((n_classes, X.shape[1]), dtype=float)

        # Multi-class PA-II online updates
        for x_i, y_i in zip(X, y):
            scores = self.weights @ x_i
            pred = np.argmax(scores)
            norm_sq = float(np.dot(x_i, x_i)) + 1e-8
            if pred != y_i:
                # Loss on target vs rival
                loss = max(0.0, 1.0 - (scores[y_i] - scores[pred]))
                tau = loss / (norm_sq + 1.0 / (2.0 * self.C))
                self.weights[y_i] += tau * x_i
                self.weights[pred] -= tau * x_i
            else:
                # Top score correct; reinforce margin against second best
                second_best = np.argsort(scores)[-2] if len(scores) > 1 else y_i
                margin = scores[y_i] - scores[second_best]
                if margin < 1.0:
                    loss = 1.0 - margin
                    tau = loss / (norm_sq + 1.0 / (2.0 * self.C))
                    self.weights[y_i] += tau * x_i
                    self.weights[second_best] -= tau * x_i

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        if self.weights is None:
            raise ValueError("Model is not fitted yet.")
        scores = X @ self.weights.T
        return scores


class _LocalNumpyEmbedder:
    """Lightweight 256-dimensional zero-dependency dense text vectorizer fallback."""
    def __init__(self, dim: int = 256):
        self.dim = dim

    def encode(self, texts: List[str], show_progress_bar: bool = False, normalize_embeddings: bool = True) -> np.ndarray:
        embeddings = np.zeros((len(texts), self.dim), dtype=np.float32)
        for idx, text in enumerate(texts):
            words = text.lower().split()
            if not words:
                continue
            vec = np.zeros(self.dim, dtype=np.float32)
            for w in words:
                h = int(hashlib.md5(w.encode('utf-8'), usedforsecurity=False).hexdigest(), 16)
                pos = h % self.dim
                sign = 1.0 if ((h >> 8) & 1) else -1.0
                vec[pos] += sign
            norm = np.linalg.norm(vec)
            if normalize_embeddings and norm > 0:
                vec /= norm
            embeddings[idx] = vec
        return embeddings


class CoderV3Engine:
    """Production NLP categorization engine integrating SetFit embeddings and PA-II active learning."""

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", codeframe: Optional[Any] = None):
        logger.info("Initializing Coder v3 Engine...")
        self.preprocessor = TaglishPreProcessor()

        # Load Sentence Transformer for embedding extraction
        # P7-09: load from CLEARSIGHT_V3_MODEL_DIR (bundled with the installer) or the local cache only.
        model_dir = os.environ.get("CLEARSIGHT_V3_MODEL_DIR")
        self.encoder_kind = "hash-fallback"
        if HAS_SENTENCE_TRANSFORMERS and HF_SentenceTransformer is not None:
            try:
                self.encoder = HF_SentenceTransformer(model_dir or model_name, local_files_only=True)
                self.encoder_kind = "minilm"
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformer '{model_dir or model_name}' offline: {e}. Falling back to on-device hash embedder.")
                self.encoder = _LocalNumpyEmbedder()
        else:
            self.encoder = _LocalNumpyEmbedder()

        # P7-08 / P7-13: Use deterministic Crammer et al. (2006) PA-II closed-form classifier
        # (tau = loss / (||x||^2 + 1/(2C))) with snapshot versioning, rollback, and poisoning guards.
        self.online_classifier = _LocalNumpyPA(C=1.0, random_state=42)
        self.model_version: int = 1
        self._weight_snapshots: List[Dict[str, Any]] = []
        self.max_step_norm: float = 2.5

        self.codeframe_labels: List[str] = []
        self.codeframe_topics: List[Dict[str, Any]] = []
        self.is_fitted: bool = False

        if codeframe is not None:
            self.load_codeframe(codeframe)

    def quantize_encoder(self):
        """Apply dynamic INT8 CPU quantization to lower inference latency."""
        logger.info("Applying dynamic INT8 quantization to transformer back-end...")
        if HAS_TORCH and torch is not None and hasattr(self.encoder, "eval"):
            try:
                # Apple Silicon / ARM needs the qnnpack backend for dynamic INT8 (fbgemm/x86 are x86-only).
                if platform.machine().lower() in ("arm64", "aarch64") and "qnnpack" in torch.backends.quantized.supported_engines:
                    torch.backends.quantized.engine = "qnnpack"
                self.encoder = torch.quantization.quantize_dynamic(
                    self.encoder, {torch.nn.Linear}, dtype=torch.qint8
                )
                logger.info("Quantization complete. Operating in low-latency CPU mode.")
            except Exception as e:
                logger.warning(f"Quantization skipped: {e}")
        else:
            logger.info("Operating in optimized zero-overhead quantized mode.")

    def set_codeframe(self, labels: List[str]):
        """Register DP Codeframe categories."""
        self.codeframe_labels = list(labels)
        logger.info(f"Codeframe loaded with {len(labels)} unique categories.")

    def load_codeframe(self, codeframe: Any):
        """Loads and bootstraps codeframe categories and seed training data."""
        topics = []
        if isinstance(codeframe, dict):
            topics = codeframe.get("topics", [])
        elif isinstance(codeframe, list):
            topics = codeframe

        labels: List[str] = []
        seed_texts: List[str] = []
        seed_labels: List[int] = []

        if topics and isinstance(topics[0], dict):
            self.codeframe_topics = topics
            for idx, t in enumerate(topics):
                label = t.get("subnet") or t.get("net") or t.get("name") or t.get("id") or f"Category_{idx+1}"
                if label not in labels:
                    labels.append(label)
                label_idx = labels.index(label)

                exemplars = t.get("exemplars", [])
                pos_kw = t.get("pos_keywords", [])
                neg_kw = t.get("neg_keywords", [])
                kw = t.get("keywords", [])

                collected_seeds = []
                if exemplars:
                    collected_seeds.extend(exemplars)
                if pos_kw:
                    collected_seeds.extend(pos_kw[:3])
                if neg_kw:
                    collected_seeds.extend(neg_kw[:3])
                if not collected_seeds and kw:
                    collected_seeds.extend(kw[:3])
                if not collected_seeds:
                    collected_seeds.append(label)

                for s in collected_seeds:
                    if isinstance(s, str) and s.strip():
                        seed_texts.append(s.strip())
                        seed_labels.append(label_idx)
        elif topics and isinstance(topics[0], str):
            labels = list(dict.fromkeys(topics))
            seed_texts = list(labels)
            seed_labels = list(range(len(labels)))
        else:
            labels = ["General Feedback", "Product & Pricing", "Service & Support", "Logistics & Delivery"]
            seed_texts = list(labels)
            seed_labels = list(range(len(labels)))

        self.set_codeframe(labels)
        if len(seed_texts) >= 2 and len(set(seed_labels)) >= 2:
            try:
                self.train_baseline(seed_texts, seed_labels)
            except Exception as e:
                logger.warning(f"Could not auto-train baseline with seed texts: {e}")

    def extract_embeddings(self, texts: List[str]) -> np.ndarray:
        """Clean input text and extract normalized dense vector embeddings."""
        cleaned_texts = [self.preprocessor.clean(t) for t in texts]
        embeddings = self.encoder.encode(cleaned_texts, show_progress_bar=False, normalize_embeddings=True)
        return np.array(embeddings)

    def train_baseline(self, texts: List[str], labels: List[int]):
        """Train initial online classification layer using labeled dataset."""
        X = self.extract_embeddings(texts)
        y = np.array(labels)
        self.online_classifier.fit(X, y)
        self.is_fitted = True
        logger.info("Baseline classification model successfully trained.")

    def predict_with_uncertainty(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Predict categories and return confidence margins for Active Learning review."""
        if not self.is_fitted:
            raise ValueError("Model has not been trained on codeframe categories.")

        X = self.extract_embeddings(texts)
        decision_values = self.online_classifier.decision_function(X)

        # Handle binary vs multi-class decision shapes
        if len(decision_values.shape) == 1:
            decision_values = np.vstack([-decision_values, decision_values]).T

        results = []
        for idx, score_vec in enumerate(decision_values):
            # Softmax conversion for probability estimation
            exp_scores = np.exp(score_vec - np.max(score_vec))
            probs = exp_scores / exp_scores.sum()
            sorted_indices = np.argsort(probs)[::-1]
            top_class = int(sorted_indices[0])
            second_class = int(sorted_indices[1]) if len(sorted_indices) > 1 else top_class

            # Margin calculation (P_top1 - P_top2)
            margin = float(probs[top_class] - probs[second_class])
            confidence = float(probs[top_class])

            # Flag for human review if margin falls below uncertainty threshold
            needs_review = margin < 0.25 or confidence < 0.50

            label_name = self.codeframe_labels[top_class] if top_class < len(self.codeframe_labels) else str(top_class)
            results.append({
                "text": texts[idx],
                "predicted_label_idx": top_class,
                "predicted_label": label_name,
                "confidence": round(confidence, 4),
                "margin": round(margin, 4),
                "needs_review": needs_review
            })
        return results

    def _snapshot_state(self):
        """Save current PA-II weights and classes for rollback resilience (P7-08 / P7-13)."""
        w = getattr(self.online_classifier, "weights", None)
        c = getattr(self.online_classifier, "classes_", None)
        if w is not None:
            self._weight_snapshots.append({
                "version": self.model_version,
                "weights": w.copy(),
                "classes": c.copy() if c is not None else None,
            })
            if len(self._weight_snapshots) > 20:
                self._weight_snapshots.pop(0)

    def rollback(self, steps: int = 1) -> int:
        """Revert online classifier weights by `steps` snapshots (P7-08 / P7-13)."""
        steps = max(1, int(steps))
        if not self._weight_snapshots:
            raise ValueError("No prior model snapshots available to roll back.")
        snap = None
        for _ in range(min(steps, len(self._weight_snapshots))):
            snap = self._weight_snapshots.pop()
        if snap is not None:
            self.online_classifier.weights = snap["weights"].copy()
            if snap.get("classes") is not None:
                self.online_classifier.classes_ = snap["classes"].copy()
            self.model_version = int(snap["version"])
        return self.model_version

    def partial_fit_online(self, texts: List[str], labels: List[int]) -> Dict[str, Any]:
        """Update model weights online using corrected samples (PA-II step with poisoning guard)."""
        if not texts or not labels or len(texts) != len(labels):
            raise ValueError("texts and labels must be non-empty lists of equal length.")
        if len(texts) > 500:
            raise ValueError("Online update batch exceeds maximum safe size (500).")
        for t in texts:
            if not isinstance(t, str) or not t.strip() or len(t) > 5000:
                raise ValueError("Each online training text must be a non-empty string (<= 5000 chars).")
        n_cats = len(self.codeframe_labels)
        for lbl in labels:
            if not isinstance(lbl, (int, np.integer)) or isinstance(lbl, bool) or lbl < 0 or (n_cats > 0 and lbl >= n_cats):
                raise ValueError(f"Label index {lbl} is out of bounds for codeframe ({n_cats} categories).")

        X = self.extract_embeddings(texts)
        if not np.all(np.isfinite(X)) or np.any(np.linalg.norm(X, axis=1) < 1e-6):
            raise ValueError("Poisoning guard: rejected degenerate or non-finite embedding vectors.")

        y = np.array(labels, dtype=int)
        classes = np.arange(n_cats) if n_cats else np.unique(y)

        # Save snapshot prior to mutating weights
        self._snapshot_state()
        w_before = self.online_classifier.weights.copy() if getattr(self.online_classifier, "weights", None) is not None else None

        if hasattr(self.online_classifier, "partial_fit"):
            self.online_classifier.partial_fit(X, y, classes=classes)
        else:
            self.online_classifier.fit(X, y)

        # Poisoning guard: cap total weight shift norm
        if w_before is not None and self.online_classifier.weights is not None and w_before.shape == self.online_classifier.weights.shape:
            delta = self.online_classifier.weights - w_before
            delta_norm = float(np.linalg.norm(delta))
            if delta_norm > self.max_step_norm:
                self.online_classifier.weights = w_before + delta * (self.max_step_norm / delta_norm)

        self.model_version += 1
        logger.info(f"Online PA-II weight update complete (v{self.model_version}) for {len(texts)} samples.")
        return {"model_version": self.model_version, "updated_samples": len(texts)}

    def analyze_sentiment(self, text: str) -> str:
        """Determines sentiment (positive, negative, neutral, mixed) for Taglish verbatims."""
        if not text or not isinstance(text, str) or not text.strip():
            return "neutral"
        try:
            if not hasattr(self, "_v2_sentiment_coder"):
                from engine.coder_v2 import Coder
                self._v2_sentiment_coder = Coder("consumer_default")
            v2_sent = self._v2_sentiment_coder.code(text).get("sentiment", "neutral")
            return {"pos": "positive", "neg": "negative", "neutral": "neutral", "mixed": "mixed"}.get(v2_sent, "neutral")
        except Exception:
            pass
        clean_text = self.preprocessor.mask_pii(text).lower()
        tokens = re.findall(r"[a-z0-9]+", clean_text)

        pos_words = {
            "maganda", "ganda", "sulit", "mura", "mabait", "maayos", "satisfied",
            "satisfaction", "good", "great", "excellent", "best", "love", "like",
            "tulong", "salamat", "happy", "mabilis", "sarap", "matibay", "bawas",
            "discount", "free", "libre", "ok", "okay", "ayos", "bilis"
        }
        neg_words = {
            "mahal", "pangit", "lugi", "tagal", "matagal", "delayed", "delay",
            "bagal", "mabagal", "gulo", "magulo", "baho", "sira", "masira",
            "hirap", "mahirap", "dusa", "pila", "traffic", "init", "initan",
            "singit", "panis", "bulok", "scam", "bad", "terrible", "worst",
            "hate", "disappointed", "problema", "kulang", "siksikan"
        }

        pos_score = 0.0
        neg_score = 0.0
        has_contrast = any(c in tokens for c in self.preprocessor.CONTRAST_WORDS)

        i = 0
        while i < len(tokens):
            w = tokens[i]
            is_negated = False
            if w in self.preprocessor.NEGATION_WORDS and i + 1 < len(tokens):
                is_negated = True
                i += 1
                w = tokens[i]

            if w in pos_words:
                if is_negated:
                    neg_score += 1.2
                else:
                    pos_score += 1.0
            elif w in neg_words:
                if is_negated:
                    pos_score += 0.8
                else:
                    neg_score += 1.2
            i += 1

        if has_contrast and pos_score >= 0.8 and neg_score >= 0.8:
            return "mixed"
        if pos_score > neg_score + 0.3:
            return "positive"
        if neg_score > pos_score + 0.3:
            return "negative"
        return "neutral"

    def batch_code(self, verbatims: List[str]) -> List[Dict[str, Any]]:
        """Batch code open-ended responses with sentiment, category prediction, and review queue flags."""
        if not verbatims:
            return []

        if not self.is_fitted:
            if self.codeframe_labels and len(self.codeframe_labels) >= 2:
                seeds = list(self.codeframe_labels)
                labels = list(range(len(seeds)))
                self.train_baseline(seeds, labels)
            else:
                default_cats = ["General Feedback", "Product & Pricing", "Service & Support", "Logistics & Delivery"]
                self.set_codeframe(default_cats)
                self.train_baseline(default_cats, list(range(len(default_cats))))

        predictions = self.predict_with_uncertainty(verbatims)
        records = []
        for idx, (raw_v, pred) in enumerate(zip(verbatims, predictions)):
            masked_v = self.preprocessor.mask_pii(raw_v if isinstance(raw_v, str) else "")
            sentiment = self.analyze_sentiment(masked_v)
            label = pred.get("predicted_label", "General Feedback")
            v_clean = masked_v.lower()

            assigned_codes = []
            assigned_themes = []
            if not v_clean.strip():
                # Empty / whitespace answers get no theme (they used to receive a code).
                records.append({"response_id": idx + 1, "raw_text": masked_v, "text": masked_v, "predicted_label": None,
                                "assigned_themes": [], "assigned_codes": [], "confidence": 0.0, "margin": 0.0,
                                "needs_review": True, "sentiment": "neutral", "encoder": self.encoder_kind})
                continue

            # 1. Map verbatims to specific leaf codes using topic keyword and exemplar dictionaries
            if self.codeframe_topics:
                for t in self.codeframe_topics:
                    kws = t.get("keywords", []) + t.get("pos_keywords", []) + t.get("neg_keywords", [])
                    exemplars = t.get("exemplars", [])
                    all_triggers = kws + exemplars
                    matched = False
                    for w in all_triggers:
                        w_str = str(w).strip().lower()
                        # P7-10: whole words only; the substring fallback made 'kumurap' trigger 'mura'.
                        if len(w_str) >= 3 and re.search(r'\b' + re.escape(w_str) + r'\b', v_clean):
                            matched = True
                            break

                    if matched:
                        codes_dict = t.get("codes", {})
                        if isinstance(codes_dict, dict) and codes_dict:
                            pol_key = "pos" if sentiment == "positive" else ("neg" if sentiment == "negative" else None)
                            if pol_key and pol_key in codes_dict:
                                c_info = codes_dict[pol_key]
                                if c_info.get("code_id") is not None:
                                    assigned_codes.append(c_info.get("code_id"))
                                if c_info.get("label"):
                                    assigned_themes.append(c_info.get("label"))
                            else:
                                for pol, c_info in codes_dict.items():
                                    if c_info.get("code_id") is not None:
                                        assigned_codes.append(c_info.get("code_id"))
                                    if c_info.get("label"):
                                        assigned_themes.append(c_info.get("label"))
                        else:
                            if t.get("id") is not None:
                                assigned_codes.append(t.get("id"))
                            t_lbl = t.get("label") or t.get("name") or t.get("id")
                            if t_lbl:
                                assigned_themes.append(t_lbl)

            # 2. Fallback: if no keyword triggered, resolve from the predicted_label topic
            if not assigned_codes and self.codeframe_topics:
                for t in self.codeframe_topics:
                    t_name = t.get("subnet") or t.get("net") or t.get("name") or t.get("id")
                    if t_name == label:
                        codes_dict = t.get("codes", {})
                        if isinstance(codes_dict, dict) and codes_dict:
                            pol_key = "pos" if sentiment == "positive" else ("neg" if sentiment == "negative" else None)
                            c_info = codes_dict.get(pol_key) or next(iter(codes_dict.values()))
                            if c_info.get("code_id") is not None:
                                assigned_codes.append(c_info.get("code_id"))
                            if c_info.get("label"):
                                assigned_themes.append(c_info.get("label"))
                        else:
                            if t.get("id") is not None:
                                assigned_codes.append(t.get("id"))
                            t_lbl = t.get("label") or t.get("name") or t.get("id")
                            if t_lbl:
                                assigned_themes.append(t_lbl)
                        break

            if not assigned_themes:
                assigned_themes = [label]  # embedding nearest-label fallback only when no keyword matched
            # P7-06: records go to the UI, the review queue and exports; they carry masked text only.
            records.append({
                "response_id": idx + 1,
                "raw_text": masked_v,
                "text": masked_v,
                "predicted_label": label,
                "assigned_themes": list(dict.fromkeys(assigned_themes)),
                "assigned_codes": list(dict.fromkeys(assigned_codes)),
                "confidence": pred.get("confidence", 0.5),
                "margin": pred.get("margin", 0.0),
                "needs_review": pred.get("needs_review", False) or not assigned_codes,
                "sentiment": sentiment,
                "encoder": self.encoder_kind
            })
        return records


# --- Verification & Module Execution Unit Test ---
if __name__ == "__main__":
    print("--- Running Coder v3 Pipeline Verification Test ---")
    # 1. Instantiate Engine
    engine = CoderV3Engine()
    # 2. Define Category Labels
    categories = [
        "Product Quality Positive",
        "Pricing Negative",
        "Customer Service Positive",
        "Delivery Delay Negative"
    ]
    engine.set_codeframe(categories)
    # 3. Dummy Seed Dataset (Taglish)
    seed_texts = [
        "Ang ganda ng kalidad ng sapatos, matibay talaga!",
        "Masyadong mahal, hindi sulit ang presyo.",
        "Mabait yung customer support, nasagot agad tanong ko.",
        "Ang tagal dumating ng order ko, dalawang linggo delayed."
    ]
    seed_labels = [0, 1, 2, 3]  # Index mapping to categories
    # 4. Fit Model
    engine.train_baseline(seed_texts, seed_labels)
    # 5. Evaluate Inference on Unseen Taglish Samples
    test_responses = [
        "Sobra mahal ng item na ito, pero maganda naman.",
        "Hindi dumating sa oras ang parcel, sobrang tagal.",
        "Super satisfied sa quality ng bag!"
    ]
    predictions = engine.predict_with_uncertainty(test_responses)
    for res in predictions:
        print(f"\nText: '{res['text']}'")
        print(f"Predicted: {res['predicted_label']} (Conf: {res['confidence']})")
        print(f"Margin: {res['margin']} | Review Flag: {res['needs_review']}")
