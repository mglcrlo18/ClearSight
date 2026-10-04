"""Coder v2: unit, property (Hypothesis) and security tests. All sentences are synthetic."""
from __future__ import annotations

import json
import os
import time

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

os.environ.setdefault("CLEARSIGHT_CODER_TELEMETRY", "0")

from engine import tl_morph
from engine.tl_morph import normalize_text, stem, tokenize
from engine.codeframe_loader import (CodeframeError, list_codeframes, load_codeframe, load_codeframe_from_dict,
                                     validate_codeframe)
from engine.coder_v2 import Coder, CoderConfig, batch_code_v2, code_verbatim_v2, get_coder
from engine.coder_feedback import FeedbackStore, text_key
from pathlib import Path

CF_DIR = Path(__file__).resolve().parent.parent / "engine" / "codeframes"


def raw_cf(name):
    return json.loads((CF_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def consumer():
    return get_coder("consumer_default")


@pytest.fixture(scope="module")
def gov():
    return get_coder("governance_default")


# --------------------------------------------------------------------------- step 1: morphology
@pytest.mark.parametrize("word,root", [
    ("mabango", "bango"), ("nakakainis", "inis"), ("pinakamura", "mura"), ("bumili", "bili"),
    ("binili", "bili"), ("tumatagal", "tagal"), ("linisin", "linis"), ("nililinis", "linis"),
    ("matulungin", "tulong"), ("bigyan", "bigay"), ("kalsada", "kalsada"), ("mahal", "mahal"),
])
def test_stemmer_known_roots(word, root):
    assert stem(word) == root


def test_normaliser_textspeak_and_elongation():
    assert tokenize("Hnd nmn sya mabangooooo!!!")[:2] == ["hindi", "naman"]
    assert "mabango" in tokenize("mabangooooo")
    assert normalize_text("ÁNG GÁNDÁ") == "ang ganda"
    assert "ñ" in normalize_text("Niño")


_WORD = st.text(alphabet="abdeghiklmnoprstuwy", min_size=1, max_size=14)


@settings(max_examples=400, deadline=None)
@given(_WORD)
def test_property_stemmer_idempotent(w):
    s = stem(w)
    assert stem(s) == s
    assert s  # never empties a word


@pytest.mark.parametrize("w", ["pagmasirang", "magnakaka-irita", "nakakamahatehin", "magmaoverhanhan"])
def test_stemmer_idempotent_on_stacked_affixes(w):
    s = stem(w)
    assert stem(s) == s


_AFFIXED = st.builds(lambda p, r, q: p + r + q, st.sampled_from(["", "ma", "mag", "pag", "naka", "nakaka", "pinaka", "ka"]),
                     st.sampled_from(["sira", "ganda", "bango", "irita", "linis", "tulong", "hate", "over"]),
                     st.sampled_from(["", "an", "in", "han", "hin", "ng"]))


@settings(max_examples=300, deadline=None)
@given(st.lists(_AFFIXED, min_size=1, max_size=3))
def test_property_stemmer_idempotent_affixed(parts):
    w = "".join(parts)
    s = stem(w)
    assert stem(s) == s


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(_WORD, min_size=1, max_size=8))
def test_property_tokenize_stable(words):
    text = " ".join(words)
    once = tokenize(text)
    assert tokenize(" ".join(once)) == once


# --------------------------------------------------------------------------- step 2: negation
@pytest.mark.parametrize("text,expected", [
    ("Mabango ang sabon", "pos"),
    ("Hindi mabango ang sabon", "neg"),
    ("Hindi naman mahal", "pos"),
    ("Walang kapantay ang linis", "pos"),
    ("Hindi lang mabango kundi matagal pa", "pos"),
    ("Di ba ang ganda", "pos"),
    pytest.param("Hindi ko masasabing hindi maganda", "pos",
                 marks=pytest.mark.xfail(strict=True, reason="known gap: non-adjacent litotes is read as negative")),
    ("Not bad at all", "pos"),
    ("Dili nindot", "neg"),
])
def test_negation_scope_and_idioms(consumer, text, expected):
    assert consumer.code(text)["sentiment"] == expected


POS = ["maganda", "mabango", "malinis", "mabait", "magaling"]


@settings(max_examples=60, deadline=None)
@given(st.sampled_from(POS))
def test_property_double_negation_flips_back(w):
    c = get_coder("consumer_default")
    base = c.code(f"{w} talaga")["sentiment"]
    single = c.code(f"hindi {w}")["sentiment"]
    double = c.code(f"hindi hindi {w}")["sentiment"]
    assert base == "pos" and single == "neg" and double == "pos"


# --------------------------------------------------------------------------- step 3: decoupled / mixed / languages
def test_mixed_with_contrast(consumer):
    r = consumer.code("Mabango siya pero medyo pricey")
    assert r["sentiment"] == "mixed"
    labels = {t["theme"] for t in r["themes"]}
    assert "Expensive / High Pricing Friction" in labels
    assert r["needs_review"] is True


def test_themes_independent_of_answer_sentiment(consumer):
    r = consumer.code("Ang bango pero ang mahal")
    pol = {t["topic"]: t["polarity"] for t in r["themes"]}
    assert pol.get("scent") == "pos" and pol.get("price") == "neg"


def test_mahal_love_sense(consumer):
    r = consumer.code("Mahal ko ang brand na ito")
    assert "Expensive / High Pricing Friction" not in {t["theme"] for t in r["themes"]}


@pytest.mark.parametrize("text,expected", [
    ("It smells really good", "pos"), ("Too expensive and it broke", "neg"),
    ("Lami kaayo", "pos"), ("Dili maayo ang serbisyo", "neg"),
])
def test_english_and_bisaya_basics(consumer, text, expected):
    assert consumer.code(text)["sentiment"] == expected


def test_special_answers(consumer):
    assert consumer.code("Hindi ko alam")["themes"][0]["code_id"] == 996
    assert consumer.code("Wala naman")["themes"][0]["code_id"] == 999
    assert consumer.code("")["needs_review"] is True


# --------------------------------------------------------------------------- step 4: codeframes
def test_bundled_codeframes_validate():
    names = list_codeframes()
    assert {"consumer_default", "governance_default", "legacy_v1"} <= set(names)
    for n in names:
        cf = load_codeframe(n)
        assert cf["topics"] and cf["special"]["other"]["code_id"] == 900


def test_governance_coding(gov):
    r = gov.code("Kurakot at walang nagawa sa bayan")
    assert r["sentiment"] == "neg"
    topics = {t["topic"] for t in r["themes"]}
    assert "integrity" in topics


@pytest.mark.parametrize("name", ["sub/../consumer_default", "./consumer_default", "consumer_default ", "../etc/passwd", "..", "/etc/passwd", "consumer_default/../../x", "a" * 65,
                                  "CON", "consumer_default.json", "%2e%2e", "x\x00y"])
def test_codeframe_path_traversal_rejected(name):  # CWE-22
    with pytest.raises(CodeframeError):
        load_codeframe(name)


def test_codeframe_symlink_escape_rejected(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "codeframes").mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(raw_cf("legacy_v1")))
    (data / "codeframes" / "evil.json").symlink_to(outside)
    monkeypatch.setenv("CLEARSIGHT_DATA", str(data))
    with pytest.raises(CodeframeError):
        load_codeframe("evil")


def test_codeframe_validation_errors():
    good = raw_cf("legacy_v1")
    bad = json.loads(json.dumps(good))
    bad["topics"].append(dict(bad["topics"][0]))  # duplicate topic id
    with pytest.raises(CodeframeError):
        validate_codeframe(bad)
    with pytest.raises(CodeframeError):
        load_codeframe_from_dict({**good, "includes": ["common_price"]})
    with pytest.raises(CodeframeError):
        load_codeframe_from_dict({"id": "x"})


def test_user_codeframe_dir(tmp_path, monkeypatch):
    (tmp_path / "codeframes").mkdir()
    cf = {"schema_version": 1, "id": "mini", "name": "Mini", "domain": "consumer",
          "topics": [{"id": "price", "net": "Pricing", "subnet": "Price", "keywords": ["presyo"],
                      "pos_keywords": ["mura"], "neg_keywords": ["mahal"],
                      "codes": {"pos": {"code_id": 1, "label": "Cheap"}, "neg": {"code_id": 2, "label": "Pricey"}}}]}
    (tmp_path / "codeframes" / "mini.json").write_text(json.dumps(cf))
    monkeypatch.setenv("CLEARSIGHT_DATA", str(tmp_path))
    c = Coder("mini", CoderConfig())
    assert c.code("ang mura ng presyo")["themes"][0]["theme"] == "Cheap"


# --------------------------------------------------------------------------- PII first / no leaks
@settings(max_examples=60, deadline=None)
@given(st.from_regex(r"09[0-9]{9}", fullmatch=True), st.sampled_from(["juan.cruz@example.com", "ana_r@test.ph"]))
def test_property_pii_masked_before_coding(phone, email):
    c = get_coder("consumer_default")
    r = c.code(f"Tawagan mo ako sa {phone} o {email} mabango talaga")
    blob = json.dumps(r)
    assert phone not in blob and email not in blob


def test_pii_never_reaches_feedback_store(tmp_path):
    fs = FeedbackStore(tmp_path / "c.json", min_examples=1)
    fs.add("email ko ay maria@example.com at 09171234567, mabango", sentiment="pos")
    raw = (tmp_path / "c.json").read_text()
    assert "maria@example.com" not in raw and "09171234567" not in raw
    assert "mabango" not in raw.split('"stems"')[0]  # verbatim itself not stored, only stems + hash


# --------------------------------------------------------------------------- step 6: confidence, review, feedback
def test_confidence_and_review_queue(consumer):
    r = consumer.code("asdf qwer zxcv")
    assert r["needs_review"] and r["themes"][0]["theme"] == "Needs Review"
    r2 = consumer.code("Sobrang sulit at mabango")
    assert 0 <= r2["confidence"] <= 1 and not r2["needs_review"]


def test_review_queue_off_falls_back_to_other():
    c = Coder("consumer_default", CoderConfig(review_queue=False))
    assert c.code("asdf qwer zxcv")["themes"][0]["code_id"] == 900


def test_feedback_exact_and_model(tmp_path):
    fs = FeedbackStore(tmp_path / "c.json", min_examples=3)
    c = Coder("consumer_default", CoderConfig(feedback=fs))
    assert c.code("kakaiba yung kulay ng bote")["sentiment"] == "neutral"
    fs.add("kakaiba yung kulay ng bote", sentiment="neg", code_ids=[335])
    r = c.code("Kakaiba yung kulay ng bote!")
    assert r["sentiment"] == "neg" and r["reasons"] == ["feedback:exact"]
    for t in ["kakaiba ang hugis", "kakaiba ang tunog", "kakaiba talaga"]:
        fs.add(t, sentiment="neg")
    r2 = c.code("kakaiba ang tekstura ng takip")
    assert r2["sentiment"] == "neg" and "feedback:sentiment" in r2["reasons"]
    fs2 = FeedbackStore(tmp_path / "c.json", min_examples=3)  # persisted
    assert len(fs2) == 4 and fs2.lookup("kakaiba yung kulay ng bote")


def test_feedback_validation(tmp_path):
    fs = FeedbackStore(tmp_path / "c.json")
    with pytest.raises(ValueError):
        fs.add("ok", sentiment="great")
    with pytest.raises(ValueError):
        fs.add("   ", sentiment="pos")
    assert text_key("Mabango!") == text_key("mabango")


def test_batch_shape_matches_v1():
    out = batch_code_v2(["Sulit at mabango", "Ang mahal", None, "asdf qwer"])
    assert {"total_analyzed", "codeframe", "records", "review_queue", "sentiment_counts", "coder_version"} <= set(out)
    rec = out["records"][0]
    assert {"response_id", "raw_text", "assigned_themes", "assigned_codes", "sentiment", "confidence", "needs_review"} <= set(rec)
    assert all({"theme", "count", "prevalence_pct", "code_id", "evidence_samples"} <= set(f) for f in out["codeframe"])


# --------------------------------------------------------------------------- step 5: fallback interface
def test_fallback_interface_optional():
    from engine.local_model import NullClassifier, build_fallback
    assert build_fallback("") is None and build_fallback("none") is None
    with pytest.raises(ValueError):
        build_fallback("http://example.com/model")
    with pytest.raises(ValueError):
        build_fallback("model2vec:/nonexistent/dir")

    class Fake:
        def predict(self, text, coder):
            return {"sentiment": "neg", "sentiment_score": 0.9, "topic": "price", "topic_score": 0.9}
    c = Coder("consumer_default", CoderConfig(fallback=Fake()))
    r = c.code("asdf qwer zxcv")
    assert r["sentiment"] == "neg" and "fallback:topic" in r["reasons"]
    c2 = Coder("consumer_default", CoderConfig(fallback=NullClassifier()))
    assert c2.code("asdf qwer zxcv")["themes"][0]["theme"] == "Needs Review"

    class Broken:
        def predict(self, text, coder):
            raise RuntimeError("boom")
    assert Coder("consumer_default", CoderConfig(fallback=Broken())).code("asdf")["sentiment"] == "neutral"


def test_fallback_sees_scrubbed_text():
    seen = []

    class Spy:
        def predict(self, text, coder):
            seen.append(text)
            return None
    Coder("consumer_default", CoderConfig(fallback=Spy())).code("tawag 09171234567 asdf")
    assert seen and "09171234567" not in seen[0]


# --------------------------------------------------------------------------- telemetry
def test_telemetry_local_only(tmp_path, monkeypatch):
    from engine import coder_v2
    monkeypatch.setenv("CLEARSIGHT_DATA", str(tmp_path))
    monkeypatch.setenv("CLEARSIGHT_CODER_TELEMETRY", "1")
    code_verbatim_v2("Mabango talaga 09171234567")
    p = coder_v2.persist_telemetry()
    data = json.loads(open(p).read())
    assert data.get("answers", 0) >= 1
    assert "09171234567" not in open(p).read() and "mabango" not in open(p).read().lower()
    monkeypatch.setenv("CLEARSIGHT_CODER_TELEMETRY", "0")
    assert coder_v2.persist_telemetry() is None


# --------------------------------------------------------------------------- ReDoS (CWE-1333)
@pytest.mark.parametrize("payload", [
    "a" * 50_000, "hindi " * 5_000, ("mabango pero " * 2_000), "!" * 20_000 + "x", "wala " * 4_000 + "!",
    "ha" * 20_000, "[" * 10_000, ("-" * 10_000) + "a",
])
def test_redos_long_inputs_are_linear(consumer, payload):
    t = time.perf_counter()
    consumer.code(payload)
    assert time.perf_counter() - t < 5.0


def test_lexicon_patterns_are_bounded():
    from engine.codeframe_loader import load_lexicon
    import re
    lx = load_lexicon()
    for key in ("none_patterns", "dont_know_patterns", "neutral_patterns"):
        for p in lx[key]:
            assert p.startswith("^") and p.endswith("$")
            assert not re.search(r"\([^)]*[+*]\)[+*]", p), p   # no nested quantifiers


def test_coding_independent_of_codeframe_load_order():
    import subprocess, sys
    prog = ("from engine.coder_v2 import Coder, CoderConfig\n"
            "{pre}"
            "c = Coder('governance_default', CoderConfig())\n"
            "print([c.code(t)['sentiment'] for t in ['nakakadisappoint ang pamamalakad', 'matulungin sa mahihirap', 'walang nagawa']])\n")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    a = subprocess.run([sys.executable, "-c", prog.format(pre="")], cwd=root, capture_output=True, text=True).stdout
    b = subprocess.run([sys.executable, "-c", prog.format(pre="Coder('legacy_v1'); Coder('consumer_default')\n")], cwd=root,
                       capture_output=True, text=True).stdout
    assert a and a == b
