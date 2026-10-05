"""
Pluggable per-project codeframes for coder v2.

* Codeframes are JSON (or YAML when PyYAML is installed; always ``safe_load``).
* Keywords are LITERAL words/phrases, never regexes, so a project codeframe cannot
  introduce a catastrophic-backtracking pattern (CWE-1333).
* Loading by name is restricted to the bundled ``engine/codeframes`` folder and the
  user's ``$CLEARSIGHT_DATA/codeframes`` folder. Names must match ``^[a-z0-9_-]{1,64}$``
  and the resolved real path must stay inside the folder (CWE-22).
* Files larger than 1 MB, more than 500 topics or 2,000 keywords per topic are rejected.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from engine.tl_morph import register_roots, stem_phrase

BUNDLED_DIR = Path(__file__).resolve().parent / "codeframes"
LEXICON_DIR = Path(__file__).resolve().parent / "lexicons"
NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
MAX_BYTES = 1_000_000
MAX_TOPICS = 500
MAX_KEYWORDS = 2000
MAX_LABEL = 160
MAX_KEYWORD = 80
SPECIAL_KEYS = ("other", "none", "dont_know", "neutral", "needs_review", "general_pos", "general_neg")
DEFAULT_SPECIAL = {
    "other": {"code_id": 900, "label": "General Feedback / Other"},
    "none": {"code_id": 999, "label": "None / No Particular Reason"},
    "dont_know": {"code_id": 996, "label": "Don't Know / Not Sure"},
    "neutral": {"code_id": 901, "label": "General / Neutral Feedback"},
    "needs_review": {"code_id": 995, "label": "Needs Review"},
    "general_pos": {"code_id": 980, "label": "General Favorable Comment"},
    "general_neg": {"code_id": 981, "label": "General Unfavorable Comment"},
}


class CodeframeError(ValueError):
    """Raised for an invalid or unsafe codeframe."""


def user_codeframe_dir() -> Optional[Path]:
    base = os.environ.get("CLEARSIGHT_DATA")
    if not base:
        base = str(Path.home() / ".clearsight")
    return Path(base) / "codeframes"


def _safe_resolve(folder: Path, name: str) -> Optional[Path]:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise CodeframeError("Codeframe name must match ^[a-z0-9_-]{1,64}$.")
    root = folder.resolve()
    for ext in (".json", ".yaml", ".yml"):
        cand = (root / (name + ext))
        if not cand.exists():
            continue
        real = Path(os.path.realpath(cand))
        if os.path.commonpath([str(real), str(root)]) != str(root):
            raise CodeframeError("Codeframe path escapes the codeframe folder.")
        return real
    return None


def _read(path: Path) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise CodeframeError("Codeframe file is larger than 1 MB.")
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # optional
        except ImportError as exc:  # pragma: no cover - depends on env
            raise CodeframeError("YAML codeframes need PyYAML; use JSON instead.") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise CodeframeError("Codeframe must be a JSON object.")
    return data


def _str_list(v: Any, field: str, topic_id: str) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > MAX_KEYWORDS:
        raise CodeframeError(f"Topic '{topic_id}': '{field}' must be a list of at most {MAX_KEYWORDS} strings.")
    out = []
    for k in v:
        if not isinstance(k, str) or not k.strip() or len(k) > MAX_KEYWORD:
            raise CodeframeError(f"Topic '{topic_id}': every '{field}' entry must be a non-empty string up to {MAX_KEYWORD} characters.")
        out.append(k.strip())
    return out


def _code(v: Any, where: str) -> dict:
    if not isinstance(v, dict) or not isinstance(v.get("code_id"), int) or isinstance(v.get("code_id"), bool):
        raise CodeframeError(f"{where}: code must be an object with an integer code_id.")
    label = v.get("label")
    if not isinstance(label, str) or not label.strip() or len(label) > MAX_LABEL:
        raise CodeframeError(f"{where}: label must be a non-empty string up to {MAX_LABEL} characters.")
    return {"code_id": int(v["code_id"]), "label": label.strip()}


def validate_codeframe(data: dict, includes: Optional[list[dict]] = None) -> dict:
    """Validate and compile a codeframe dict. Returns the compiled form used by coder v2."""
    if data.get("schema_version") != 1:
        raise CodeframeError("schema_version must be 1.")
    cf_id = data.get("id")
    if not isinstance(cf_id, str) or not NAME_RE.match(cf_id):
        raise CodeframeError("id must match ^[a-z0-9_-]{1,64}$.")
    topics_in = list(data.get("topics") or [])
    for inc in includes or []:
        topics_in = list(inc.get("topics") or []) + topics_in
    if not isinstance(topics_in, list) or len(topics_in) > MAX_TOPICS:
        raise CodeframeError(f"topics must be a list of at most {MAX_TOPICS} items.")
    special = dict(DEFAULT_SPECIAL)
    for k, v in (data.get("special_codes") or {}).items():
        if k not in SPECIAL_KEYS:
            raise CodeframeError(f"Unknown special code '{k}'.")
        special[k] = _code(v, f"special_codes.{k}")
    overrides = {}
    for k, v in (data.get("sentiment_overrides") or {}).items():
        if not isinstance(k, str) or not isinstance(v, (int, float)) or isinstance(v, bool) or abs(v) > 3:
            raise CodeframeError("sentiment_overrides must map words to numbers between -3 and 3.")
        overrides[k] = float(v)
    seen_topics, seen_codes = set(), {}
    topics = []
    for t in topics_in:
        if not isinstance(t, dict):
            raise CodeframeError("Each topic must be an object.")
        tid = t.get("id")
        if not isinstance(tid, str) or not NAME_RE.match(tid) or tid in seen_topics:
            raise CodeframeError(f"Topic id '{tid}' is missing, invalid or duplicated.")
        seen_topics.add(tid)
        codes = {}
        for pol, c in (t.get("codes") or {}).items():
            if pol not in ("pos", "neg", "neutral"):
                raise CodeframeError(f"Topic '{tid}': codes keys must be pos/neg/neutral.")
            cc = _code(c, f"topic {tid}.{pol}")
            prev = seen_codes.get(cc["code_id"])
            if prev and prev != cc["label"]:
                raise CodeframeError(f"code_id {cc['code_id']} is used for two different labels.")
            seen_codes[cc["code_id"]] = cc["label"]
            codes[pol] = cc
        if not codes:
            raise CodeframeError(f"Topic '{tid}' has no codes.")
        kw = _str_list(t.get("keywords"), "keywords", tid)
        pk = _str_list(t.get("pos_keywords"), "pos_keywords", tid)
        nk = _str_list(t.get("neg_keywords"), "neg_keywords", tid)
        if not (kw or pk or nk):
            raise CodeframeError(f"Topic '{tid}' has no keywords.")
        register_roots(kw + pk + nk)
        top_dict = {
            "id": tid,
            "net": str(t.get("net") or "")[:MAX_LABEL],
            "subnet": str(t.get("subnet") or tid)[:MAX_LABEL],
            "codes": codes,
            "keywords": kw, "pos_keywords": pk, "neg_keywords": nk,
            "exemplars": _str_list(t.get("exemplars"), "exemplars", tid) if t.get("exemplars") else [],
        }
        if t.get("dp_instruction"):
            top_dict["dp_instruction"] = str(t.get("dp_instruction"))[:MAX_LABEL]
        topics.append(top_dict)
    # compile phrases AFTER all roots are registered so stems are consistent
    for t in topics:
        t["kw_stems"] = sorted({stem_phrase(k) for k in t["keywords"] + t["pos_keywords"] + t["neg_keywords"]} - {()}, key=len, reverse=True)
        t["pos_stems"] = {stem_phrase(k) for k in t["pos_keywords"]} - {()}
        t["neg_stems"] = {stem_phrase(k) for k in t["neg_keywords"]} - {()}
    return {
        "id": cf_id,
        "name": str(data.get("name") or cf_id)[:MAX_LABEL],
        "domain": str(data.get("domain") or "general")[:40],
        "special": special,
        "overrides": overrides,
        "options": dict(data.get("options") or {}),
        "topics": topics,
    }


def load_codeframe(name: str, extra_dirs: Optional[list[Path]] = None) -> dict:
    """Load a codeframe by name from the bundled folder or $CLEARSIGHT_DATA/codeframes (never an arbitrary path)."""
    dirs = [d for d in [user_codeframe_dir(), BUNDLED_DIR] + list(extra_dirs or []) if d is not None]
    for folder in dirs:
        if not folder.exists():
            continue
        path = _safe_resolve(folder, name)
        if path is None:
            continue
        data = _read(path)
        includes = []
        for inc in data.get("includes") or []:
            inc_name = Path(str(inc)).stem
            inc_path = _safe_resolve(path.parent, inc_name) or _safe_resolve(BUNDLED_DIR, inc_name)
            if inc_path is None:
                raise CodeframeError(f"Included codeframe '{inc_name}' not found.")
            includes.append(_read(inc_path))
        return validate_codeframe(data, includes)
    raise CodeframeError(f"Codeframe '{name}' not found.")


def load_codeframe_from_dict(data: dict) -> dict:
    """Validate an uploaded codeframe (e.g. from the UI). Includes are not allowed here."""
    if data.get("includes"):
        raise CodeframeError("Uploaded codeframes cannot use 'includes'.")
    return validate_codeframe(data)


def list_codeframes() -> list[str]:
    names = set()
    for folder in [BUNDLED_DIR, user_codeframe_dir()]:
        if folder and folder.exists():
            for p in folder.iterdir():
                if p.suffix in (".json", ".yaml", ".yml") and NAME_RE.match(p.stem) and not p.stem.startswith("common_"):
                    names.add(p.stem)
    return sorted(names)


def load_lexicon(name: str = "sentiment_lexicon") -> dict:
    path = _safe_resolve(LEXICON_DIR, name)
    if path is None:
        raise CodeframeError(f"Lexicon '{name}' not found.")
    return _read(path)
