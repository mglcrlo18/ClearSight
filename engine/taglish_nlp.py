"""
ClearSight Analytics - Localized Taglish NLP & Qualitative Engine
Implements:
1. Robust Regex PII Redactor (Philippine Mobiles, Landlines, Gov IDs, Names, Emails)
2. Taglish Morphosyntactic Disambiguation & Affix Normalization
3. Polysemy Resolution for "Mahal" (Affinity vs. Expense) with Negation Windowing
4. Human Lock-Step Protocol with Observed Agreement and Cohen's Kappa
"""

import re
from collections import Counter

# ---------------------------------------------------------------------------
# 1. PII Redaction Pipeline
# ---------------------------------------------------------------------------

# Philippine Mobile numbers: +63 917..., 0917..., 63917..., (0917)... with any delimiter
PHONE_REGEX = re.compile(r'(?:\+?63[\s.-]?\(?9\d{2}\)?|\(?09\d{2}\)?|09\d{2})[\s.-]?(?:\d[\s.-]?){7}\b')

# Philippine Landlines: (02) 8123 4567, 02-8123-4567, etc.
LANDLINE_REGEX = re.compile(r'(?:\(?0\d{1,2}\)?|\b0\d{1,2})[\s.-]?\d{3,4}[\s.-]?\d{4}\b')

# Valid RFC-compliant email without stray '|'
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

# Philippine Government IDs
TIN_REGEX = re.compile(r'\b\d{3}[-\s]\d{3}[-\s]\d{3}(?:[-\s]\d{3})?\b')
SSS_REGEX = re.compile(r'\b\d{2}[-\s]\d{7}[-\s]\d{1}\b')
PHILHEALTH_REGEX = re.compile(r'\b\d{2}[-\s]\d{9}[-\s]\d{1}\b')
UMID_REGEX = re.compile(r'\b\d{4}[-\s]\d{7}[-\s]\d{1}\b')

# Name honorifics in Philippine English / Tagalog
NAME_HONORIFICS = re.compile(
    r'\b(?i:mr\.|ms\.|mrs\.|dr\.|doc\b|atty\.|attorney|si\b|kay\b|ni\b)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b'
)


def scrub_pii(text) -> str:
    """
    Masks Philippine mobile numbers, landlines, emails, government IDs, and names.
    Safely converts non-string inputs to str first.
    """
    if text is None:
        return ""
    text_str = str(text)

    scrubbed = PHONE_REGEX.sub("[PHONE_REDACTED]", text_str)
    scrubbed = LANDLINE_REGEX.sub("[PHONE_REDACTED]", scrubbed)
    scrubbed = EMAIL_REGEX.sub("[EMAIL_REDACTED]", scrubbed)
    scrubbed = TIN_REGEX.sub("[TIN_REDACTED]", scrubbed)
    scrubbed = SSS_REGEX.sub("[SSS_REDACTED]", scrubbed)
    scrubbed = PHILHEALTH_REGEX.sub("[PHILHEALTH_REDACTED]", scrubbed)
    scrubbed = UMID_REGEX.sub("[UMID_REDACTED]", scrubbed)
    scrubbed = NAME_HONORIFICS.sub("[NAME_REDACTED]", scrubbed)

    return scrubbed


# ---------------------------------------------------------------------------
# 2. Taglish Morphosyntax & Polysemy Disambiguation Rules
# ---------------------------------------------------------------------------

# Affix stripper for common Tagalog verbal prefixes/infixes
AFFIX_PATTERN = re.compile(r'^(?:nag-|mag-|naka-|ipag-|i-|um-)?(.+?)(?:-in|-an)?$')

def normalize_taglish_affixes(token: str) -> str:
    """Strips common Tagalog verbal affixes to isolate root words."""
    clean = token.lower().strip()
    match = AFFIX_PATTERN.match(clean)
    if match and len(match.group(1)) >= 3:
        return match.group(1)
    return clean


PRICE_KEYWORDS = {"presyo", "bayad", "shipping", "sf", "fee", "cost", "gastos", "price", "singil", "pamasahe"}
AFFINITY_KEYWORDS = {"ko", "namin", "customer", "serbisyo", "ganda", "loyal", "love", "gusto", "bait"}
NEGATION_WORDS = {"hindi", "di", "wala", "not", "walang", "hndi"}

TAGLISH_THEME_RULES = [
    {
        "theme": "Affordable / High Value (Sulit)",
        "polarity": "Positive",
        "patterns": [r'\bsulit\b', r'\bmura\b', r'\bvalue for money\b', r'\bdiscount\b', r'\btipid\b']
    },
    {
        "theme": "Expensive / High Pricing Friction",
        "polarity": "Negative",
        "patterns": [r'\bmahal\b', r'\boverpriced\b', r'\bgastos\b', r'\blugi\b', r'\bpricey\b']
    },
    {
        "theme": "Slow Logistics / Delivery Delay",
        "polarity": "Negative",
        "patterns": [
            r'(?:mabagal|ang bagal|tagal|matagal).*(?:deliver|dating|shipping|order)',
            r'\b(?:ang\s+)?tagal\s+(?:dumating|ng\s+order)\b',
            r'\bmatagal\s+dumating\b',
            r'\bdelay(?:ed)?\b',
            r'\bhindi\s+dumating\b'
        ]
    },
    {
        "theme": "Responsive Customer Service",
        "polarity": "Positive",
        "patterns": [
            r'\bmabilis mag[-\s]?reply\b',
            r'\bmababait\b',
            r'\bhelpful\b',
            r'\baccommodating\b',
            r'\bresponsive\b'
        ]
    },
    {
        "theme": "Damaged / Defective Packaging",
        "polarity": "Negative",
        "patterns": [
            r'(?:sira|yupi|basag|tagas|damaged|wasak).*(?:packaging|box|balot)',
            r'(?:packaging|box|balot).*(?:sira|yupi|basag|tagas|damaged|wasak)'
        ]
    }
]


def check_negation(tokens: list[str], target_idx: int, window: int = 3) -> bool:
    """Checks if a negation token exists within a preceding window."""
    start = max(0, target_idx - window)
    preceding = tokens[start:target_idx]
    return any(neg in preceding for neg in NEGATION_WORDS)


def analyze_taglish_verbatim(text: str) -> list[dict]:
    """
    Parses a single Taglish response, resolving polysemy, negation, and extracting themes.
    """
    scrubbed = scrub_pii(text)
    lower = scrubbed.lower()
    tokens = re.findall(r'\b\w+\b', lower)
    matched_themes = []

    # 1. Check explicit negated phrases first
    is_negated_mahal = bool(re.search(r'\b(?:hindi|di|hndi|not)\s+(?:masyadong\s+)?mahal\b', lower))
    is_negated_sulit = bool(re.search(r'\b(?:hindi|di|hndi|not)\s+sulit\b', lower))

    if is_negated_mahal:
        matched_themes.append({
            "theme": "Affordable / High Value (Sulit)",
            "evidence": scrubbed,
            "rule_weight": 0.88
        })

    if is_negated_sulit:
        matched_themes.append({
            "theme": "Expensive / High Pricing Friction",
            "evidence": scrubbed,
            "rule_weight": 0.88
        })

    # 2. Polysemy Disambiguation for "mahal" (when not negated - CS-N10 resolution)
    has_affinity = False
    if "mahal" in tokens and not is_negated_mahal:
        token_set = set(tokens)
        has_affinity_phrase = bool(re.search(r'\bmahal\s+(?:na\s+mahal|ko|namin|ng\s+customer)\b', lower)) or ('love' in tokens or 'loyal' in tokens)
        if has_affinity_phrase and not token_set.intersection(PRICE_KEYWORDS):
            has_affinity = True
            matched_themes.append({
                "theme": "Strong Brand Affinity / Loyalty",
                "evidence": scrubbed,
                "rule_weight": 0.95
            })
        elif token_set.intersection(PRICE_KEYWORDS) or any(w in lower for w in ["shipping", "sf", "fee", "cost", "gastos", "presyo", "price"]):
            if not any(t["theme"] == "Expensive / High Pricing Friction" for t in matched_themes):
                matched_themes.append({
                    "theme": "Expensive / High Pricing Friction",
                    "evidence": scrubbed,
                    "rule_weight": 0.92
                })
        else:
            if not any(t["theme"] == "Expensive / High Pricing Friction" for t in matched_themes):
                matched_themes.append({
                    "theme": "Expensive / High Pricing Friction",
                    "evidence": scrubbed,
                    "rule_weight": 0.85
                })

    # 3. Commercial Theme Patterns
    for rule in TAGLISH_THEME_RULES:
        if has_affinity and rule["theme"] == "Expensive / High Pricing Friction":
            continue
        if any(t["theme"] == rule["theme"] for t in matched_themes):
            continue

        for pat in rule["patterns"]:
            match = re.search(pat, lower)
            if match:
                if is_negated_sulit and rule["theme"] == "Affordable / High Value (Sulit)":
                    continue
                if is_negated_mahal and rule["theme"] == "Expensive / High Pricing Friction":
                    continue

                if not any(t["theme"] == rule["theme"] for t in matched_themes):
                    matched_themes.append({
                        "theme": rule["theme"],
                        "evidence": scrubbed,
                        "rule_weight": 0.85
                    })
                break

    if not matched_themes:
        matched_themes.append({
            "theme": "General Feedback / Other",
            "evidence": scrubbed,
            "rule_weight": 0.60
        })

    return matched_themes


def batch_code_open_ends(verbatims: list[str]) -> dict:
    """
    Codes an entire battery of open-ended answers, generating a standardized
    codeframe with verbatim citations and frequency distribution.
    """
    if not verbatims:
        return {
            "total_analyzed": 0,
            "codeframe": [],
            "records": []
        }

    theme_citations = {}
    theme_counts = Counter()
    coded_records = []

    for idx, raw_text in enumerate(verbatims):
        matches = analyze_taglish_verbatim(raw_text)
        record = {
            "response_id": idx + 1,
            "raw_text": scrub_pii(raw_text),
            "assigned_themes": [m["theme"] for m in matches]
        }
        coded_records.append(record)

        for m in matches:
            theme = m["theme"]
            theme_counts[theme] += 1
            if theme not in theme_citations:
                theme_citations[theme] = []
            if len(theme_citations[theme]) < 5:
                theme_citations[theme].append({
                    "response_id": idx + 1,
                    "quote": m["evidence"]
                })

    sorted_codeframe = []
    total_responses = len(verbatims)
    for theme, count in theme_counts.most_common():
        sorted_codeframe.append({
            "theme": theme,
            "count": count,
            "prevalence_pct": round((count / total_responses) * 100.0, 1),
            "evidence_samples": theme_citations.get(theme, [])
        })

    return {
        "total_analyzed": total_responses,
        "codeframe": sorted_codeframe,
        "records": coded_records
    }


def compute_human_agreement(human_codes: list[str], ai_codes: list[str]) -> dict:
    """
    Computes Observed Percent Agreement and Cohen's Kappa for inter-coder reliability.
    """
    if len(human_codes) != len(ai_codes):
        raise ValueError(
            f"Review lengths do not match: {len(human_codes)} human codes vs {len(ai_codes)} AI codes."
        )
    N = len(human_codes)
    if N == 0:
        return {"observed_agreement_pct": 0.0, "cohens_kappa": 0.0, "audited_count": 0}

    agreements = sum(1 for h, a in zip(human_codes, ai_codes) if str(h).strip().lower() == str(a).strip().lower())
    p_o = agreements / N

    # Cohen's kappa expected chance agreement
    all_categories = list(set([str(x).strip().lower() for x in human_codes] + [str(x).strip().lower() for x in ai_codes]))
    p_e = 0.0
    for cat in all_categories:
        p_h = sum(1 for h in human_codes if str(h).strip().lower() == cat) / N
        p_a = sum(1 for a in ai_codes if str(a).strip().lower() == cat) / N
        p_e += (p_h * p_a)

    kappa = (p_o - p_e) / (1.0 - p_e) if (1.0 - p_e) > 0 else 1.0

    return {
        "observed_agreement_pct": round(p_o * 100.0, 1),
        "cohens_kappa": round(kappa, 3),
        "audited_count": N
    }
