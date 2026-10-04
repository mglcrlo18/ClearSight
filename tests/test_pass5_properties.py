"""
ClearSight Pass 5 property-based tests (Hypothesis): weighting, Kish neff, FDR, mean benchmarks/ANOVA (P4-08),
pairwise z, PII masking invariants (P4-10/P5-07). Skipped automatically if hypothesis is not installed.
"""
import math
import re

import numpy as np
import pandas as pd
import pytest
import scipy.stats as st

hyp = pytest.importorskip("hypothesis")
from hypothesis import given, settings, HealthCheck, strategies as hs  # noqa: E402

import engine.stats_engine as se  # noqa: E402  (module import: avoids pytest collecting se.test_* functions)
from engine.tabulation_engine import build_crosstab_table  # noqa: E402
from engine.taglish_nlp import scrub_pii  # noqa: E402

S = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])


# ---------------------------------------------------------------- weighting
@S
@given(hs.lists(hs.integers(1, 5000), min_size=2, max_size=4), hs.integers(0, 10**6))
def test_integer_count_targets_give_count_shares(counts, seed):
    r = np.random.default_rng(seed)
    k = len(counts)
    df = pd.DataFrame({"C": r.choice([f"c{i}" for i in range(k)], 400)})
    df.loc[:k - 1, "C"] = [f"c{i}" for i in range(k)]          # every category present
    w, _ = se.calculate_rim_weights(df, {"C": {f"c{i}": counts[i] for i in range(k)}}, trim_percentile=None)
    tot = sum(counts)
    for i in range(k):
        assert abs(w[df.C.values == f"c{i}"].sum() / w.sum() - counts[i] / tot) < 1e-4


@S
@given(hs.lists(hs.floats(0.01, 100), min_size=1, max_size=200))
def test_kish_neff_bounds(ws):
    w = np.array(ws)
    n = se.calculate_kish_neff(w)
    assert 1 - 1e-9 <= n <= len(w) + 1e-9
    assert abs(se.calculate_kish_neff(np.ones(len(w))) - len(w)) < 1e-9


# ---------------------------------------------------------------- FDR
@S
@given(hs.lists(hs.floats(0, 1), min_size=1, max_size=40), hs.sampled_from([0.05, 0.10]))
def test_bh_matches_scipy_and_is_step_up(ps, alpha):
    sig = se.apply_fdr_benjamini_hochberg(ps, alpha)
    adj = st.false_discovery_control(ps, method="bh")
    assert sig == [bool(a <= alpha + 1e-12) for a in adj]
    if any(sig):
        cutoff = max(p for p, s in zip(ps, sig) if s)
        assert all(s for p, s in zip(ps, sig) if p <= cutoff)


@S
@given(hs.lists(hs.floats(0, 1), min_size=1, max_size=40))
def test_by_never_more_discoveries_than_bh(ps):
    assert sum(se.apply_fdr_benjamini_yekutieli(ps)) <= sum(se.apply_fdr_benjamini_hochberg(ps))


# ---------------------------------------------------------------- pairwise z
@S
@given(hs.floats(0, 1), hs.floats(0, 1), hs.floats(25, 5000), hs.floats(25, 5000))
def test_pairwise_z_formula_and_antisymmetry(p1, p2, n1, n2):
    z, p, _ = se.test_pairwise_proportions(p1, p2, n1, n2)
    z2, p2_, _ = se.test_pairwise_proportions(p2, p1, n2, n1)
    assert abs(z + z2) < 1e-9 and abs(p - p2_) < 1e-12
    pp = (p1 * n1 + p2 * n2) / (n1 + n2)
    sd = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    if sd > 0:
        assert abs(z - (p1 - p2) / sd) < 1e-9


# ---------------------------------------------------------------- P4-08 means
def _mean_tab(df, w=None):
    return build_crosstab_table(df, "Q_1to5", ["Total", "G"], weights=w, metric="mean")


@S
@given(hs.integers(0, 10**6))
def test_mean_benchmark_matches_scipy_welch_unweighted(seed):
    r = np.random.default_rng(seed)
    g = r.choice(["x", "y", "z"], 400)
    q = np.where(g == "x", r.integers(1, 6, 400), r.integers(2, 6, 400))
    t = _mean_tab(pd.DataFrame({"G": g, "Q_1to5": q}))
    labels = [c.rsplit(" (", 1)[0] for c in t["banner_cols"][1:]]
    for j, lab in enumerate(labels, start=1):
        res = st.ttest_ind(q[g == lab].astype(float), q[g != lab].astype(float), equal_var=False)
        if res.statistic > 0:
            exp = "++" if res.pvalue < .05 else ("+" if res.pvalue < .10 else "")
        else:
            exp = "--" if res.pvalue < .05 else ("-" if res.pvalue < .10 else "")
        # skip knife-edge p-values where df rounding could flip the marker
        if min(abs(res.pvalue - .05), abs(res.pvalue - .10)) > 1e-3:
            assert t["rows"][0]["sig_benchmarks"][j] == exp


@S
@given(hs.integers(0, 10**6), hs.floats(0.1, 50))
def test_weighted_anova_invariant_to_weight_scale(seed, c):
    r = np.random.default_rng(seed)
    df = pd.DataFrame({"G": r.choice(list("abc"), 300), "Q_1to5": r.integers(1, 6, 300)})
    w = r.uniform(0.3, 3, 300)
    a1, a2 = _mean_tab(df, w)["anova"], _mean_tab(df, w * c)["anova"]
    assert a1 and a2 and abs(a1["f_stat"] - a2["f_stat"]) < 1e-3


def test_no_difference_gives_blank_benchmark():
    df = pd.DataFrame({"G": list("ab") * 100, "Q_1to5": [3, 4] * 50 + [4, 3] * 50})
    assert set(_mean_tab(df)["rows"][0]["sig_benchmarks"][1:]) == {""}


# ---------------------------------------------------------------- PII invariants
_digits = lambda n: hs.text(alphabet="0123456789", min_size=n, max_size=n)
_sep = hs.sampled_from(["", " ", "-", "."])


def _no_digit_run(s, n):
    return re.search(r"\d(?:[\s.-]?\d){%d,}" % (n - 1), s) is None


@hs.composite
def _ph_mobile(draw):
    net = draw(hs.sampled_from(["917", "905", "918", "927", "939", "966", "977", "995", "998", "895", "896", "813", "817", "908"]))
    sub = draw(_digits(7))
    a, b = draw(_sep), draw(_sep)
    fmt = draw(hs.sampled_from(["0{n}{a}{x}{b}{y}", "+63{a}{n}{a}{x}{b}{y}", "63{a}{n}{a}{x}{b}{y}", "(0{n}){a}{x}{b}{y}", "+63 ({n}) {x} {y}"]))
    return fmt.format(n=net, a=a, b=b, x=sub[:3], y=sub[3:])


@settings(max_examples=300, deadline=None)
@given(_ph_mobile(), hs.sampled_from(["salamat.", "po", "ok"]))
def test_every_ph_mobile_masked_and_next_word_kept(num, word):
    out = scrub_pii(f"Tawagan mo ako sa {num} {word}")
    assert _no_digit_run(out, 7), out
    assert out.endswith(" " + word), out


@settings(max_examples=300, deadline=None)
@given(hs.text(max_size=120))
def test_scrub_idempotent(t):
    once = scrub_pii(t)
    assert scrub_pii(once) == once


@S
@given(hs.integers(1, 9_999_999), hs.sampled_from(["₱{:,}", "PHP {:,}", "{:,} pesos", "Php{:,}.00"]))
def test_money_not_masked(n, tpl):
    t = "Gastos ko " + tpl.format(n)
    assert scrub_pii(t) == t


def _luhn_ok(num):
    ds = [int(x) for x in num][::-1]
    return sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(ds)) % 10 == 0


@S
@given(hs.sampled_from(["4", "51", "55", "2221", "2720", "6011"]), hs.data())
def test_luhn_valid_cards_masked(prefix, data):
    body = prefix + data.draw(_digits(15 - len(prefix)))
    num = body + next(str(c) for c in range(10) if _luhn_ok(body + str(c)))
    grouped = " ".join(num[i:i + 4] for i in range(0, 16, 4))
    assert _no_digit_run(scrub_pii(f"card {grouped}"), 12)
