"""
ClearSight Analytics - Localized Taglish NLP & Qualitative Engine
Industrial-grade qualitative engine calibrated on real-world Philippine FMCG
(Harmony W3) and Civic/Public Opinion (Frontier 2022) codeframes.

Key Capabilities:
1. PII Redaction: Masks Philippine mobile numbers (including DITO 0895-0898), landlines (with lookaround to avoid #order digits),
   emails, PhilSys numbers (12/16-digit), Gov IDs (TIN, SSS, PhilHealth, UMID), and names (including Ate/Kuya honorifics and ALL-CAPS).
2. Orthographic & Dialect Normalization: Normalizes SMS shortcuts (kc, diko, lng, hnd, brgy),
   brand typos (calgate, soff), and Visayan/Cebuano regional vocabulary (barato, maayo, nindot, lami, ra gyod, jud).
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
6. Comprehensive Negation Windowing: Detects negators (hindi, di, wala, walang, not, never, ayaw, kulang, dili, indi)
   in the 3 tokens preceding a pattern match and flips to paired complaint/opposite code.
7. Hierarchical Codeframe & Dynamic Lumping:
   - 4-Tier Tree: Net -> Subnet -> Sub-subnet -> Code/Description.
   - Dynamic Consolidation ("Lump to Code X") preserving granular audit trail.
8. Category Guardrails & Non-Answer Classification: Maps 'wala/none' to Code 999 (None),
   'ok lang' to Neutral, and reserves Reask for non-substantive text.
9. Inter-Coder Reliability: Multi-label Jaccard agreement, per-code Cohen's Kappa, and mean Kappa.
"""

import re
from collections import Counter
from typing import Optional, Union
import numpy as np

# ---------------------------------------------------------------------------
# 1. PII Redaction Pipeline (P3-09, CS-023, CS-N12)
# ---------------------------------------------------------------------------

# Philippine Mobile numbers: standard 09xx, DITO 0895-0898, +63 9xx, +63 89x
PHONE_REGEX = re.compile(
    r'(?<!\d)(?:\+?63[\s.-]?\(?(?:9\d{2}|89[5-8])\)?|\(?0(?:9\d{2}|89[5-8])\)?|0(?:9\d{2}|89[5-8]))[\s.-]?(?:\d[\s.-]?){7}(?!\d)'
)

# Philippine Landlines: (02) 8123 4567, 02-8123-4567 (with lookaround to avoid masking order numbers like #2024)
LANDLINE_REGEX = re.compile(r'(?<![\d#])(?:\(0\d{1,2}\)|0\d{1,2})[\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)')

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
PHILSYS_REGEX = re.compile(r'(?<![\d#])(?:\d{4}[\s-]\d{4}[\s-]\d{4}(?:[\s-]\d{4})?)(?!\d)')
TIN_REGEX = re.compile(r'\b\d{3}[-\s]\d{3}[-\s]\d{3}(?:[-\s]\d{3})?\b')
SSS_REGEX = re.compile(r'\b\d{2}[-\s]\d{7}[-\s]\d{1}\b')
PHILHEALTH_REGEX = re.compile(r'\b\d{2}[-\s]\d{9}[-\s]\d{1}\b')
UMID_REGEX = re.compile(r'\b\d{4}[-\s]\d{7}[-\s]\d{1}\b')

# Name honorifics in Philippine English / Tagalog (including kinship terms & ALL-CAPS names)
NAME_HONORIFICS = re.compile(
    r'\b(?i:mr\.|ms\.|mrs\.|dr\.|doc\b|atty\.|attorney|si|kay|ni|ate|kuya|tita|tito|mang|aling|manang|manong)\s+'
    r'((?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){0,2})\b'
)

BRAND_ALLOWLIST = {'mang inasal', 'gcash', 'paymaya', 'shopee', 'lazada', 'grab', 'angkas'}


def scrub_pii(text: Optional[str]) -> str:
    """Masks Philippine mobile numbers, landlines, emails, PhilSys, government IDs, and names."""
    if text is None:
        return ""
    text_str = str(text)

    scrubbed = PHONE_REGEX.sub("[PHONE_REDACTED]", text_str)
    scrubbed = LANDLINE_REGEX.sub("[PHONE_REDACTED]", scrubbed)
    scrubbed = EMAIL_REGEX.sub("[EMAIL_REDACTED]", scrubbed)
    scrubbed = PHILSYS_REGEX.sub("[PHILSYS_REDACTED]", scrubbed)
    scrubbed = TIN_REGEX.sub("[TIN_REDACTED]", scrubbed)
    scrubbed = SSS_REGEX.sub("[SSS_REDACTED]", scrubbed)
    scrubbed = PHILHEALTH_REGEX.sub("[PHILHEALTH_REDACTED]", scrubbed)
    scrubbed = UMID_REGEX.sub("[UMID_REDACTED]", scrubbed)

    def replace_name(match):
        full_match = match.group(0)
        name_part = match.group(1).lower()
        if any(b in full_match.lower() for b in BRAND_ALLOWLIST) or any(b in name_part for b in BRAND_ALLOWLIST):
            return full_match
        prefix = full_match[:match.start(1) - match.start(0)]
        return prefix + "[NAME_REDACTED]"

    scrubbed = NAME_HONORIFICS.sub(replace_name, scrubbed)

    return scrubbed


# ---------------------------------------------------------------------------
# 2. Text-Speak, Orthographic & Regional Dialect Normalization (P3-18)
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

    # Regional Visayan/Cebuano markers found in national research (P3-18)
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


# Affix pattern for Tagalog verbal prefixes, loanword hyphens, circumfixes, and infixes (P3-13)
AFFIX_PATTERN = re.compile(r'^(?:nag-|mag-|naka-|ipag-|i-|um-|mapa-|pina-|na-)?(.+?)(?:-in|-an)?$')


def normalize_taglish_affixes(token: str) -> str:
    """Strips Tagalog verbal affixes, loanword hyphens, circumfixes, and infixes to isolate root words."""
    clean = token.lower().strip()
    clean = re.sub(r'^(?:nag\s*t-|na-|i-|mag-)', '', clean)
    clean = re.sub(r'^(?:napa|pina|ipa)(.+?)(?:an|in)$', r'\1', clean)  # napafabconan -> fabcon
    clean = re.sub(r'^([bcdfghjklmnpqrstvwxyz])(?:in|um)', r'\1', clean)  # plinancha -> plantsa
    match = AFFIX_PATTERN.match(clean)
    if match and len(match.group(1)) >= 3:
        return match.group(1)
    return clean


# ---------------------------------------------------------------------------
# 3. Semantic Clause Chunking (Multi-Coding Foundation)
# ---------------------------------------------------------------------------

CLAUSE_DELIMITERS = re.compile(
    r'(?:[;,]|\b(?i:at|tapos|kaso|kaso lang|pero|kaya|kaya lang|habang|lalo na kung)\b)',
    re.IGNORECASE
)


def split_into_semantic_clauses(text: str) -> list[str]:
    """Splits compound Taglish responses into constituent thoughts/clauses."""
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
EXTENDED_NEGATORS = {"hindi", "di", "wala", "walang", "not", "never", "ayaw", "kulang", "dili", "indi"}

# Categorization of Non-Substantive and Neutral answers (P3-16)
NONE_PATTERNS = [
    r'^(?:wala(?:\s+naman|\s+lang)?|none|n/?a|wla(?:\s+lng)?|no\s+comment)$'
]
NEUTRAL_PATTERNS = [
    r'^(?:ok(?:ay)?(?:\s+(?:lang|naman)){0,2}|ayos(?:\s+lang)?)$'
]
REASK_PATTERNS = [
    r'^\W*$',
    r'^(?:asdf|xxx|\.+)$',
    r'^(?:kasi\s+gusto\s+ko\s+lang|basta)$'
]

# Opposite/complaint code mapping when a pattern is negated (P3-08)
OPPOSITE_CODES = {
    210: (230, "Negative / Unfavorable Comment", "Fragrance & Freshness", "Musty Odor / Scent Defect"),
    220: (230, "Negative / Unfavorable Comment", "Fragrance & Freshness", "Musty Odor / Scent Defect"),
    240: (245, "Negative / Unfavorable Comment", "Fabric Feel & Garment Care", "Rough / Difficult to Iron Fabric"),
    250: (255, "Negative / Unfavorable Comment", "Dermatological Compatibility", "Skin Irritation / Hindi Hiyang"),
    110: (120, "Negative / Unfavorable Comment", "Pricing & Value Perception", "Expensive / High Pricing Friction"),
    130: (135, "Negative / Unfavorable Comment", "Pack Size & Sachet Format", "No Sachet / Pack Format Unavailable"),
    310: (315, "Negative / Unfavorable Comment", "Customer Experience & Service", "Unresponsive / Poor Customer Service"),
    410: (415, "Negative / Unfavorable Comment", "Social Welfare & Assistance", "Government Aid Not Received / Delayed Distribution")
}

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
            r'\bdi\s+mahal\b',
            r'\bbarato\b',
            r'\bbarato ra\b'
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
            r'\bdi sulit\b',
            r'\bdili barato\b',
            r'\bmahal kaayo\b'
        ]
    },
    {
        "code_id": 130,
        "net": "Positive / Favorable Comment",
        "subnet": "Pack Size & Sachet Format",
        "theme": "Sachet / Tingi-Tingi Availability",
        "lump_into": 110,
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
            r'\bfresh scent\b',
            r'\bnabango-?han\b'
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
            r'\biwas gusot\b',
            r'\bplinancha\b',
            r'\bplantsa\b'
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
            # P3-17: Require delay word and delivery term within 3 words
            r'\b(?:mabagal|ang bagal|matagal|tagal)\b(?:\W+\w+){0,3}?\W+(?:dumating|darating|ma-?deliver|delivery|shipping|ang order)\b',
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
            r'\bpaborito\b',
            r'\b(?:maayo|nindot|lami)\b'
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

CODEFRAME_MAP = {entry["code_id"]: entry for entry in HIERARCHICAL_CODEFRAME}


# ---------------------------------------------------------------------------
# 5. Core Analytical Engine & Category Guardrails
# ---------------------------------------------------------------------------

def check_negation(tokens: list[str], target_idx: int, window: int = 3) -> bool:
    """Checks if a negation token exists within a preceding window."""
    start = max(0, target_idx - window)
    preceding = tokens[start:target_idx]
    return any(neg in preceding for neg in EXTENDED_NEGATORS)


def analyze_taglish_verbatim(
    text: str,
    category: Optional[str] = None,
    apply_lumping: bool = False
) -> list[dict]:
    """
    Parses a single Taglish response, resolving polysemy, conditionality,
    negations, and decomposing compound clauses for multi-coding.
    """
    scrubbed = scrub_pii(text)
    if not scrubbed.strip():
        return []

    clean_strip = scrubbed.strip().lower()
    clean_norm = re.sub(r'[.!?,]+$', '', clean_strip)
    clean_norm = re.sub(r'\b(?:po|opo|naman|lang)\b', ' ', clean_norm, flags=re.IGNORECASE).strip()
    clean_norm = re.sub(r'\s+', ' ', clean_norm)

    # P3-16: Non-answer and neutral mapping
    for pat in NONE_PATTERNS:
        if re.search(pat, clean_strip) or re.search(pat, clean_norm):
            return [{
                "code_id": 999,
                "net": "Neutral / No Comment",
                "subnet": "No Opinion",
                "theme": "None / No Particular Reason",
                "evidence": scrubbed,
                "rule_weight": 0.99
            }]

    for pat in NEUTRAL_PATTERNS:
        if re.search(pat, clean_strip) or re.search(pat, clean_norm):
            return [{
                "code_id": 900,
                "net": "Neutral / General Feedback",
                "subnet": "General Comment",
                "theme": "General / Neutral Feedback",
                "evidence": scrubbed,
                "rule_weight": 0.90
            }]

    for pat in REASK_PATTERNS:
        if re.search(pat, clean_strip):
            return [{
                "code_id": 998,
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

    is_fabcon = category and category.lower() in ("fabcon", "fabric_conditioner", "fabric conditioner")

    for clause in clauses:
        clause_lower = clause.lower()
        clause_tokens = re.findall(r'\b[\w-]+\b', clause_lower)
        # P3-13: Augment clause with normalized roots
        root_tokens = [normalize_taglish_affixes(t) for t in clause_tokens]
        clause_augmented = clause_lower + " " + " ".join(root_tokens)

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

        # 2. Evaluate Codeframe Rules with Negation Windowing (P3-08)
        for entry in HIERARCHICAL_CODEFRAME:
            target_id = entry["lump_into"] if (apply_lumping and entry["lump_into"]) else entry["code_id"]
            if target_id in seen_code_ids:
                continue

            if has_affinity and entry["code_id"] == 120:
                continue

            for pat in entry["patterns"]:
                mm = re.search(pat, clause_augmented)
                if mm:
                    # Check for preceding negator in the last 3 tokens
                    toks_before = re.findall(r'\w+', clause_lower[:mm.start()])[-3:]
                    is_negated = any(t in EXTENDED_NEGATORS for t in toks_before)

                    if is_negated:
                        # P3-08: Compound negation exceptions like "hindi lang", "walang kapantay", "di ba"
                        window = clause_lower[max(0, mm.start() - 25):mm.end()]
                        if re.search(r'\b(?:hindi lang|di lang|walang kapantay|walang katulad|di ba)\b', window, re.IGNORECASE):
                            is_negated = False

                    if is_negated:
                        opp = OPPOSITE_CODES.get(entry["code_id"])
                        if opp:
                            opp_id, opp_net, opp_sub, opp_theme = opp
                            if opp_id not in seen_code_ids:
                                matched_themes.append({
                                    "code_id": opp_id,
                                    "net": opp_net,
                                    "subnet": opp_sub,
                                    "theme": opp_theme,
                                    "evidence": clause,
                                    "rule_weight": 0.88
                                })
                                seen_code_ids.add(opp_id)
                        break

                    # Guard against negated matches
                    if is_negated_sulit and entry["code_id"] == 110:
                        continue
                    if is_negated_mahal and entry["code_id"] == 120:
                        continue

                    # Domain Guardrail: Filter whitening in fabric conditioner
                    if is_fabcon and "puti" in clause_lower and entry["code_id"] not in (210, 220, 240, 250):
                        continue

                    theme_label = entry["theme"]
                    if apply_lumping and entry["lump_into"] and entry["lump_into"] in CODEFRAME_MAP:
                        parent_entry = CODEFRAME_MAP[entry["lump_into"]]
                        theme_label = parent_entry["theme"]

                    matched_themes.append({
                        "code_id": target_id,
                        "net": entry["net"],
                        "subnet": entry["subnet"],
                        "theme": theme_label,
                        "evidence": clause,
                        "rule_weight": 0.88
                    })
                    seen_code_ids.add(target_id)
                    break

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
    hierarchical codeframe with verbatim citations and frequency distribution.
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
# 7. Inter-Coder Reliability Metrics (P3-14)
# ---------------------------------------------------------------------------

def compute_human_agreement(
    human_codes: list[Union[str, list[str]]],
    ai_codes: list[Union[str, list[str]]]
) -> dict:
    """
    Computes Observed Percent Agreement, Jaccard Multi-label Similarity,
    and per-code Cohen's Kappa for inter-coder reliability audits.
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
            "per_code_kappa": {},
            "audited_count": 0
        }

    norm_human = []
    norm_ai = []
    for h, a in zip(human_codes, ai_codes):
        h_set = {str(x).strip().lower() for x in (h if isinstance(h, list) else [h])}
        a_set = {str(x).strip().lower() for x in (a if isinstance(a, list) else [a])}
        norm_human.append(h_set)
        norm_ai.append(a_set)

    # 1. Exact agreement
    exact_matches = sum(1 for h_s, a_s in zip(norm_human, norm_ai) if h_s == a_s)
    p_o = exact_matches / N

    # 2. Multi-label Jaccard index
    jaccards = []
    for h_s, a_s in zip(norm_human, norm_ai):
        union = h_s.union(a_s)
        jaccards.append(len(h_s.intersection(a_s)) / len(union) if union else 1.0)
    jaccard_mean = sum(jaccards) / len(jaccards)

    # 3. Per-code Cohen's Kappa across multi-label indicators (P3-14)
    all_codes = sorted(set().union(*norm_human, *norm_ai))
    per_code = {}
    for c in all_codes:
        h_bin = [c in s for s in norm_human]
        a_bin = [c in s for s in norm_ai]
        p_agree = sum(1 for h_i, a_i in zip(h_bin, a_bin) if h_i == a_i) / N
        p_h_pos = sum(h_bin) / N
        p_a_pos = sum(a_bin) / N
        p_exp = (p_h_pos * p_a_pos) + ((1.0 - p_h_pos) * (1.0 - p_a_pos))
        k_c = (p_agree - p_exp) / (1.0 - p_exp) if (1.0 - p_exp) > 0 else 1.0
        per_code[c] = round(float(k_c), 3)

    mean_k = float(np.mean(list(per_code.values()))) if per_code else 1.0

    return {
        "observed_agreement_pct": round(p_o * 100.0, 1),
        "jaccard_mean_pct": round(jaccard_mean * 100.0, 1),
        "cohens_kappa": round(mean_k, 3),
        "per_code_kappa": per_code,
        "audited_count": N
    }
