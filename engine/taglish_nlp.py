"""
Sukat by Lunsad - Localized Taglish NLP & Qualitative Guardrails Engine
Handles:
1. Client-Side Regex PII Masking (RA 10173 Compliance)
2. Taglish Morphosyntactic Disambiguation & Polysemy Resolution
3. Human-in-the-Loop Lock-Step Protocol & Inter-Coder Reliability
"""

import re
from collections import Counter

# ---------------------------------------------------------------------------
# 1. PII Redaction Pipeline (Zero-Cloud Data Sovereignty)
# ---------------------------------------------------------------------------

PHONE_REGEX = re.compile(r'(?:(?:\+63)|0)[9]\d{2}[-\s]?\d{3}[-\s]?\d{4}\b')
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')

def scrub_pii(text: str) -> str:
    """Masks Philippine mobile numbers and email addresses client-side."""
    if not isinstance(text, str):
        return ""
    scrubbed = PHONE_REGEX.sub("[PHONE_REDACTED]", text)
    scrubbed = EMAIL_REGEX.sub("[EMAIL_REDACTED]", scrubbed)
    return scrubbed


# ---------------------------------------------------------------------------
# 2. Taglish Morphosyntax & Polysemy Disambiguation Rules
# ---------------------------------------------------------------------------

PRICE_KEYWORDS = {"presyo", "bayad", "shipping", "sf", "fee", "cost", "gastos", "bili", "order", "price"}
AFFINITY_KEYWORDS = {"ko", "namin", "talaga", "customer", "serbisyo", "ganda", "loyal", "love"}

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
        "patterns": [r'\bmabagal\b.*(?:deliver|dating|shipping)', r'\btagal\b', r'\bdelay\b', r'\bhindi dumating\b']
    },
    {
        "theme": "Responsive Customer Service",
        "polarity": "Positive",
        "patterns": [r'\bmabilis mag-reply\b', r'\bmababait\b', r'\bhelpful\b', r'\baccommodating\b']
    },
    {
        "theme": "Damaged / Defective Packaging",
        "polarity": "Negative",
        "patterns": [r'\bsira\b', r'\byupi\b', r'\bbasag\b', r'\btagas\b', r'\bdamaged\b', r'\bpackaging\b']
    }
]

def analyze_taglish_verbatim(text: str) -> list[dict]:
    """
    Parses a single Taglish response, resolving polysemy and extracting themes.
    """
    scrubbed = scrub_pii(text)
    lower = scrubbed.lower()
    matched_themes = []
    
    # Polysemy check for 'mahal'
    if "mahal" in lower:
        tokens = set(re.findall(r'\w+', lower))
        if tokens.intersection(PRICE_KEYWORDS):
            matched_themes.append({
                "theme": "Expensive / High Pricing Friction",
                "evidence": scrubbed,
                "confidence": 0.92
            })
        elif tokens.intersection(AFFINITY_KEYWORDS):
            matched_themes.append({
                "theme": "Strong Brand Affinity / Loyalty",
                "evidence": scrubbed,
                "confidence": 0.88
            })
            
    # Pattern matching for predefined commercial themes
    for rule in TAGLISH_THEME_RULES:
        for pat in rule["patterns"]:
            if re.search(pat, lower):
                # Avoid duplicating if already handled by polysemy check
                if not any(t["theme"] == rule["theme"] for t in matched_themes):
                    matched_themes.append({
                        "theme": rule["theme"],
                        "evidence": scrubbed,
                        "confidence": 0.85
                    })
                break
                
    if not matched_themes:
        matched_themes.append({
            "theme": "General Feedback / Other",
            "evidence": scrubbed,
            "confidence": 0.60
        })
        
    return matched_themes


def batch_code_open_ends(verbatims: list[str]) -> dict:
    """
    Codes an entire battery of open-ended answers, generating a standardized
    English codeframe with exact verbatim citations and frequency distribution.
    """
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
            if len(theme_citations[theme]) < 5:  # Store top 5 verbatim proofs
                theme_citations[theme].append({
                    "response_id": idx + 1,
                    "quote": m["evidence"]
                })
                
    # Sort themes by volume
    sorted_codeframe = []
    total_responses = max(1, len(verbatims))
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


def compute_human_agreement(human_codes: list[str], ai_codes: list[str]) -> float:
    """
    Computes observed percent agreement between Human Reviewer and AI Coder.
    """
    if not human_codes or len(human_codes) != len(ai_codes):
        return 0.0
    agreements = sum(1 for h, a in zip(human_codes, ai_codes) if str(h).strip().lower() == str(a).strip().lower())
    return round((agreements / len(human_codes)) * 100.0, 1)
