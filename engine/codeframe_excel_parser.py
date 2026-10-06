"""
Excel-driven Data Processor (DP) Codeframe Parser for ClearSight.

Enables zero-hardcoding dynamic codeframe ingestion from Microsoft Excel (.xlsx) workbooks.
Supports:
* Arbitrary hierarchy depth: Level 0 (Sentiment) -> Level 1 (NET) -> Level 2 (Subnet)
  -> Level 3 (Sub-Subnet) -> Level 4/5 (Leaf Codes).
* Global Code ID uniqueness validation (zero collision guarantee).
* Automatic extraction of Themes, Anchored Verbatims (exemplars), and DP instructions.
* Dynamic keyword generation from theme labels and anchor quotes.
* Seamless compilation into ClearSight's validated codeframe schema (schema_version: 1).
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import openpyxl

from engine.codeframe_loader import CodeframeError, validate_codeframe
from engine.tl_morph import tokenize, stem, stem_phrase

RE_NET = re.compile(r"\b\(?NET\)?\b", re.IGNORECASE)
RE_SUBNET = re.compile(r"\b\(?Sub-?net\)?\b", re.IGNORECASE)
RE_SUB_SUBNET = re.compile(r"\b\(?Sub-?sub-?net\)?\b", re.IGNORECASE)
RE_SUB_SUB_SUBNET = re.compile(r"\b\(?Sub-?sub-?sub-?net\)?\b", re.IGNORECASE)

RE_FAVORABLE = re.compile(r"\b(favorable|positive|accomplishment|accomplishments|satisfaction|good|better)\b", re.IGNORECASE)
RE_UNFAVORABLE = re.compile(r"\b(unfavorable|negative|concern|concerns|problem|problems|worse|dissatisfaction|deficit)\b", re.IGNORECASE)

# Standard Tagalog / English stopwords to filter when extracting keyword stems from labels
STOPWORDS = {
    "ang", "mga", "ng", "sa", "sa mga", "si", "ni", "kay", "ay", "at", "o", "nang",
    "na", "pa", "ba", "po", "opo", "din", "rin", "daw", "raw", "naman", "kasi", "kaya",
    "kung", "kapag", "para", "dahil", "habang", "pero", "kaso", "kahit", "the", "a", "an",
    "and", "or", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was",
    "were", "be", "been", "have", "has", "had", "do", "does", "did", "from", "etc"
}


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _slugify(text: str, code_id: Optional[int] = None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.lower()).strip("_")
    if not cleaned:
        cleaned = "topic"
    if code_id is not None:
        cleaned = f"{cleaned[:50]}_{code_id}"
    return cleaned[:64]


def _extract_keywords_from_text(label: str, exemplars: List[str]) -> List[str]:
    """Generate high-precision keyword anchors from the label and anchor verbatims."""
    phrases: Set[str] = set()
    label_clean = re.sub(r"\(.*?\)", "", label).strip()
    if label_clean and len(label_clean) <= 80:
        phrases.add(label_clean.lower())

    # Split label into meaningful 2-word and 3-word n-grams and significant unigrams
    words = [w for w in re.findall(r"[a-zA-ZñÑ0-9-]+", label_clean.lower()) if w not in STOPWORDS and len(w) > 2]
    for w in words:
        phrases.add(w)
    for i in range(len(words) - 1):
        phrases.add(f"{words[i]} {words[i+1]}")

    for ex in exemplars:
        ex_clean = ex.strip().strip('"').strip("'").lower()
        ex_words = [w for w in re.findall(r"[a-zA-ZñÑ0-9-]+", ex_clean) if w not in STOPWORDS and len(w) > 2]
        for w in ex_words:
            if len(w) > 3:
                phrases.add(w)
        for i in range(len(ex_words) - 1):
            phrase = f"{ex_words[i]} {ex_words[i+1]}"
            if len(phrase) <= 80:
                phrases.add(phrase)

    # Return sorted non-empty keywords capped to 200 per topic
    return sorted([p for p in phrases if len(p) <= 80])[:200]


class CodeframeNormalizer:
    """
    Normalizes diverse survey codeframe files (CSV with BOM/CP1252, XLSX, XLS)
    with non-standardized column headers (e.g. Theme, Category, Net, Subnet, Code, Label, ID)
    into validated ClearSight codeframe entities.
    """
    SYNONYM_MAP = {
        "id": ["theme_id", "code_id", "id", "tag_id", "code", "codes", "item_id"],
        "name": ["theme", "theme_name", "label", "tag", "concept", "theme_standardized_label", "sub_category"],
        "net_group": ["net", "subnet", "parent", "parent_theme", "group", "net_group", "thematic_group", "section", "category", "category_name"],
        "description": ["description", "definition", "notes", "criteria", "dp_instructions", "instructions", "dp_instruction"],
        "exemplars": ["anchored_verbatims", "exemplars", "quotes", "verbatims", "raw_quotes", "examples", "sample_verbatims"]
    }

    @classmethod
    def parse_tabular_codeframe(
        cls,
        file_input: Union[str, Path, bytes, io.BytesIO],
        filename: str = "codeframe.csv",
        codeframe_name: Optional[str] = None
    ) -> Dict[str, Any]:
        import pandas as pd

        if isinstance(file_input, bytes):
            buf = io.BytesIO(file_input)
        elif isinstance(file_input, (str, Path)):
            with open(file_input, "rb") as f:
                buf = io.BytesIO(f.read())
        elif isinstance(file_input, io.BytesIO):
            buf = file_input
        else:
            raise CodeframeError("Invalid input for CodeframeNormalizer.")

        fn_lower = filename.lower()
        if fn_lower.endswith(".csv"):
            try:
                buf.seek(0)
                df = pd.read_csv(buf, encoding="utf-8-sig")
            except Exception:
                try:
                    buf.seek(0)
                    df = pd.read_csv(buf, encoding="cp1252")
                except Exception as e:
                    raise CodeframeError(f"Failed to read CSV codeframe: {e}")
        elif fn_lower.endswith((".xlsx", ".xls")) or (len(buf.getvalue()) > 4 and buf.getvalue()[:4] == b"PK\x03\x04"):
            try:
                buf.seek(0)
                df = pd.read_excel(buf)
            except Exception as e:
                raise CodeframeError(f"Failed to read Excel codeframe: {e}")
        else:
            try:
                buf.seek(0)
                df = pd.read_csv(buf, encoding="utf-8-sig")
            except Exception:
                try:
                    buf.seek(0)
                    df = pd.read_excel(buf)
                except Exception as e:
                    raise CodeframeError(f"Unsupported codeframe file format: {e}")

        if df is None or len(df) == 0:
            raise CodeframeError("Uploaded codeframe contains no data.")

        # Normalize column names using SYNONYM_MAP
        normalized_cols: Dict[str, str] = {}
        used_keys = set()
        for col in df.columns:
            clean_col = re.sub(r"[^\w\s]", "", str(col)).strip().lower().replace(" ", "_")
            for standard_key, synonyms in cls.SYNONYM_MAP.items():
                if standard_key not in used_keys and (clean_col in synonyms or any(s == clean_col for s in synonyms)):
                    normalized_cols[col] = standard_key
                    used_keys.add(standard_key)
                    break

        df = df.rename(columns=normalized_cols)
        if "name" not in df.columns:
            text_cols = df.select_dtypes(include=["object"]).columns
            if len(text_cols) > 0:
                df = df.rename(columns={text_cols[0]: "name"})
            else:
                df["name"] = df.iloc[:, 0].astype(str)

        topics = []
        cf_title = codeframe_name or Path(filename).stem.replace("_", " ").title()

        current_net = "General Feedback (NET)"
        current_subnet = "Responses (Subnet)"

        for idx, row in df.iterrows():
            name_val = str(row.get("name", "")).strip()
            if not name_val or name_val.lower() == "nan":
                continue

            if RE_NET.search(name_val):
                current_net = name_val
                continue
            if RE_SUBNET.search(name_val):
                current_subnet = name_val
                continue

            net_val = str(row.get("net_group", "")).strip() if pd.notna(row.get("net_group")) else current_net
            if net_val and net_val.lower() != "nan":
                if not net_val.endswith("(NET)") and not net_val.endswith("(Subnet)"):
                    net_val = f"{net_val} (Subnet)"
            else:
                net_val = current_subnet

            raw_id = row.get("id")
            cid = None
            if pd.notna(raw_id):
                try:
                    cid = int(float(str(raw_id).strip()))
                except (ValueError, TypeError):
                    cid = idx + 101
            else:
                cid = idx + 101

            exemplars_val = row.get("exemplars")
            exs = []
            if pd.notna(exemplars_val) and str(exemplars_val).strip() and str(exemplars_val).lower() != "nan":
                exs = [str(exemplars_val).strip()]

            desc_val = str(row.get("description", "")).strip() if pd.notna(row.get("description")) else ""
            if desc_val.lower() == "nan":
                desc_val = ""

            slug = _slugify(name_val, code_id=cid)
            keywords = _extract_keywords_from_text(name_val, exs)

            pol = "pos" if (RE_FAVORABLE.search(name_val) or RE_FAVORABLE.search(net_val)) else ("neg" if (RE_UNFAVORABLE.search(name_val) or RE_UNFAVORABLE.search(net_val)) else "pos")

            topics.append({
                "id": slug,
                "net": current_net,
                "subnet": net_val,
                "codes": {
                    pol: {"code_id": cid, "label": name_val}
                },
                "keywords": keywords,
                "pos_keywords": keywords[:5] if pol == "pos" else [],
                "neg_keywords": keywords[:5] if pol == "neg" else [],
                "exemplars": exs,
                "dp_instruction": desc_val
            })

        if not topics:
            raise CodeframeError("Could not extract any valid category topics from the codeframe file.")

        cf_dict = {
            "schema_version": 1,
            "id": _slugify(cf_title),
            "name": cf_title,
            "domain": "survey",
            "topics": topics,
            "special": {
                "general_pos": {"code_id": 980, "label": "General Favorable Comment"},
                "general_neg": {"code_id": 981, "label": "General Unfavorable Comment"},
                "needs_review": {"code_id": 995, "label": "Needs Review"},
                "dont_know": {"code_id": 996, "label": "Don't Know / No Opinion"},
                "neutral": {"code_id": 901, "label": "General Neutral Comment"},
                "none": {"code_id": 999, "label": "None / No Particular Reason"},
                "other": {"code_id": 900, "label": "Other Unspecified"}
            }
        }
        return cf_dict


def parse_excel_codeframe(
    file_source: Union[str, Path, bytes, io.BytesIO],
    codeframe_id: Optional[str] = None,
    codeframe_name: Optional[str] = None,
    domain: str = "general"
) -> Dict[str, Any]:
    """
    Parse an openpyxl workbook stream or path into a compiled ClearSight codeframe dict.

    Expected Column Structure (detected dynamically):
    - Codes: Numeric integer code (Column A or column containing 'code')
    - Label / Theme: Header banners or leaf code descriptions (Column B or 'label' / 'theme')
    - Anchored Verbatims: Representative raw respondent quotes (Column C or 'verbatim')
    - DP Instructions: Lumping or processing directives (Column D or 'instruction')
    """
    if isinstance(file_source, bytes):
        wb = openpyxl.load_workbook(io.BytesIO(file_source), data_only=True, read_only=True)
    elif isinstance(file_source, (str, Path)):
        wb = openpyxl.load_workbook(str(file_source), data_only=True, read_only=True)
    elif isinstance(file_source, io.BytesIO):
        wb = openpyxl.load_workbook(file_source, data_only=True, read_only=True)
    else:
        raise CodeframeError("Invalid file source for Excel codeframe parser.")

    sheet = wb.active
    if sheet is None:
        raise CodeframeError("Excel workbook has no active sheet.")

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise CodeframeError("Uploaded Excel sheet is empty.")

    # Detect header row
    header_idx = -1
    col_code = 0
    col_label = 1
    col_verbatim = 2
    col_instruction = 3

    for r_idx, row in enumerate(rows[:15]):
        row_str = " ".join([_clean_str(c).lower() for c in row if c is not None])
        if "code" in row_str and ("label" in row_str or "theme" in row_str or "message" in row_str):
            header_idx = r_idx
            # Map column indices
            for c_idx, cell in enumerate(row):
                c_text = _clean_str(cell).lower()
                if "code" in c_text:
                    col_code = c_idx
                elif any(k in c_text for k in ("label", "theme", "description", "message")):
                    col_label = c_idx
                elif any(k in c_text for k in ("verbatim", "anchor", "exemplar", "quote")):
                    col_verbatim = c_idx
                elif any(k in c_text for k in ("instruction", "lump", "split", "dp", "comment", "action")):
                    col_instruction = c_idx
            break

    data_rows = rows[header_idx + 1:] if header_idx != -1 else rows

    # State machine tracking active hierarchical path
    active_polarity = "pos"
    active_net = "General (NET)"
    active_subnet = "General (Subnet)"
    active_sub_subnet: Optional[str] = None
    active_sub_sub_subnet: Optional[str] = None

    seen_codes: Dict[int, str] = {}
    seen_topic_ids: Set[str] = set()
    topics: List[Dict[str, Any]] = []

    for row in data_rows:
        if not row:
            continue

        raw_code = row[col_code] if col_code < len(row) else None
        raw_label = row[col_label] if col_label < len(row) else None
        raw_verbatim = row[col_verbatim] if col_verbatim < len(row) else None
        raw_instruction = row[col_instruction] if col_instruction < len(row) else None

        label_str = _clean_str(raw_label)
        verbatim_str = _clean_str(raw_verbatim)
        instruction_str = _clean_str(raw_instruction)

        # Ignore empty lines
        if not label_str and raw_code is None:
            continue

        # Check if this row is a header row (code is None or not an integer)
        is_header = False
        code_int: Optional[int] = None

        if raw_code is None or _clean_str(raw_code) == "":
            is_header = True
        else:
            try:
                # Handle numeric string or float from Excel
                code_float = float(raw_code)
                if code_float.is_integer():
                    code_int = int(code_float)
                else:
                    is_header = True
            except (ValueError, TypeError):
                is_header = True

        if is_header:
            if not label_str:
                continue

            # Update Polarity if detected
            if RE_UNFAVORABLE.search(label_str):
                active_polarity = "neg"
            elif RE_FAVORABLE.search(label_str):
                active_polarity = "pos"

            # Detect Hierarchy Depth from Suffix or Structure
            if RE_SUB_SUB_SUBNET.search(label_str):
                active_sub_sub_subnet = label_str
            elif RE_SUB_SUBNET.search(label_str):
                active_sub_subnet = label_str
                active_sub_sub_subnet = None
            elif RE_SUBNET.search(label_str):
                active_subnet = label_str
                active_sub_subnet = None
                active_sub_sub_subnet = None
            elif RE_NET.search(label_str) or not topics:
                active_net = label_str
                clean_net = re.sub(r'\(.*?\)', '', label_str).strip()
                active_subnet = f"{clean_net} (Subnet)"
                active_sub_subnet = None
                active_sub_sub_subnet = None
            else:
                # Header without suffix tag; treat as Subnet under current NET
                active_subnet = f"{label_str} (Subnet)"
                active_sub_subnet = None
                active_sub_sub_subnet = None
            continue

        # Terminal Leaf Code Row
        assert code_int is not None
        if not label_str:
            # Fallback if label is missing
            label_str = f"Code {code_int}"

        # Global Code ID Uniqueness Validation (Zero Collision Guarantee)
        if code_int in seen_codes:
            prev_label = seen_codes[code_int]
            if prev_label != label_str:
                raise CodeframeError(
                    f"Code ID collision: integer code '{code_int}' is used for two different labels: "
                    f"'{prev_label}' and '{label_str}'. Every code in the question must be unique."
                )
        seen_codes[code_int] = label_str

        # Build topic ID
        topic_id = _slugify(label_str, code_int)
        if topic_id in seen_topic_ids:
            topic_id = f"{topic_id}_{len(seen_topic_ids)}"
        seen_topic_ids.add(topic_id)

        exemplars_list = [verbatim_str] if verbatim_str else []
        keywords_list = _extract_keywords_from_text(label_str, exemplars_list)

        # Build compound subnet title showing full depth
        full_subnet = active_subnet
        if active_sub_subnet:
            full_subnet = f"{active_subnet} > {active_sub_subnet}"
        if active_sub_sub_subnet:
            full_subnet = f"{full_subnet} > {active_sub_sub_subnet}"

        # Determine effective polarity for this code
        code_polarity = active_polarity
        if RE_UNFAVORABLE.search(label_str):
            code_polarity = "neg"
        elif RE_FAVORABLE.search(label_str):
            code_polarity = "pos"

        topic_entry = {
            "id": topic_id,
            "net": active_net[:160],
            "subnet": full_subnet[:160],
            "codes": {
                code_polarity: {
                    "code_id": code_int,
                    "label": label_str[:160]
                }
            },
            "keywords": keywords_list,
            "pos_keywords": keywords_list if code_polarity == "pos" else [],
            "neg_keywords": keywords_list if code_polarity == "neg" else [],
            "exemplars": exemplars_list,
        }

        if instruction_str:
            topic_entry["dp_instruction"] = instruction_str[:160]

        topics.append(topic_entry)

    if not topics:
        raise CodeframeError("No valid code rows could be extracted from the Excel codeframe.")

    cf_id = codeframe_id or _slugify(codeframe_name or "custom_excel_codeframe")
    compiled = {
        "schema_version": 1,
        "id": cf_id,
        "name": (codeframe_name or "Custom DP Codeframe")[:160],
        "domain": domain,
        "topics": topics,
        "special_codes": {
            "other": {"code_id": 900, "label": "General Feedback / Other"},
            "none": {"code_id": 999, "label": "None / No Particular Reason"},
            "dont_know": {"code_id": 996, "label": "Don't Know / Not Sure"},
            "neutral": {"code_id": 901, "label": "General / Neutral Feedback"},
            "needs_review": {"code_id": 995, "label": "Needs Review"},
            "general_pos": {"code_id": 980, "label": "General Favorable Comment"},
            "general_neg": {"code_id": 981, "label": "General Unfavorable Comment"},
        },
        "sentiment_overrides": {},
        "options": {}
    }

    # Validate against ClearSight's production codeframe compiler
    return validate_codeframe(compiled)
