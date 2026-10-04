"""
ClearSight Taglish coder v2.

Pipeline (each step can be switched off through ``CoderConfig`` for ablations):

1. ``scrub_pii`` first (PII never reaches the lexicon, the model fallback or the feedback store).
2. Special answers (none / don't know / neutral / non-substantive) from bounded patterns.
3. Normalise + tokenise + stem (``engine.tl_morph``), applied identically to lexicon and input.
4. Clause segmentation at punctuation, contrast markers (pero, kaso, kaya lang, but ...) and
   concessive markers (kahit, despite ...).
5. Negation scope: a negator flips the first polar item within ``neg_window`` tokens of the same
   clause; a negator inside an open scope toggles it back (double negation). Idioms such as
   "hindi lang ... pati", "walang kapantay", "di ba", "sana all" are exempt. A negator whose scope
   holds no polar word ("walang stock", "hindi ko alam ang plano") contributes an "absence" score.
6. Decoupled outputs: multi-label topics from the codeframe, and an answer-level sentiment
   (pos / neg / neutral / mixed). A topic's code (favourable vs unfavourable) follows the
   topic's own polar keywords, else the clause sentiment, else the answer sentiment.
7. Confidence per answer; low-confidence or uncodable answers go to a "Needs review" queue
   instead of being silently dumped into Other.
8. Optional local fallbacks (no network): a pluggable ``LocalClassifier`` and a feedback model
   learnt from analyst corrections.

All regexes are bounded alternations or anchored patterns (CWE-1333). Codeframe keywords are
literals, never regexes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from engine.codeframe_loader import load_codeframe, load_lexicon
from engine.taglish_nlp import scrub_pii
from engine import tl_morph
from engine.tl_morph import register_roots, stem, stem_phrase, tokenize

CODER_VERSION = "2.0.0"


@dataclass
class CoderConfig:
    stem: bool = True                 # step 1
    negation: bool = True             # step 2
    contrast: bool = True             # step 3 (contrast weighting + mixed detection)
    sentiment_lexicon: bool = True    # step 3 (decoupled general sentiment lexicon)
    review_queue: bool = True         # step 6
    neg_window: int = 4
    absence_weight: float = 0.8
    hindi_absence_weight: float = 0.6
    after_contrast_weight: float = 1.5
    before_contrast_weight: float = 0.6
    concessive_weight: float = 0.4
    polar_threshold: float = 0.25
    mixed_min: float = 0.9
    mixed_ratio: float = 0.75
    mixed_on_raw: bool = True         # judge "mixed" on unweighted clause masses (contrast weights still set the polarity)
    review_threshold: float = 0.5
    comparative_flip: Optional[bool] = None   # None = use codeframe option
    fallback: Any = None              # LocalClassifier or None
    fallback_min_score: float = 0.0
    feedback: Any = None              # FeedbackStore or None


# ---------------------------------------------------------------------------
# Telemetry: local-only counters (no text). Persisted to $CLEARSIGHT_DATA/coder_telemetry.json
# unless CLEARSIGHT_CODER_TELEMETRY=0.
# ---------------------------------------------------------------------------
TELEMETRY: Counter = Counter()
_TELEMETRY_LOCK = threading.Lock()


def _tick(**kw: int) -> None:
    with _TELEMETRY_LOCK:
        for k, v in kw.items():
            TELEMETRY[k] += v


def telemetry_snapshot() -> dict:
    with _TELEMETRY_LOCK:
        return dict(TELEMETRY)


def persist_telemetry() -> Optional[str]:
    if os.environ.get("CLEARSIGHT_CODER_TELEMETRY", "1") == "0":
        return None
    base = Path(os.environ.get("CLEARSIGHT_DATA") or (Path.home() / ".clearsight"))
    try:
        base.mkdir(parents=True, exist_ok=True)
        path = base / "coder_telemetry.json"
        old = {}
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                old = {}
        snap = telemetry_snapshot()
        merged = {k: int(old.get(k, 0)) + int(v) for k, v in snap.items()}
        for k, v in old.items():
            merged.setdefault(k, v)
        path.write_text(json.dumps(merged, indent=1, sort_keys=True), encoding="utf-8")
        with _TELEMETRY_LOCK:
            TELEMETRY.clear()
        return str(path)
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Lexicon compilation
# ---------------------------------------------------------------------------
_LOVE_AFTER = {"ko", "kita", "namin", "natin", "niya", "nila", "ninyo", "mo"}
_PUNCT_SPLIT = re.compile(r"[.;!?\n]+|\s[-–—]\s|\(|\)|,")


_BUNDLED_DONE = [False]
_BUNDLED_LOCK = threading.Lock()


def _register_bundled_roots() -> None:
    """Register the roots of every *bundled* codeframe once, before any coder compiles.

    The stemmer's root list is process-wide; registering the bundled union up front makes stemming
    (and so coding) independent of which codeframe happened to be loaded first."""
    with _BUNDLED_LOCK:
        if _BUNDLED_DONE[0]:
            return
        from engine.codeframe_loader import BUNDLED_DIR
        words: list = []
        for p in sorted(BUNDLED_DIR.glob("*.json")):
            try:
                cf = load_codeframe(p.stem) if not p.stem.startswith("common_") else None
            except Exception:
                cf = None
            for t in (cf or {}).get("topics", []):
                words += t["keywords"] + t["pos_keywords"] + t["neg_keywords"]
        register_roots(words)
        _BUNDLED_DONE[0] = True


def _phrase_map(entries: dict, sign: float) -> dict:
    out = {}
    for k, w in entries.items():
        if k.startswith("_") or not isinstance(w, (int, float)) or w == 0:
            continue
        ph = stem_phrase(k)
        if ph:
            out[ph] = sign * float(w)
    return out


class Coder:
    """A compiled coder for one codeframe. Thread-safe for concurrent ``code`` calls."""

    def __init__(self, codeframe: dict | str = "consumer_default", config: Optional[CoderConfig] = None,
                 lexicon: Optional[dict] = None):
        self.config = config or CoderConfig()
        self.cf = load_codeframe(codeframe) if isinstance(codeframe, str) else codeframe
        self.lex = lexicon or load_lexicon()
        self._lock = threading.Lock()
        self._version = -1
        self._compile()

    # -- compilation -----------------------------------------------------
    def _compile(self) -> None:
        lx = self.lex
        words = list(lx["positive"]) + list(lx["negative"]) + list(lx["intensifiers"]) + list(self.cf["overrides"])
        for t in self.cf["topics"]:
            words += t["keywords"] + t["pos_keywords"] + t["neg_keywords"]
        _register_bundled_roots()
        register_roots(words)
        st = stem if self.config.stem else (lambda w: w)
        self._st = st

        def ph(s):
            return tuple(st(t) for t in tokenize(s))

        pol = {}
        if self.config.sentiment_lexicon:
            for k, w in lx["positive"].items():
                if isinstance(w, (int, float)) and w:
                    pol[ph(k)] = float(w)
            for k, w in lx["negative"].items():
                if isinstance(w, (int, float)) and w:
                    pol[ph(k)] = -float(w)
        for k, w in self.cf["overrides"].items():
            pol[ph(k)] = float(w)
        # topic polar keywords also carry polarity
        for t in self.cf["topics"]:
            for k in t["pos_keywords"]:
                pol.setdefault(ph(k), 1.0)
            for k in t["neg_keywords"]:
                pol.setdefault(ph(k), -1.0)
        pol.pop((), None)
        self.polar = pol
        self.max_phrase = max([len(p) for p in pol] + [1])
        self.intens = {ph(k): float(v) for k, v in lx["intensifiers"].items()}
        # negators and suggestion markers match SURFACE tokens: stemming would turn "mawala" into "wala"
        # and "binigay" into the imperative "magbigay".
        surf = lambda k: tuple(tokenize(k))
        self.negators = {surf(k) for k in lx["negators"]} - {()}
        self.absence = {surf(k) for k in lx["absence_negators"]} - {()}
        self.idioms = {ph(k): float(v) for k, v in lx["negation_idioms"].items() if not k.startswith("_")}
        self.idiom_order = sorted(self.idioms, key=len, reverse=True)
        self.contrast = sorted({ph(k) for k in lx["contrast_markers"]}, key=len, reverse=True)
        self.concessive = sorted({ph(k) for k in lx["concessive_markers"]}, key=len, reverse=True)
        self.comp_other = {ph(k) for k in lx["comparative_other"]}
        self.flips = sorted({ph(k) for k in lx.get("flip_markers", [])} - {()}, key=len, reverse=True)
        self.suggest = {surf(k): float(v) for k, v in lx.get("suggestion_markers", {}).items() if v}
        self.moder_t = {ph(k) for k in lx.get("moderation_targets", [])}
        self.scope_skip = {st(t) for k in lx.get("scope_skip", []) for t in tokenize(k)}
        self.moder_w = {ph(k) for k in lx.get("moderation_words", [])}
        self.none_re = [re.compile(p) for p in lx["none_patterns"]]
        self.dk_re = [re.compile(p) for p in lx["dont_know_patterns"]]
        self.neutral_re = [re.compile(p) for p in lx["neutral_patterns"]]
        topics = []
        for t in self.cf["topics"]:
            topics.append({
                **t,
                "kw": sorted({ph(k) for k in t["keywords"] + t["pos_keywords"] + t["neg_keywords"]} - {()}, key=len, reverse=True),
                "pk": {ph(k) for k in t["pos_keywords"]} - {()},
                "nk": {ph(k) for k in t["neg_keywords"]} - {()},
            })
        # a topic keyword must never be a negator or a function word (e.g. "nawawala" -> "wala")
        banned = {(st(p[0]),) for p in self.negators if len(p) == 1} | {p for p in self.negators if len(p) == 1} | {(w,) for w in self.scope_skip}
        for t in topics:
            t["kw"] = [p for p in t["kw"] if p not in banned]
        self.topics = topics
        cmp_opt = self.cf.get("options", {}).get("comparative_flip")
        self.comparative_flip = self.config.comparative_flip if self.config.comparative_flip is not None else (
            cmp_opt if cmp_opt is not None else self.cf.get("domain") == "consumer")
        self._version = tl_morph.ROOTS_VERSION[0]

    def _ensure_compiled(self) -> None:
        if self._version != tl_morph.ROOTS_VERSION[0]:
            with self._lock:
                if self._version != tl_morph.ROOTS_VERSION[0]:
                    self._compile()

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _match_at(stems: list[str], i: int, phrase: tuple) -> bool:
        n = len(phrase)
        return tuple(stems[i:i + n]) == phrase

    def _special(self, scrubbed: str) -> Optional[str]:
        norm = " ".join(tokenize(scrubbed))
        norm2 = re.sub(r"\b(?:po|opo|naman|lang|na|talaga|eh|e|ha)\b", " ", norm)
        norm2 = re.sub(r"\s+", " ", norm2).strip()
        if not norm.strip() or re.fullmatch(r"[\W_]*", scrubbed or "") or re.fullmatch(r"(?:asdf|xxx|\.+|-+|test)", norm):
            return "needs_review"
        for rx in self.none_re:
            if rx.match(norm) or rx.match(norm2):
                return "none"
        for rx in self.dk_re:
            if rx.match(norm) or rx.match(norm2):
                return "dont_know"
        for rx in self.neutral_re:
            if rx.match(norm) or rx.match(norm2):
                return "neutral"
        return None

    def _segment(self, toks: list[str], stems: list[str]) -> list[dict]:
        """Split the token stream into clauses; mark clause roles (normal / after-contrast / concessive)."""
        clauses, cur, role = [], [], "normal"
        i = 0
        n = len(stems)

        def flush(next_role):
            nonlocal cur, role
            if cur:
                clauses.append({"idx": cur, "role": role})
            cur, role = [], next_role

        while i < n:
            if toks[i] == "\x00":
                flush("normal")
                i += 1
                continue
            hit = None
            if self.config.contrast:
                for c in self.contrast:
                    if self._match_at(stems, i, c):
                        hit = ("contrast", len(c))
                        break
                if not hit:
                    for c in self.concessive:
                        if self._match_at(stems, i, c):
                            hit = ("concessive", len(c))
                            break
            if hit:
                if hit[0] == "contrast":
                    if clauses or cur:
                        # everything so far is the "before" part
                        flush("after_contrast")
                        for c in clauses:
                            if c["role"] == "normal":
                                c["role"] = "before_contrast"
                    else:
                        role = "after_contrast"
                else:
                    flush("concessive")
                i += hit[1]
                continue
            cur.append(i)
            i += 1
        flush("normal")
        return clauses

    def _clause_polarity(self, stems: list[str], idx: list[int], toks: Optional[list[str]] = None) -> tuple[float, dict]:
        """Score one clause; returns (score, info). info['flipped'] = set of positions whose polarity was negated."""
        cfg = self.config
        s = [stems[i] for i in idx]
        r = [toks[i] for i in idx] if toks is not None else s
        n = len(s)
        score = 0.0
        flipped_pos: set[int] = set()
        polar_hits: list[tuple[int, float]] = []
        scope_left = 0
        scope_flip = False
        scope_neg = None
        scope_kind = "neg"
        last_neg_end = -1
        suggested = False
        mult = 1.0
        j = 0
        while j < n:
            # idioms first (longest)
            idiom = next((ph for ph in self.idiom_order if tuple(s[j:j + len(ph)]) == ph), None)
            if idiom is not None and cfg.negation:
                val = self.idioms[idiom]
                if val:
                    score += val
                    polar_hits.append((idx[j], val))
                j += len(idiom)
                continue
            # multi-word polar phrases that start with a negator ("walang nagawa", "walang stock") win over the negator
            long_hit = None
            for L in range(min(self.max_phrase, n - j), 1, -1):
                ph = tuple(s[j:j + L])
                if ph in self.polar:
                    long_hit = (ph, self.polar[ph])
                    break
            if long_hit is not None:
                val = long_hit[1] * mult
                mult = 1.0
                if scope_left > 0 and scope_flip:
                    val = -val
                    for k in range(len(long_hit[0])):
                        flipped_pos.add(idx[j + k])
                    scope_left, scope_flip = 0, False
                score += val
                polar_hits.append((idx[j], val))
                j += len(long_hit[0])
                continue
            neg = next((ph for ph in self.negators if tuple(r[j:j + len(ph)]) == ph), None)
            if neg is not None and cfg.negation:
                # "hindi masyadong malamig" = not too cold -> moderation, mildly positive
                k2 = j + len(neg)
                while k2 < n and s[k2] in ("ko", "siya", "ito", "naman", "po", "sya", "kasi", "pa"):
                    k2 += 1
                if k2 < n and (s[k2],) in self.moder_w and k2 + 1 < n and (s[k2 + 1],) in self.moder_t:
                    score += 0.8
                    polar_hits.append((idx[j], 0.8))
                    j = k2 + 2
                    continue
                if scope_left > 0 and last_neg_end == j and scope_flip and neg in (("hindi",), ("di",), ("not",)) and scope_neg in (("hindi",), ("di",), ("not",)):
                    scope_flip = False               # adjacent double negation ("hindi hindi") toggles back
                    scope_left = cfg.neg_window
                else:
                    if scope_left > 0 and scope_flip and scope_kind == "neg":
                        w = cfg.absence_weight if scope_neg in self.absence else cfg.hindi_absence_weight
                        score -= w
                        polar_hits.append((idx[j], -w))
                    scope_left, scope_flip, scope_neg, scope_kind = cfg.neg_window, True, neg, "neg"
                j += len(neg)
                last_neg_end = j
                continue
            flip = next((ph for ph in self.flips if tuple(s[j:j + len(ph)]) == ph), None) if cfg.negation else None
            if flip is not None:
                # removal / protection verbs flip their object without an absence penalty ("nakakatanggal ng libag")
                scope_left, scope_flip, scope_neg, scope_kind = cfg.neg_window, True, flip, "flip"
                j += len(flip)
                continue
            sug = next((ph for ph in self.suggest if tuple(r[j:j + len(ph)]) == ph), None) if cfg.sentiment_lexicon else None
            if sug is not None and not suggested:
                # suggestions imply a current shortfall ("dapat magkaroon ng ilaw", "fix the roads")
                score -= self.suggest[sug]
                polar_hits.append((idx[j], -self.suggest[sug]))
                suggested = True
                scope_left, scope_flip, scope_neg, scope_kind = cfg.neg_window, True, sug, "sugg"
                j += len(sug)
                continue
            inten = next((ph for ph in self.intens if tuple(s[j:j + len(ph)]) == ph), None)
            if inten is not None:
                mult = max(mult, self.intens[inten])
                j += len(inten)
                continue
            hit = None
            for L in range(min(self.max_phrase, n - j), 0, -1):
                ph = tuple(s[j:j + L])
                if ph in self.polar:
                    hit = (ph, self.polar[ph])
                    break
            if hit and scope_left > 0 and scope_flip and len(hit[0]) == 1 and s[j] in self.scope_skip and j + 1 < n:
                hit = None  # adverb inside a negation scope ("hindi madaling pawisan"): skip it, negate the head
            if hit and scope_left > 0 and scope_flip and scope_kind == "sugg":
                # a wished-for state is not a current positive ("dapat ayusin ang kalsada")
                for k in range(len(hit[0])):
                    flipped_pos.add(idx[j + k])
                scope_left, scope_flip = 0, False
                j += len(hit[0])
                continue
            if hit:
                val = hit[1] * mult
                mult = 1.0
                if scope_left > 0 and scope_flip:
                    val = -val
                    for k in range(len(hit[0])):
                        flipped_pos.add(idx[j + k])
                    scope_left, scope_flip = 0, False
                elif scope_left > 0:
                    scope_left = 0
                score += val
                polar_hits.append((idx[j], val))
                j += len(hit[0])
                continue
            if scope_left > 0 and s[j] in self.scope_skip:
                j += 1
                continue
            if scope_left > 0:
                scope_left -= 1
                if scope_left == 0 and scope_flip and scope_kind in ("flip", "sugg"):
                    scope_flip = False
                elif scope_left == 0 and scope_flip:
                    # scope closed with no polar word: absence / plain negation
                    w = cfg.absence_weight if scope_neg in self.absence else cfg.hindi_absence_weight
                    score -= w
                    polar_hits.append((idx[j], -w))
                    scope_flip = False
            j += 1
        if scope_left > 0 and scope_flip and scope_kind == "neg":
            w = cfg.absence_weight if scope_neg in self.absence else cfg.hindi_absence_weight
            score -= w
            polar_hits.append((idx[-1] if idx else 0, -w))
        if self.comparative_flip and score > 0 and "mas" in s and any(
                tuple(s[k:k + len(c)]) == c for c in self.comp_other for k in range(n)):
            score = -score
        return score, {"flipped": flipped_pos, "hits": polar_hits}

    # -- main entry --------------------------------------------------------
    def code(self, text: Any) -> dict:
        self._ensure_compiled()
        cfg = self.config
        scrubbed = scrub_pii("" if text is None else str(text))
        sp = self.cf["special"]
        _tick(answers=1)
        if cfg.feedback is not None:
            fb = cfg.feedback.lookup(scrubbed)
            if fb is not None:
                res = self._from_correction(scrubbed, fb)
                if res is not None:
                    _tick(feedback_exact=1)
                    return res
        kind = self._special(scrubbed)
        if kind:
            code = sp[kind]
            sent = "neutral"
            needs = kind == "needs_review" and cfg.review_queue
            if kind == "needs_review" and not cfg.review_queue:
                code = sp["other"]
            _tick(**{f"special_{kind}": 1})
            return self._result(scrubbed, [self._theme(code, "Special", kind, "neutral", 0.95)], sent, 0.0, 0.95 if not needs else 0.2,
                                needs, [f"special:{kind}"])
        # tokenise with clause breaks preserved as \x00 markers
        pieces = [p for p in _PUNCT_SPLIT.split(scrubbed) if p and p.strip()]
        toks: list[str] = []
        for k, p in enumerate(pieces):
            if k:
                toks.append("\x00")
            toks.extend(tokenize(p))
        # "mahal" polysemy: love sense when followed by a pronoun / "na mahal"
        for i, t in enumerate(toks):
            if t == "mahal":
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                prv = toks[i - 1] if i > 0 else ""
                if nxt in _LOVE_AFTER or prv in ("minamahal", "pinakamamahal") or (nxt == "na" and toks[i + 2:i + 3] == ["mahal"]):
                    toks[i] = "love"
            elif t in ("pagmamahal", "nagmamahal", "nagmamahalan", "minamahal", "mapagmahal"):
                toks[i] = "love"
        stems = [self._st(t) if t != "\x00" else t for t in toks]
        clauses = self._segment(toks, stems)
        pos_mass = neg_mass = raw_pos = raw_neg = 0.0
        has_contrast = any(c["role"] in ("after_contrast", "before_contrast") for c in clauses)
        clause_scores = []
        flipped: set[int] = set()
        for c in clauses:
            sc, info = self._clause_polarity(stems, c["idx"], toks)
            flipped |= info["flipped"]
            w = 1.0
            if cfg.contrast:
                w = {"after_contrast": cfg.after_contrast_weight, "before_contrast": cfg.before_contrast_weight,
                     "concessive": cfg.concessive_weight}.get(c["role"], 1.0)
            clause_scores.append(sc)
            if sc > 0:
                pos_mass += sc * w
                raw_pos += sc
            elif sc < 0:
                neg_mass += -sc * w
                raw_neg += -sc
        total = pos_mass - neg_mass
        mp, mn = (raw_pos, raw_neg) if cfg.mixed_on_raw else (pos_mass, neg_mass)
        if cfg.contrast and has_contrast and mp >= cfg.mixed_min and mn >= cfg.mixed_min and \
                min(mp, mn) / max(mp, mn) >= cfg.mixed_ratio:
            sentiment = "mixed"
        elif total > cfg.polar_threshold:
            sentiment = "pos"
        elif total < -cfg.polar_threshold:
            sentiment = "neg"
        else:
            sentiment = "neutral"
        reasons = []
        # topics
        themes = []
        seen = set()
        topic_hits = 0
        for ci, c in enumerate(clauses):
            idx = c["idx"]
            s = [stems[i] for i in idx]
            # collect every keyword match, then let longer phrases claim their span first
            matches = []
            for ti, t in enumerate(self.topics):
                for ph in t["kw"]:
                    L = len(ph)
                    for k in range(len(s) - L + 1):
                        if tuple(s[k:k + L]) == ph:
                            matches.append((L, ti, k, ph))
            matches.sort(key=lambda m: -m[0])
            claimed: dict[int, int] = {}
            per_topic: dict[int, list] = {}
            for L, ti, k, ph in matches:
                span = range(k, k + L)
                owners = {claimed.get(x) for x in span} - {None}
                if owners and ti not in owners and all(x in claimed for x in span):
                    continue  # fully inside a longer phrase owned by another topic
                for x in span:
                    claimed.setdefault(x, ti)
                per_topic.setdefault(ti, []).append((k, ph))
            for ti in sorted(per_topic):
                t = self.topics[ti]
                hits, pol = 0, 0.0
                for k, ph in per_topic[ti]:
                    L = len(ph)
                    hits += 1
                    sign = 1.0 if ph in t["pk"] else -1.0 if ph in t["nk"] else 0.0
                    if sign and any(idx[k + m] in flipped for m in range(L)):
                        sign = -sign
                    pol += sign
                topic_hits += hits
                if pol > 0:
                    p, why = "pos", "topic keyword"
                elif pol < 0:
                    p, why = "neg", "topic keyword"
                elif clause_scores[ci] > 0:
                    p, why = "pos", "clause sentiment"
                elif clause_scores[ci] < 0:
                    p, why = "neg", "clause sentiment"
                elif sentiment in ("pos", "neg"):
                    p, why = sentiment, "answer sentiment"
                else:
                    p, why = "neutral", "no polarity"
                code = t["codes"].get(p) or (t["codes"].get("neutral") if p == "neutral" else None) or \
                    t["codes"].get("pos") or next(iter(t["codes"].values()))
                key = code["code_id"]
                if key in seen:
                    continue
                seen.add(key)
                conf = min(0.95, 0.45 + 0.15 * min(hits, 2) + (0.2 if why == "topic keyword" else 0.1 if why == "clause sentiment" else 0.0)
                           - (0.25 if p == "neutral" else 0.0))
                themes.append(self._theme(code, t["subnet"], t["id"], p, conf, net=t["net"]))
                reasons.append(f"topic:{t['id']}({why})")
        # fallback model for topic / sentiment
        if cfg.fallback is not None and (not themes or sentiment == "neutral"):
            try:
                fb = cfg.fallback.predict(scrubbed, self)
            except Exception:  # never let an optional model break coding
                fb = None
            if fb:
                _tick(fallback_calls=1)
                if sentiment == "neutral" and fb.get("sentiment") in ("pos", "neg") and fb.get("sentiment_score", 0) >= cfg.fallback_min_score:
                    sentiment = fb["sentiment"]
                    reasons.append("fallback:sentiment")
                    for th in themes:
                        if th["polarity"] == "neutral":
                            t = next(x for x in self.topics if x["id"] == th["topic"])
                            c2 = t["codes"].get(sentiment)
                            if c2:
                                th.update(code_id=c2["code_id"], theme=c2["label"], polarity=sentiment)
                if not themes and fb.get("topic") and fb.get("topic_score", 0) >= cfg.fallback_min_score:
                    t = next((x for x in self.topics if x["id"] == fb["topic"]), None)
                    if t:
                        p = sentiment if sentiment in ("pos", "neg") else "pos"
                        c2 = t["codes"].get(p) or next(iter(t["codes"].values()))
                        themes.append(self._theme(c2, t["subnet"], t["id"], p, 0.5, net=t["net"]))
                        reasons.append("fallback:topic")
        if cfg.feedback is not None and (not themes or sentiment == "neutral"):
            pred = cfg.feedback.predict(stems)
            if pred:
                _tick(feedback_model=1)
                if sentiment == "neutral" and pred.get("sentiment") in ("pos", "neg", "mixed"):
                    sentiment = pred["sentiment"]
                    reasons.append("feedback:sentiment")
        if sentiment == "mixed":
            reasons.append("mixed:contrast")
        sent_conf = min(1.0, abs(total) / 2.0) if sentiment != "mixed" else 0.4
        needs = False
        if not themes:
            if sentiment in ("pos", "neg") and abs(total) >= 0.9:
                code = sp["general_pos"] if sentiment == "pos" else sp["general_neg"]
                themes.append(self._theme(code, "General", "general", sentiment, 0.45))
                reasons.append("general:sentiment-only")
                needs = cfg.review_queue
            elif cfg.review_queue:
                themes.append(self._theme(sp["needs_review"], "Review", "needs_review", sentiment, 0.2))
                needs = True
                reasons.append("review:no topic")
            else:
                themes.append(self._theme(sp["other"], "General", "other", sentiment, 0.3))
        top = max(th["confidence"] for th in themes)
        conf = round(0.6 * top + 0.4 * sent_conf, 3)
        if cfg.review_queue and (conf < cfg.review_threshold or sentiment == "mixed"):
            needs = True
        _tick(needs_review=int(needs), **{f"sentiment_{sentiment}": 1})
        return self._result(scrubbed, themes, sentiment, round(total, 3), conf, needs, reasons)

    def _from_correction(self, scrubbed: str, fb: dict) -> Optional[dict]:
        """Rebuild a coder result from a stored analyst correction (exact text match)."""
        index = {}
        for t in self.topics:
            for pol, c in t["codes"].items():
                index.setdefault(str(c["code_id"]), (c, t, pol))
        for kind, c in self.cf["special"].items():
            index.setdefault(str(c["code_id"]), (c, None, "neutral"))
        sent = fb.get("sentiment") or "neutral"
        themes = []
        for cid in fb.get("code_ids") or []:
            hit = index.get(str(cid))
            if not hit:
                continue
            c, t, pol = hit
            themes.append(self._theme(c, t["subnet"] if t else "Special", t["id"] if t else "special",
                                      pol if pol in ("pos", "neg") else sent, 1.0, net=(t or {}).get("net", "")))
        if not themes:
            return None
        return self._result(scrubbed, themes, sent, 0.0, 1.0, False, ["feedback:exact"])

    def explain_topics(self, text: str) -> list:
        """Debug helper: which topic keyword phrases match (stems)."""
        stems = [self._st(t) for t in tokenize(scrub_pii(text))]
        out = []
        for t in self.topics:
            for ph in t["kw"]:
                for k in range(len(stems) - len(ph) + 1):
                    if tuple(stems[k:k + len(ph)]) == ph:
                        out.append((t["id"], " ".join(ph)))
        return out

    @staticmethod
    def _theme(code: dict, subnet: str, topic: str, polarity: str, conf: float, net: str = "") -> dict:
        net_label = net or {"pos": "Positive / Favorable Comment", "neg": "Negative / Unfavorable Comment"}.get(polarity, "Neutral / General")
        return {"code_id": code["code_id"], "theme": code["label"], "net": net_label, "subnet": subnet,
                "topic": topic, "polarity": polarity, "confidence": round(conf, 3)}

    @staticmethod
    def _result(text, themes, sentiment, score, conf, needs, reasons) -> dict:
        return {"text": text, "themes": themes, "sentiment": sentiment, "sentiment_score": score,
                "confidence": conf, "needs_review": bool(needs), "reasons": reasons, "coder_version": CODER_VERSION}


# ---------------------------------------------------------------------------
# Convenience API + batch coding (drop-in for v1 batch_code_open_ends output shape)
# ---------------------------------------------------------------------------
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()


def get_coder(codeframe: str = "consumer_default", **cfg) -> Coder:
    key = (codeframe, tuple(sorted(cfg.items())))
    with _CACHE_LOCK:
        c = _CACHE.get(key)
        if c is None:
            c = Coder(codeframe, CoderConfig(**cfg))
            _CACHE[key] = c
        return c


def code_verbatim_v2(text: Any, codeframe: str = "consumer_default", coder: Optional[Coder] = None) -> dict:
    return (coder or get_coder(codeframe)).code(text)


def batch_code_v2(verbatims: list, codeframe: str = "consumer_default", coder: Optional[Coder] = None) -> dict:
    coder = coder or get_coder(codeframe)
    records, counts, meta, cites = [], Counter(), {}, {}
    review = []
    sent_counts = Counter()
    for i, raw in enumerate(verbatims or []):
        r = coder.code(raw)
        rid = i + 1
        records.append({
            "response_id": rid, "raw_text": r["text"],
            "assigned_themes": [t["theme"] for t in r["themes"]],
            "assigned_codes": [t["code_id"] for t in r["themes"]],
            "sentiment": r["sentiment"], "confidence": r["confidence"],
            "needs_review": r["needs_review"], "reasons": r["reasons"],
        })
        sent_counts[r["sentiment"]] += 1
        if r["needs_review"]:
            review.append(rid)
        for t in r["themes"]:
            counts[t["theme"]] += 1
            meta.setdefault(t["theme"], {"code_id": t["code_id"], "net": t["net"], "subnet": t["subnet"]})
            c = cites.setdefault(t["theme"], [])
            if len(c) < 5:
                c.append({"response_id": rid, "quote": r["text"]})
    n = len(records)
    frame = [{**meta[th], "theme": th, "count": cnt, "prevalence_pct": round(100.0 * cnt / n, 1) if n else 0.0,
              "evidence_samples": cites.get(th, [])} for th, cnt in counts.most_common()]
    persist_telemetry()
    return {"total_analyzed": n, "codeframe": frame, "records": records, "review_queue": review,
            "sentiment_counts": dict(sent_counts), "coder_version": CODER_VERSION, "codeframe_id": coder.cf["id"]}


def text_key(text: str) -> str:
    """Stable key of the PII-masked, normalised text (used by the feedback store)."""
    norm = " ".join(tokenize(scrub_pii(text or "")))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
