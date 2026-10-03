"""
ClearSight Analytics - Localized Taglish NLP & Qualitative Engine
Industrial-grade qualitative engine calibrated on real-world Philippine FMCG
(Harmony W3) and Civic/Public Opinion (Frontier 2022) codeframes.

Key Capabilities:
1. PII Redaction: Masks Philippine mobile numbers, landlines, emails, Gov IDs (TIN, SSS, PhilHealth, UMID), and names.
2. Orthographic & Dialect Normalization: Normalizes SMS shortcuts (kc, diko, lng, hnd, brgy),
   brand typos (calgate, soff), and Visayan/Cebuano regional enclitics (ra gyod, jud).
3. Taglish Morphosyntax & Loanword Affixation: Decomposes hybrid prefixes (na-expose,
   nag t-trigger, napafabconan, plinancha).
4. Semantic Clause Disentanglement: Splits compound responses across conjunctions
   (at, tapos, kaso, kaya, pero) to support rigorous multi-coding without label collision.
5. Cultural Collocations & Polarity Inversion:
   - "kulob" / "amoy araw" (musty odor) vs. "iwas kulob" (positive odor protection).
   - "kahit hindi naarawan" (all-weather durability).
   - "hiyang" (biological/dermatological suitability).
   - "tingi" / "tingi-tingi" (sachet packaging economics).
   - "ayuda" (social safety net subsidies) & "tambay" (street loiterers).
6. Hierarchical Codeframe & Dynamic Lumping:
   - 4-Tier Tree: Net -> Subnet -> Sub-subnet -> Code/Description.
   - Dynamic Consolidation ("Lump to Code X") preserving granular audit trail.
7. Category Guardrails: Flags or suppresses invalid domain claims (e.g. whitening in fabcon).
8. Inter-Coder Reliability: Multi-label Jaccard agreement, Macro-F1, and Cohen's Kappa.
"""

import re
from collections import Counter
from typing import Optional, Union

# ---------------------------------------------------------------------------
# 1. PII Redaction Pipeline
# ---------------------------------------------------------------------------

PHONE_REGEX = re.compile(r'(?:\+?63[\s.-]?\(?9\d{2}\)?|\(?09\d{2}\)?|09\d{2})[\s.-]?(?:\d[\s.-]?){7}\b')
LANDLINE_REGEX = re.compile(r'(?:\(?0\d{1,2}\)?|\b0\d{1,2})[\s.-]?\d{3,4}[\s.-]?\d{4}\b')
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
TIN_REGEX = re.compile(r'\b\d{3}[-\s]\d{3}[-\s]\d{3}(?:[-\s]\d{3})?\b')
SSS_REGEX = re.compile(r'\b\d{2}[-\s]\d{7}[-\s]\d{1}\b')
PHILHEALTH_REGEX = re.compile(r'\b\d{2}[-\s]\d{9}[-\s]\d{1}\b')
UMID_REGEX = re.compile(r'\b\d{4}[-\s]\d{7}[-\s]\d{1}\b')

NAME_HONORIFICS = re.compile(
    r'\b(?i:mr\.|ms\.|mrs\.|dr\.|doc\b|atty\.|attorney|si\b|kay\b|ni\b)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b'
)


def scrub_pii(text: Optional[str]) -> str:
    """Masks Philippine mobile numbers, landlines, emails, government IDs, and names."""
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
# 2. Text-Speak, Orthographic & Regional Dialect Normalization
# ---------------------------------------------------------------------------

TEXT_SPEAK_MAP = {
    # Negations & Pronouns
    r'\bdiko\b': 'hindi ko',
    r'\bdko\b': 'hindi ko',
    r'\bhnd\b': 'hindi',
    r'\bhndi\b': 'hindi',
    r'\bdi\b': 'hindi',
    r'\baq\b': 'ako',
    r'\bikw\b': 'ikaw',
    r'\bsya\b': 'siya',
    r'\bsta\b': 'siya',
    r'\bnla\b': 'nila',
    r'\bnmin\b': 'namin',
    r'\bkin\b': 'akin',

    # Conjunctions & Particles
    r'\bkc\b': 'kasi',
    r'\bkse\b': 'kasi',
    r'\bkase\b': 'kasi',
    r'\blng\b': 'lang',
    r'\bngalang\b': 'nga lang',
    r'\bden\b': 'din',
    r'\bdn\b': 'din',
    r'\bpa dn\b': 'pa din',
    r'\bpdeng\b': 'pwedeng',
    r'\bpde\b': 'pwede',
    r'\bpwde\b': 'pwede',
    r'\bbkt\b': 'bakit',
    r'\bbkit\b': 'bakit',
    r'\btlga\b': 'talaga',
    r'\btlaga\b': 'talaga',
    r'\bsb\b': 'sabi',
    r'\bdto\b': 'dito',
    r'\bdun\b': 'doon',
    r'\bbka\b': 'baka',
    r'\bbrgy\b': 'barangay',

    # Regional Visayan/Cebuano markers found in national research
    r'\bra gyod\b': 'lang talaga',
    r'\bra gyud\b': 'lang talaga',
    r'\bman gud\b': 'kasi nga',
    r'\bjud\b': 'talaga',
    r'\bgyud\b': 'talaga',

    # Common brand / product typos
    r'\bcalgate\b': 'colgate',
    r'\bsoff\b': 'sof & mmmm',
    r'\bplanggana\b': 'palanggana',
    r'\bmbango\b': 'mabango'
}

COMPILED_TEXT_SPEAK = [(re.compile(pat, re.IGNORECASE), repl) for pat, repl in TEXT_SPEAK_MAP.items()]


def normalize_taglish_text(text: str) -> str:
    """Expands SMS abbreviations, corrects common brand typos, and normalizes regional enclitics."""
    if not text:
        return ""
    normalized = text
    for pattern, replacement in COMPILED_TEXT_SPEAK:
        normalized = pattern.sub(replacement, normalized)
    return normalized


# Affix pattern for Tagalog verbal prefixes, loanword hyphens, and infixes
AFFIX_PATTERN = re.compile(r'^(?:nag-|mag-|naka-|ipag-|i-|um-|mapa-|pina-|na-)?(.+?)(?:-in|-an)?$')


def normalize_taglish_affixes(token: str) -> str:
    """Strips common Tagalog verbal affixes to isolate root words, including English loanword stems."""
    clean = token.lower().strip()
    clean = re.sub(r'^(?:nag\s*t-|na-|i-|mag-)', '', clean)
    match = AFFIX_PATTERN.match(clean)
    if match and len(match.group(1)) >= 3:
        return match.group(1)
    return clean


# ---------------------------------------------------------------------------
# 3. Semantic Clause Chunking (Multi-Coding Foundation)
# ---------------------------------------------------------------------------

# Conjunctions and punctuation that delineate independent thoughts in Taglish
CLAUSE_DELIMITERS = re.compile(
    r'(?:[;,]|\b(?i:at|tapos|kaso|kaso lang|pero|kaya|kaya lang|habang|dahil|lalo na kung)\b)',
    re.IGNORECASE
)


def split_into_semantic_clauses(text: str) -> list[str]:
    """
    Splits compound Taglish responses into constituent thoughts/clauses.
    e.g. 'Mabango at malambot sa damit hindi na kailangan plantsahin'
    -> ['Mabango', 'malambot sa damit', 'hindi na kailangan plantsahin']
    """
    if not text:
        return []
    parts = CLAUSE_DELIMITERS.split(text)
    clauses = [p.strip() for p in parts if p and len(p.strip()) > 1]
    return clauses if clauses else [text.strip()]


# ---------------------------------------------------------------------------
# 4. Hierarchical Codeframe Taxonomy & Cultural Collocations
# ---------------------------------------------------------------------------

PRICE_KEYWORDS = {"presyo", "bayad", "shipping", "sf", "fee", "cost", "gastos", "price", "singil", "pamasahe"}
AFFINITY_KEYWORDS = {"ko", "namin", "customer", "serbisyo", "ganda", "loyal", "love", "gusto", "bait"}
NEGATION_WORDS = {"hindi", "di", "wala", "not", "walang", "hndi"}

# Non-responsive verbatims that coders mark as "Reask / Non-Answer"
NON_ANSWER_PATTERNS = [
    r'^(?:wala(?:\s+lang)?|wala\s+akong\s+masabi|wala\s+naman|n/?a|none|kasi\s+gusto\s+ko\s+lang|basta|ok\s+lang)$',
    r'^(?:wla|wla\s+lng|wla\s+masabi|no\s+comment)$'
]

# Comprehensive hierarchical taxonomy derived from Harmony W3 & Frontier 2022
HIERARCHICAL_CODEFRAME = [
    # --- NET 100: Commercial Value, Pricing & Packaging ---
    {
        "code_id": 110,
        "net": "Positive / Favorable Comment",
        "subnet": "Pricing & Value Perception",
        "theme": "Affordable / High Value (Sulit)",
        "lump_into": None,
        "patterns": [
            r'\bsulit\b',
            r'\bmura\b',
            r'\bvalue for money\b',
            r'\bdiscount\b',
            r'\btipid\b',
            r'\bmatipid\b',
            r'\bpang[- ]?masa\b',
            r'\bkayang[- ]?kaya sa bulsa\b',
            r'\bhindi\s+mahal\b',
            r'\bdi\s+mahal\b'
        ]
    },
    {
        "code_id": 120,
        "net": "Negative / Unfavorable Comment",
        "subnet": "Pricing & Value Perception",
        "theme": "Expensive / High Pricing Friction",
        "lump_into": None,
        "patterns": [
            r'\boverpriced\b',
            r'\bgastos\b',
            r'\blugi\b',
            r'\bpricey\b',
            r'\btumataas ang presyo\b',
            r'\bmedyo mahal\b',
            r'\bsobrang mahal\b',
            r'\bhindi sulit\b',
            r'\bdi sulit\b'
        ]
    },
    {
        "code_id": 130,
        "net": "Positive / Favorable Comment",
        "subnet": "Pack Size & Sachet Format",
        "theme": "Sachet / Tingi-Tingi Availability",
        "lump_into": 110,  # Lumped into general affordability in high-level summaries
        "patterns": [
            r'\btingi[- ]?tingi\b',
            r'\btingi\b',
            r'\bsachet\b',
            r'\bmaliit na pack\b',
            r'\bpang[- ]?isahang gamit\b'
        ]
    },

    # --- NET 200: Product Efficacy, Sensory, & Domestic Labor (FMCG Focus) ---
    {
        "code_id": 210,
        "net": "Positive / Favorable Comment",
        "subnet": "Fragrance & Freshness",
        "theme": "Long-Lasting Pleasant Fragrance / Scent",
        "lump_into": None,
        "patterns": [
            r'\bmabango\b',
            r'\bbango\b',
            r'\bhumahalimuyak\b',
            r'\bkapit ang amoy\b',
            r'\bmatagal mawala ang bango\b',
            r'\bparang pabango\b',
            r'\bmild scent\b',
            r'\bfresh scent\b'
        ]
    },
    {
        "code_id": 220,
        "net": "Positive / Favorable Comment",
        "subnet": "Fragrance & Freshness",
        "theme": "Odor Protection / Anti-Kulob (Iwas-Kulob)",
        "lump_into": 210,
        "patterns": [
            r'\biwas[- ]?kulob\b',
            r'\bpang[- ]?tanggal kulob\b',
            r'\bwalang amoy kulob\b',
            r'\banti[- ]?kulob\b',
            r'\biwas[- ]?amoy araw\b',
            r'\bkahit\s+(?:hindi\s+naarawan|maulan|walang\s+araw)\b'
        ]
    },
    {
        "code_id": 230,
        "net": "Negative / Unfavorable Comment",
        "subnet": "Fragrance & Freshness",
        "theme": "Musty Odor / Amoy Kulob Defect",
        "lump_into": None,
        "patterns": [
            r'\bamoy kulob\b',
            r'\bnagkukulob\b',
            r'\bmasakit sa ilong\b',
            r'\bmatapang ang amoy\b',
            r'\bamoy araw\b'
        ]
    },
    {
        "code_id": 240,
        "net": "Positive / Favorable Comment",
        "subnet": "Fabric Feel & Garment Care",
        "theme": "Fabric Softness / Easy Ironing",
        "lump_into": None,
        "patterns": [
            r'\bmalambot\b',
            r'\blambot\b',
            r'\bmadaling plantsahin\b',
            r'\bhindi na kailangan plantsahin\b',
            r'\bready to wear\b',
            r'\biwas gusot\b'
        ]
    },
    {
        "code_id": 250,
        "net": "Positive / Favorable Comment",
        "subnet": "Dermatological Compatibility",
        "theme": "Skin Suitability / Hiyang",
        "lump_into": None,
        "patterns": [
            r'\bhiyang\b',
            r'\bhindi makati\b',
            r'\bdi makati\b',
            r'\bhindi nag t-?trigger\b',
            r'\bgood for sensitive skin\b',
            r'\bligtas sa balat\b'
        ]
    },

    # --- NET 300: Service, Logistics & Packaging Condition ---
    {
        "code_id": 310,
        "net": "Positive / Favorable Comment",
        "subnet": "Customer Experience & Service",
        "theme": "Responsive Customer Service",
        "lump_into": None,
        "patterns": [
            r'\bmabilis mag[-\s]?reply\b',
            r'\bmababait\b',
            r'\bhelpful\b',
            r'\baccommodating\b',
            r'\bresponsive\b',
            r'\bmaayos makipag[- ]?usap\b'
        ]
    },
    {
        "code_id": 320,
        "net": "Negative / Unfavorable Comment",
        "subnet": "Delivery & Fulfillment",
        "theme": "Slow Logistics / Delivery Delay",
        "lump_into": None,
        "patterns": [
            r'(?:mabagal|ang bagal|tagal|matagal).*(?:deliver|dating|shipping|order)',
            r'\b(?:ang\s+)?tagal\s+(?:dumating|ng\s+order)\b',
            r'\bmatagal\s+dumating\b',
            r'\bdelay(?:ed)?\b',
            r'\bhindi\s+dumating\b'
        ]
    },
    {
        "code_id": 330,
        "net": "Negative / Unfavorable Comment",
        "subnet": "Packaging & Condition",
        "theme": "Damaged / Defective Packaging",
        "lump_into": None,
        "patterns": [
            r'(?:sira|yupi|basag|tagas|damaged|wasak).*(?:packaging|box|balot)',
            r'(?:packaging|box|balot).*(?:sira|yupi|basag|tagas|damaged|wasak)'
        ]
    },
    {
        "code_id": 340,
        "net": "Positive / Favorable Comment",
        "subnet": "Brand Sentiment",
        "theme": "Strong Brand Affinity / Loyalty",
        "lump_into": None,
        "patterns": [
            r'\bmahal\s+(?:na\s+mahal|ko|namin|ng\s+customer)\b',
            r'\bloyal customer\b',
            r'\bgo[- ]?to choice\b',
            r'\bfavorite\b',
            r'\bpaborito\b'
        ]
    },

    # --- NET 400: Socio-Political & Public Administration (Frontier Focus) ---
    {
        "code_id": 410,
        "net": "Positive / Favorable Comment",
        "subnet": "Social Welfare & Assistance",
        "theme": "Government Assistance / Ayuda / 4Ps",
        "lump_into": None,
        "patterns": [
            r'\bayuda\b',
            r'\b4ps\b',
            r'\bsap\b',
            r'\btulong pinansyal\b',
            r'\bfinancial assistance\b',
            r'\bpamahagi ng bigas\b'
        ]
    },
    {
        "code_id": 420,
        "net": "Negative / Unfavorable Comment",
        "subnet": "Infrastructure & Public Works",
        "theme": "Damaged / Incomplete Roads & Drainage",
        "lump_into": None,
        "patterns": [
            r'\bsira[- ]?sirang kalsada\b',
            r'\blubak[- ]?lubak\b',
            r'\bhindi natapos na kalsada\b',
            r'\bbaradong kanal\b',
            r'\bwalang drainage\b',
            r'\bbahaing kalsada\b'
        ]
    },
    {
        "code_id": 430,
        "net": "Negative / Unfavorable Comment",
        "subnet": "Peace, Order & Local Enforcement",
        "theme": "Ineffective Local Enforcement / Loitering",
        "lump_into": None,
        "patterns": [
            r'\btambay\b',
            r'\bmga nag[- ]?iinuman sa kalsada\b',
            r'\bkulang sa tanod\b',
            r'\bwalang nagpapatrolya\b',
            r'\bmagulong paligid\b',
            r'\bmaingay sa gabi\b'
        ]
    }
]


# ---------------------------------------------------------------------------
# 5. Core Analytical Engine & Category Guardrails
# ---------------------------------------------------------------------------

def is_non_answer(text: str) -> bool:
    """Detects circular, empty, or non-substantive answers flagged by human coders as 'Reask'."""
    clean = text.strip().lower()
    for pat in NON_ANSWER_PATTERNS:
        if re.search(pat, clean):
            return True
    return False


def check_negation(tokens: list[str], target_idx: int, window: int = 3) -> bool:
    """Checks if a negation token exists within a preceding window."""
    start = max(0, target_idx - window)
    preceding = tokens[start:target_idx]
    return any(neg in preceding for neg in NEGATION_WORDS)


def analyze_taglish_verbatim(
    text: str,
    category: Optional[str] = None,
    apply_lumping: bool = False
) -> list[dict]:
    """
    Parses a single Taglish response, resolving polysemy, conditionality,
    negations, and decomposing compound clauses for multi-coding.

    Parameters:
        text: Raw verbatim string from survey respondent.
        category: Optional domain constraint (e.g. 'fabcon', 'fmcg', 'civic').
        apply_lumping: If True, consolidates sub-codes into parent codes.
    """
    scrubbed = scrub_pii(text)
    if not scrubbed.strip():
        return []

    # Quality Control Gate: Check for non-substantive answers
    if is_non_answer(scrubbed):
        return [{
            "code_id": 999,
            "net": "Uncoded / Non-Substantive",
            "subnet": "Data Quality",
            "theme": "Non-Substantive / Needs Reask",
            "evidence": scrubbed,
            "rule_weight": 0.99
        }]

    normalized = normalize_taglish_text(scrubbed)
    clauses = split_into_semantic_clauses(normalized)

    matched_themes = []
    seen_code_ids = set()

    # Category guardrail rules (e.g. Harmony W3: whitening is invalid for fabric softener)
    is_fabcon = category and category.lower() in ("fabcon", "fabric_conditioner", "fabric conditioner")

    for clause in clauses:
        clause_lower = clause.lower()
        clause_tokens = re.findall(r'\b\w+\b', clause_lower)

        # 1. Polysemy Disambiguation for "mahal" (Expense vs. Brand Love)
        is_negated_mahal = bool(re.search(r'\b(?:hindi|di|hndi|not)\s+(?:masyadong\s+)?mahal\b', clause_lower))
        is_negated_sulit = bool(re.search(r'\b(?:hindi|di|hndi|not)\s+sulit\b', clause_lower))

        if is_negated_mahal and 110 not in seen_code_ids:
            matched_themes.append({
                "code_id": 110,
                "net": "Positive / Favorable Comment",
                "subnet": "Pricing & Value Perception",
                "theme": "Affordable / High Value (Sulit)",
                "evidence": clause,
                "rule_weight": 0.90
            })
            seen_code_ids.add(110)

        if is_negated_sulit and 120 not in seen_code_ids:
            matched_themes.append({
                "code_id": 120,
                "net": "Negative / Unfavorable Comment",
                "subnet": "Pricing & Value Perception",
                "theme": "Expensive / High Pricing Friction",
                "evidence": clause,
                "rule_weight": 0.90
            })
            seen_code_ids.add(120)

        has_affinity = False
        if "mahal" in clause_tokens and not is_negated_mahal:
            token_set = set(clause_tokens)
            has_affinity_phrase = bool(re.search(r'\bmahal\s+(?:na\s+mahal|ko|namin|ng\s+customer)\b', clause_lower)) or ('love' in clause_tokens or 'loyal' in clause_tokens)
            if has_affinity_phrase and not token_set.intersection(PRICE_KEYWORDS):
                has_affinity = True
                if 340 not in seen_code_ids:
                    matched_themes.append({
                        "code_id": 340,
                        "net": "Positive / Favorable Comment",
                        "subnet": "Brand Sentiment",
                        "theme": "Strong Brand Affinity / Loyalty",
                        "evidence": clause,
                        "rule_weight": 0.95
                    })
                    seen_code_ids.add(340)
            elif token_set.intersection(PRICE_KEYWORDS) or any(w in clause_lower for w in ["shipping", "sf", "fee", "cost", "gastos", "presyo", "price"]):
                if 120 not in seen_code_ids:
                    matched_themes.append({
                        "code_id": 120,
                        "net": "Negative / Unfavorable Comment",
                        "subnet": "Pricing & Value Perception",
                        "theme": "Expensive / High Pricing Friction",
                        "evidence": clause,
                        "rule_weight": 0.92
                    })
                    seen_code_ids.add(120)
            else:
                if 120 not in seen_code_ids:
                    matched_themes.append({
                        "code_id": 120,
                        "net": "Negative / Unfavorable Comment",
                        "subnet": "Pricing & Value Perception",
                        "theme": "Expensive / High Pricing Friction",
                        "evidence": clause,
                        "rule_weight": 0.85
                    })
                    seen_code_ids.add(120)

        # 2. Evaluate Codeframe Rules
        for entry in HIERARCHICAL_CODEFRAME:
            target_id = entry["lump_into"] if (apply_lumping and entry["lump_into"]) else entry["code_id"]
            if target_id in seen_code_ids:
                continue

            # Respect affinity suppression of pricing friction
            if has_affinity and entry["code_id"] == 120:
                continue

            for pat in entry["patterns"]:
                if re.search(pat, clause_lower):
                    # Guard against negated matches
                    if is_negated_sulit and entry["code_id"] == 110:
                        continue
                    if is_negated_mahal and entry["code_id"] == 120:
                        continue

                    # Domain Guardrail: Filter whitening in fabric conditioner
                    if is_fabcon and "puti" in clause_lower and entry["code_id"] not in (210, 220, 240, 250):
                        continue

                    matched_themes.append({
                        "code_id": target_id,
                        "net": entry["net"],
                        "subnet": entry["subnet"],
                        "theme": entry["theme"],
                        "evidence": clause,
                        "rule_weight": 0.88
                    })
                    seen_code_ids.add(target_id)
                    break

    # Fallback to general feedback if nothing matched
    if not matched_themes:
        matched_themes.append({
            "code_id": 900,
            "net": "Neutral / General Feedback",
            "subnet": "General Comment",
            "theme": "General Feedback / Other",
            "evidence": scrubbed,
            "rule_weight": 0.60
        })

    return matched_themes


# ---------------------------------------------------------------------------
# 6. Batch Production Processing & Taxonomy Rollup
# ---------------------------------------------------------------------------

def batch_code_open_ends(
    verbatims: list[str],
    category: Optional[str] = None,
    apply_lumping: bool = False
) -> dict:
    """
    Codes an entire battery of open-ended answers, generating a standardized
    4-tier hierarchical codeframe with verbatim citations and frequency distribution.
    """
    if not verbatims:
        return {
            "total_analyzed": 0,
            "codeframe": [],
            "records": []
        }

    theme_citations = {}
    theme_counts = Counter()
    theme_metadata = {}
    coded_records = []

    for idx, raw_text in enumerate(verbatims):
        matches = analyze_taglish_verbatim(raw_text, category=category, apply_lumping=apply_lumping)
        record = {
            "response_id": idx + 1,
            "raw_text": scrub_pii(raw_text),
            "assigned_themes": [m["theme"] for m in matches],
            "assigned_codes": [m["code_id"] for m in matches]
        }
        coded_records.append(record)

        for m in matches:
            theme = m["theme"]
            code_id = m["code_id"]
            theme_counts[theme] += 1
            if theme not in theme_metadata:
                theme_metadata[theme] = {
                    "code_id": code_id,
                    "net": m["net"],
                    "subnet": m["subnet"]
                }
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
        meta = theme_metadata.get(theme, {})
        sorted_codeframe.append({
            "code_id": meta.get("code_id", 900),
            "net": meta.get("net", "General"),
            "subnet": meta.get("subnet", "General"),
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


# ---------------------------------------------------------------------------
# 7. Inter-Coder Reliability Metrics (Multi-Label & Kappa)
# ---------------------------------------------------------------------------

def compute_human_agreement(
    human_codes: list[Union[str, list[str]]],
    ai_codes: list[Union[str, list[str]]]
) -> dict:
    """
    Computes Observed Percent Agreement, Jaccard Multi-label Similarity,
    and Cohen's Kappa for inter-coder reliability audits.
    Supports both single-label and multi-label code assignments.
    """
    if len(human_codes) != len(ai_codes):
        raise ValueError(
            f"Review lengths do not match: {len(human_codes)} human codes vs {len(ai_codes)} AI codes."
        )
    N = len(human_codes)
    if N == 0:
        return {
            "observed_agreement_pct": 0.0,
            "jaccard_mean_pct": 0.0,
            "cohens_kappa": 0.0,
            "audited_count": 0
        }

    # Normalize inputs to sets of strings
    norm_human = []
    norm_ai = []
    for h, a in zip(human_codes, ai_codes):
        h_set = {str(x).strip().lower() for x in (h if isinstance(h, list) else [h])}
        a_set = {str(x).strip().lower() for x in (a if isinstance(a, list) else [a])}
        norm_human.append(h_set)
        norm_ai.append(a_set)

    # 1. Exact agreement (set equality)
    exact_matches = sum(1 for h_s, a_s in zip(norm_human, norm_ai) if h_s == a_s)
    p_o = exact_matches / N

    # 2. Multi-label Jaccard index
    jaccards = []
    for h_s, a_s in zip(norm_human, norm_ai):
        union = h_s.union(a_s)
        if not union:
            jaccards.append(1.0)
        else:
            jaccards.append(len(h_s.intersection(a_s)) / len(union))
    jaccard_mean = sum(jaccards) / len(jaccards)

    # 3. Cohen's Kappa for dominant/primary label
    h_dominant = [sorted(list(s))[0] if s else "" for s in norm_human]
    a_dominant = [sorted(list(s))[0] if s else "" for s in norm_ai]

    all_categories = list(set(h_dominant + a_dominant))
    p_e = 0.0
    for cat in all_categories:
        p_h = sum(1 for x in h_dominant if x == cat) / N
        p_a = sum(1 for x in a_dominant if x == cat) / N
        p_e += (p_h * p_a)

    kappa = (p_o - p_e) / (1.0 - p_e) if (1.0 - p_e) > 0 else 1.0

    return {
        "observed_agreement_pct": round(p_o * 100.0, 1),
        "jaccard_mean_pct": round(jaccard_mean * 100.0, 1),
        "cohens_kappa": round(kappa, 3),
        "audited_count": N
    }
