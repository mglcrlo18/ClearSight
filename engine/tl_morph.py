"""
Tagalog / Taglish / Bisaya text normaliser and dictionary-guided stemmer (coder v2).

Design notes
------------
* Pure Python, no dependencies, linear-time regexes only (CWE-1333: every
  pattern here is either anchored with bounded repetition or a plain word
  alternation, so there is no catastrophic backtracking).
* ``stem()`` is applied to BOTH the lexicon/codeframe keywords and the input,
  so a stem only has to be consistent, not linguistically perfect.
* When a candidate root is known (``KNOWN_ROOTS`` plus every keyword loaded
  from the codeframes and lexicons, see ``register_roots``) the shortest known
  candidate wins; otherwise a conservative heuristic strip is used.
* ``stem()`` is idempotent: ``stem(stem(w)) == stem(w)`` (property-tested).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# ---------------------------------------------------------------------------
# 1. Text-speak / orthographic normalisation (token level, applied before stemming)
# ---------------------------------------------------------------------------
TEXT_SPEAK: dict[str, str] = {
    'deciion': 'desisyon',
    'gulity': 'guilty',
    'corrpution': 'corruption',
    'matuluning': 'matulungin',
    'san juanico': 'san_juanico',
    'bed ridden': 'may_sakit',
    'hawaii': 'hawaii',
    "tangal": "tanggal", "tinangal": "tinanggal",
    # negators / pronouns
    "d": "hindi", "di": "hindi", "dii": "hindi", "hnd": "hindi", "hndi": "hindi", "hinde": "hindi",
    "nde": "hindi", "nd": "hindi", "indi": "hindi", "diko": "hindi ko", "dko": "hindi ko",
    "dipa": "hindi pa", "dpa": "hindi pa", "dna": "hindi na", "wla": "wala", "wlang": "walang",
    "wala ng": "wala na", "ayoko": "ayaw ko", "ayw": "ayaw", "wag": "huwag", "wg": "huwag",
    "aq": "ako", "aku": "ako", "q": "ko", "ikw": "ikaw", "sya": "siya", "cya": "siya", "xa": "siya",
    "sha": "siya", "nya": "niya", "nia": "niya", "nla": "nila", "nmin": "namin", "kmi": "kami",
    "kau": "kayo", "kyo": "kayo", "c": "si", "nyo": "ninyo",
    # particles / conjunctions
    "nmn": "naman", "nman": "naman", "nmam": "naman", "lng": "lang", "lang2": "lang", "nlng": "na lang",
    "tlga": "talaga", "tlaga": "talaga", "tlg": "talaga", "tala": "talaga",
    "kc": "kasi", "ksi": "kasi", "kse": "kasi", "kase": "kasi", "kz": "kasi", "dhil": "dahil", "dahl": "dahil",
    "pro": "pero", "per0": "pero", "kso": "kaso", "kya": "kaya", "kht": "kahit", "khit": "kahit",
    "pra": "para", "pr": "para", "sna": "sana", "dn": "din", "den": "din", "rn": "rin",
    "nga": "nga", "pde": "pwede", "pwde": "pwede", "pdeng": "pwedeng", "puede": "pwede",
    "bkt": "bakit", "bkit": "bakit", "dto": "dito", "d2": "dito", "dun": "doon", "dyan": "diyan",
    "bka": "baka", "brgy": "barangay", "gov": "gobyerno", "govt": "gobyerno", "gobyrno": "gobyerno",
    "msyado": "masyado", "mxado": "masyado", "msydo": "masyado", "sobrang": "sobra", "sobrah": "sobra",
    "grbe": "grabe", "grabeh": "grabe", "tas": "tapos", "tpos": "tapos", "nka": "naka", "mga": "mga",
    "mgnda": "maganda", "mganda": "maganda", "gnda": "ganda", "mbango": "mabango", "mbaho": "mabaho",
    "mhal": "mahal", "mhl": "mahal", "mra": "mura", "sulet": "sulit", "slit": "sulit",
    "ok": "okay", "oks": "okay", "okey": "okay", "k": "okay", "goods": "good", "gud": "good",
    "pls": "please", "tnx": "thanks", "ty": "thanks", "bcoz": "because", "bcs": "because", "coz": "because",
    "w/o": "without", "w/": "with", "dpt": "dapat", "dapt": "dapat", "kpg": "kapag", "pag": "kapag",
    "kng": "kung", "lgi": "lagi", "plagi": "palagi", "tlgang": "talagang",
    # Bisaya / Hiligaynon enclitics and function words
    "jud": "gyud", "gyod": "gyud", "jd": "gyud", "kaau": "kaayo", "kau2": "kaayo", "dli": "dili",
    "wa": "wala", "walay": "wala", "way": "wala", "indi": "hindi",
    # common brand / product typos kept from v1
    "calgate": "colgate", "planggana": "palanggana",
}
_MULTI_SPEAK = {k: v for k, v in TEXT_SPEAK.items() if " " in k}
_SINGLE_SPEAK = {k: v for k, v in TEXT_SPEAK.items() if " " not in k}

_ELONGATION = re.compile(r"([a-z])\1{2,}")
_TOKEN = re.compile(r"\[[a-z_]+\]|[a-zñ0-9]+(?:[-'][a-zñ0-9]+)*")


def normalize_text(text: str) -> str:
    """Lower-case, NFKC, strip accents (keep ñ), collapse elongations ('grabeee' -> 'grabe')."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    t = t.replace("ñ", "\x00")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = t.replace("\x00", "ñ").replace("’", "'").replace("`", "'")
    t = _ELONGATION.sub(r"\1", t)
    for k, v in _MULTI_SPEAK.items():
        t = re.sub(r"\b" + re.escape(k) + r"\b", v, t)
    return t


def tokenize(text: str) -> list[str]:
    """Normalised tokens with text-speak expanded (an expansion may yield 2 tokens)."""
    out: list[str] = []
    for tok in _TOKEN.findall(normalize_text(text)):
        exp = _SINGLE_SPEAK.get(tok)
        if exp:
            out.extend(exp.split())
        else:
            out.append(tok)
    return out


# ---------------------------------------------------------------------------
# 2. Stemmer
# ---------------------------------------------------------------------------
# A small seed list of frequent roots. Codeframe / lexicon keywords are added at load time.
KNOWN_ROOTS: set[str] = set("""
ganda bango baho linis tulong presyo mahal mura sulit tipid bili gamit tagal lamig init puti tanggal
bilis bagal sira ayos husay galing bait tapat tiwala trabaho gawa kain inom ligo hugas alis gaan bigat
kati sakit galing lakas hina dami konti kulang sobra hirap dali sarap pait alat tamis asim kinis lambot
tigas lagkit bula laman bigay tulog gising sunod daan baha basura trapik ilaw tubig kuryente gamot
lusog ngipin hininga bibig balat buhok anit pawis amoy kulay hugis tingin pakita dating sabi alam
isip intindi unawa tupad pangako plano proyekto pondo nakaw kurakot sugal droga krimen gulo ayuda
kita sahod bayad singil buwis taas baba lapit layo bago luma lumang tibay tatag tapang hinahon
kumbaba yabang yaman hirap mahirap trato lingkod serbisyo iboto boto panalo talo laban suporta
puno bayan itim bigay dala kuha buti tama mali
""".split())


ROOTS_VERSION = [0]


def register_roots(words) -> None:
    """Add known roots (e.g. every keyword from the loaded codeframes and lexicons).

    Bumps ROOTS_VERSION when the set changes so compiled coders can recompile their phrases.
    """
    added = False
    for w in words:
        for t in tokenize(str(w)):
            if t.isalpha() and len(t) >= 3 and t not in KNOWN_ROOTS:
                KNOWN_ROOTS.add(t)
                added = True
    if added:
        _stem_cached.cache_clear()
        ROOTS_VERSION[0] += 1


_VOWELS = set("aeiou")
# longest-first prefix list (verbal, adjectival, superlative, causative, abilitative)
_PREFIXES = (
    "pinakama", "pinaka", "nakakapagpa", "makakapagpa", "nakapagpa", "pagpapa", "nakakapag", "makakapag", "nakapag", "makapag", "ipinag", "ipinapa",
    "nagpapa", "magpapa", "pinagka", "pagkaka", "nakaka", "makaka", "nagka", "magka", "pagka",
    "pagpa", "nagpa", "magpa", "ipag", "ipa", "naka", "maka", "napa", "mapa", "pina", "pang",
    "mang", "nang", "mam", "nam", "man", "nan", "pam", "pan", "nag", "mag", "pag", "ika", "ka", "ma", "na", "pa", "i",
)
_SUFFIXES = ("hanan", "nanan", "han", "hin", "nan", "nin", "an", "in")


def _strip_redup(w: str) -> str:
    # full reduplication: "sira-sira" / "sirasira" / "araw-araw"
    if "-" in w:
        parts = [p for p in w.split("-") if p]
        if len(parts) == 2 and (parts[0] == parts[1] or parts[1].startswith(parts[0][:3])):
            return parts[1]
        return "".join(parts)
    n = len(w)
    if n >= 8 and n % 2 == 0 and w[: n // 2] == w[n // 2:]:
        return w[: n // 2]
    # partial CV / CVC reduplication at the start: "tatrabaho" -> "trabaho", "kakain" -> "kain"
    if n >= 5 and w[0] not in _VOWELS and w[1] in _VOWELS:
        cv = w[:2]
        if w[2:4] == cv or (w[2] == w[0] and len(w) > 4 and w[3] not in _VOWELS and w[4:5] == w[1:2]):
            return w[2:]
    if n >= 4 and w[0] in _VOWELS and w[1] == w[0]:
        return w[1:]
    return w


def _strip_infix(w: str) -> str:
    # -um- / -in- after the first consonant: k-um-ain, s-in-abi, b-in-ili; "ni-" for l/y roots: nilinis
    if len(w) >= 5 and w[0] not in _VOWELS and w[1:3] in ("um", "in") and w[3] in _VOWELS | set("bcdfghklmnprstwy"):
        return w[0] + w[3:]
    if len(w) >= 6 and w.startswith("ni") and w[2] in "ly":
        return w[2:]
    if len(w) >= 5 and w.startswith(("um", "in")) and w[2] in _VOWELS:
        return w[2:]
    return w


def _linker(w: str) -> str:
    # ligature -ng after a vowel-final root ("magandang" -> "maganda"); "-g" after n handled by "ng" check
    if len(w) >= 5 and w.endswith("ng") and w[-3] in _VOWELS:
        return w[:-2]
    return w


_CLUSTERS = ("bl", "br", "dr", "dy", "gr", "gl", "kl", "kr", "kw", "ky", "pl", "pr", "py", "sw", "sy", "tr", "ts", "ty", "sh", "ch", "st", "sp", "sk", "sm", "sn", "fl", "fr", "ng")


def _valid_onset(x: str) -> bool:
    """Reject candidates that start with an impossible consonant cluster (e.g. 'lsada' from 'kalsada')."""
    if len(x) < 2 or x[0] in _VOWELS or x[1] in _VOWELS:
        return True
    return x[:2] in _CLUSTERS


def _ou(x: str) -> str:
    # o -> u alternation before a suffix: tulong -> tulungan, inom -> inumin
    i = x.rfind("u")
    if i >= 0 and i >= len(x) - 3:
        return x[:i] + "o" + x[i + 1:]
    return x


def _candidates(w: str):
    seen = []

    def add(x):
        if x and len(x) >= 3 and x not in seen and _valid_onset(x):
            seen.append(x)

    add(w)
    for base in (w, _linker(w)):
        add(base)
        for p in _PREFIXES:
            if base.startswith(p) and len(base) - len(p) >= 3:
                rest = base[len(p):].lstrip("-")
                add(rest)
                # nasal assimilation: pang-/mang-/nang- + p/b -> m, + t/d/s -> n, + k -> ng
                if p in ("mam", "nam", "pam") or (p in ("ma", "na", "pa") and rest.startswith("m")):
                    r = rest if rest.startswith("m") else "m" + rest
                    r = _strip_redup(r)
                    add("p" + r[1:]); add("b" + r[1:])
                if p in ("man", "nan", "pan") and rest.startswith("n"):
                    r = _strip_redup(rest)
                    add("t" + r[1:]); add("d" + r[1:]); add("s" + r[1:])
                if p in ("mang", "nang", "pang"):
                    r = _strip_redup(rest)
                    add("k" + r); add(r)
                    if r.startswith("i") and len(r) > 2:
                        add(_strip_redup(r[2:]) if r[:2] == "in" else r)
                r2 = _strip_redup(rest)
                add(r2)
                add(_strip_infix(r2))
        for x in list(seen):
            add(_strip_redup(x))
            add(_strip_infix(x))
        for x in list(seen):
            for s in _SUFFIXES:
                if x.endswith(s) and len(x) - len(s) >= 3:
                    add(x[: -len(s)])
                    add(_ou(x[: -len(s)]))
                    r = x[: -len(s)]
                    if len(r) >= 3 and r[-1] not in _VOWELS and r[-2] not in _VOWELS:
                        add(r[:-1] + "a" + r[-1])  # bigyan -> bigay, dalhin -> dala(h)
                        add(r[:-1] + "a")
                    add(_ou(_linker(x[: -len(s)] + "ng")) if x[: -len(s)].endswith("ng") else None)
    return seen


# Function words and frequent words that must never be stemmed (e.g. "kasama" must not become "sama").
NO_STEM: set[str] = set("""
kasama kasi kaya kahit kapag kaso para pero mga sila siya kami tayo kayo nila niya namin natin ninyo pala palagi lagi
talaga naman ngayon noon dahil dito doon diyan ito iyan iyon yung ang ng sa na at ay si ni kay may mayroon meron wala
walang hindi ayaw huwag gusto sana lang din rin pa po opo ba nga daw raw kung tapos saka habang bago pagkatapos masyado
sobra grabe marami maraming pagkain kalaban kailangan kapwa katawan kababayan kalsada kapatid kaibigan kapitbahay
kaalyado karapatan kalidad kahirapan kabataan kababaihan kalinisan kaunti konti mahal mahalaga mabuhay salamat
pamilya magulang matanda bata babae lalaki tao naman nalang nlang talagang ganito ganyan ganoon paano bakit ano sino
saan kailan alin ilan iba ibang lahat bawat isa dalawa tatlo mas pinaka unang huling mahihirap mayayaman makabayan
""".split())


SPECIAL_STEMS: dict[str, str] = {
    "naniniwala": "tiwala",
    "maniwala": "tiwala",
    "paniniwala": "tiwala",
    "pagmamahal": "love",
    "nagmamahal": "love",
    "nagmamahalan": "love",
    "mapagmahal": "love",
    "makatao": "makatao",
    "makabayan": "makabayan",
    "makatao": "makatao",
    "makabayan": "makabayan",
}

@lru_cache(maxsize=65536)
def _stem_cached(w: str) -> str:
    if w in SPECIAL_STEMS:
        return SPECIAL_STEMS[w]
    if len(w) <= 3 or not w.replace("-", "").isalpha() or w in NO_STEM:
        return w
    cands = _candidates(w)
    known = [c for c in cands if c in KNOWN_ROOTS]
    if known:
        return min(known, key=len)
    # heuristic fallback: strip one prefix + redup + infix + one suffix, keep >= 4 chars
    x = _linker(w)
    for p in _PREFIXES:
        if x.startswith(p) and len(x) - len(p) >= 4 and _valid_onset(x[len(p):].lstrip("-")):
            x = x[len(p):].lstrip("-")
            break
    y = _strip_infix(_strip_redup(x))
    x = y if _valid_onset(y) else x
    for s in _SUFFIXES:
        if x.endswith(s) and len(x) - len(s) >= 4:
            x = x[: -len(s)]
            break
    return x if len(x) >= 3 else w


def stem(word: str) -> str:
    """Stem one token. Idempotent: stem(stem(w)) == stem(w)."""
    w = str(word).lower()
    s = _stem_cached(w)
    # enforce idempotence for heuristic outputs (a second pass may strip again)
    for _ in range(3):
        s2 = _stem_cached(s)
        if s2 == s:
            break
        s = s2
    return s


def stem_tokens(tokens) -> list[str]:
    return [stem(t) for t in tokens]


def stem_phrase(phrase: str) -> tuple[str, ...]:
    """Normalise + stem a lexicon phrase exactly as input text is processed."""
    return tuple(stem(t) for t in tokenize(phrase))
