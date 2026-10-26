"""Persian/Arabic search normalisation for the document index (M45).

Normalisation is applied ONLY to the search index and to queries, the same
way on both sides.  Stored page text, file names and review decisions are
never rewritten: every match found in normalised text is mapped back to a
character span of the original text, so snippets and highlights show the
text exactly as stored.

Rules (``NORMALIZATION_VERSION`` changes whenever a rule changes, which
forces the in-memory index to be rebuilt from the stored originals):

==========================  =========================  =====================
Input                       Indexed as                 Why
==========================  =========================  =====================
Arabic yeh U+064A,          Persian yeh U+06CC         same letter, two
alef maksura U+0649                                    keyboard layouts
Arabic kaf U+0643           Persian keheh U+06A9       same letter, two
                                                       keyboard layouts
Arabic-Indic digits         ASCII digits               "۲۵۰۰" finds "2500"
U+0660-0669, Persian
digits U+06F0-06F9
ZWNJ U+200C (half-space)    removed (joins the parts)  "می‌شود" == "میشود"
harakat U+064B-065F,        removed                    vowel marks are rare
superscript alef U+0670                                and optional
tatweel U+0640              removed                    decorative stretching
Latin letter with           its base letter            FTS5 ``unicode61
diacritics (é, ï, ñ ...),   (e, i, n ...)              remove_diacritics 2``
combining marks U+0300-036F removed                    folds these too; the
                                                       highlighter must agree
==========================  =========================  =====================

Tokens are runs of letters and digits; ``_`` and every other character
separate tokens, exactly as the FTS5 ``unicode61`` tokenizer splits them, so
highlighting, the fallback scan and the index see the same words (v2; v1
treated ``_`` as part of a word and did not fold Latin diacritics, so FTS5
hits such as "cafe" -> "café" had no highlight and no line).

Comparison form (v3, M47) - what the fallback scan and the highlighter
compare, mirroring ``unicode61 remove_diacritics 2`` exactly as probed through
``fts5vocab``: Unicode *simple* case folding of each character (``ß``, ``ẞ``,
``ŉ``, ``ẚ`` keep their identity - FTS5 does not expand them - and ``ſ`` folds
to ``s``), THEN the diacritic fold above, so ``ẛ`` (long s with dot above)
folds to ``ẛ`` -> ``ṡ`` -> ``s`` as in FTS5. ``ǡ``/``Ǡ`` (U+01E1/U+01E0, a with
dot above and macron) are not folded: SQLite's diacritic table keeps them
(v2 folded them to ``a``, so FTS5 and the fallback disagreed). Known residual:
characters added to Unicode after SQLite's tokenizer tables (e.g. Cherokee
small letters, Latin Extended-D U+A796+, Georgian Mtavruli) are case-folded by
Python but not by FTS5; ``tests/test_search_closure_m47.py`` probes the real
tokenizer for every Latin and Arabic-script letter.

Deliberately NOT normalised (each would merge distinct words): alef forms
(آ/أ/إ/ا - "آب" water vs "اب"), teh marbuta/heh (ة/ه), hamza seats (ؤ/ئ),
and Latin case (FTS5 unicode61 is already case-insensitive).  A space typed
where the document has a half-space is handled at query time by an extra
alternative that joins the two words (``fts_match_expression``); repeated
spaces and line breaks never matter because the tokenizer splits on any
whitespace.
"""
from __future__ import annotations

import re
import unicodedata

NORMALIZATION_VERSION = 3

_CHAR_MAP = {
    "\u064a": "\u06cc",   # ARABIC LETTER YEH -> ARABIC LETTER FARSI YEH
    "\u0649": "\u06cc",   # ARABIC LETTER ALEF MAKSURA -> FARSI YEH
    "\u0643": "\u06a9",   # ARABIC LETTER KAF -> ARABIC LETTER KEHEH
}
_CHAR_MAP.update({chr(0x0660 + d): str(d) for d in range(10)})   # Arabic-Indic digits
_CHAR_MAP.update({chr(0x06F0 + d): str(d) for d in range(10)})   # Extended (Persian) digits
_REMOVED = frozenset(["\u200c", "\u0640", "\u0670", *(chr(c) for c in range(0x064B, 0x0660)),
                      *(chr(c) for c in range(0x0300, 0x0370))])   # Latin combining diacritics


def _latin_base(char: str):
    """Base letter of a precomposed LATIN letter with diacritics, else None.

    Only letters whose canonical decomposition is an ASCII letter plus
    combining marks are folded (é -> e, Ñ -> N).  Arabic-script letters such
    as alef with hamza (أ = ا + U+0654) are deliberately NOT folded: their
    base is not ASCII, and merging them would join distinct words.
    """
    decomposed = unicodedata.normalize("NFD", char)
    if len(decomposed) > 1 and decomposed[0].isascii() and decomposed[0].isalpha() \
            and all(unicodedata.combining(c) for c in decomposed[1:]):
        return decomposed[0]
    return None


# Letters whose decomposition is ASCII + combining marks but which SQLite's
# unicode61 diacritic table keeps as they are (probed via fts5vocab, M47).
_FTS5_KEEPS = frozenset(("\u01e0", "\u01e1"))
_CHAR_MAP.update({c: base for c in map(chr, range(0x00C0, 0x0250))
                  if c not in _FTS5_KEEPS and (base := _latin_base(c))})
_CHAR_MAP.update({c: base for c in map(chr, range(0x1E00, 0x1F00)) if (base := _latin_base(c))})

# Letters and digits only: "_" separates tokens, as in FTS5 unicode61.
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_QUOTED = re.compile(r'"([^"]*)"')
MAX_TERMS = 12


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Return ``(normalised, origin)``; ``origin[i]`` is the index in ``text``
    of normalised character ``i`` (every rule maps one char to at most one)."""
    out, origin = [], []
    for index, char in enumerate(text or ""):
        if char in _REMOVED:
            continue
        out.append(_CHAR_MAP.get(char, char))
        origin.append(index)
    return "".join(out), origin


def _simple_fold(char: str) -> str:
    """Unicode simple case folding of one character (one character out).

    ``str.casefold`` applies *full* folding (``ß`` -> ``ss``); FTS5 unicode61
    folds one character to one character. A full-only folding keeps the
    character unless its lowercase is a single character (``ẞ`` -> ``ß``).
    """
    folded = char.casefold()
    if len(folded) == 1:
        return folded
    lower = char.lower()
    return lower if len(lower) == 1 else char


def _fold(text: str) -> str:
    """Comparison form: simple case fold, then the diacritic fold.

    Same order as FTS5 unicode61 (case first, so ``ẛ`` -> ``ṡ`` -> ``s``).
    Length-preserving, so positions stay aligned with ``normalize_with_map``.
    """
    out = []
    for char in text:
        folded = _simple_fold(char)
        out.append(_CHAR_MAP.get(folded, folded))
    return "".join(out)


def normalize(text: str) -> str:
    """Index/comparison form of ``text`` (never stored, never displayed)."""
    return normalize_with_map(text)[0]


def tokens(text: str) -> list[str]:
    """Word tokens of the normalised text (letters, digits, underscore)."""
    return _TOKEN.findall(normalize(text))


def parse_query(query: str) -> list[list[str]]:
    """Split a query into groups; each group is matched as one phrase.

    * ``"..."`` - an explicit phrase;
    * a whitespace-separated chunk with internal punctuation (``SYN-DEV-01``,
      ``13-3/8``) - its parts must be adjacent, so identifiers stay precise;
    * anything else - one group per word.
    Groups keep their order; at most ``MAX_TERMS`` tokens in total.
    """
    groups, used = [], 0
    text = query or ""
    pieces = []
    last = 0
    for match in _QUOTED.finditer(text):
        pieces.extend(("chunk", chunk) for chunk in text[last:match.start()].split())
        pieces.append(("phrase", match.group(1)))
        last = match.end()
    pieces.extend(("chunk", chunk) for chunk in text[last:].split())
    for _kind, piece in pieces:
        parts = tokens(piece)
        if not parts or used >= MAX_TERMS:
            continue
        parts = parts[: MAX_TERMS - used]
        used += len(parts)
        groups.append(parts)
    return groups


def query_terms(query: str) -> list[str]:
    """Flat token list of a query (normalised), for highlighting/snippets."""
    return [t for group in parse_query(query) for t in group]


def _quote(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _group_expression(group: list[str]) -> str:
    if len(group) == 1:
        return _quote(group[0]) + "*"         # single word: prefix match ("cem" finds "cement")
    # Phrase of exact tokens: an identifier "SYN-DEV-01" must not match "SYN-DEV-012".
    return _quote(" ".join(group))


def query_alternatives(groups: list[list[str]]) -> list[list[list[str]]]:
    """The group lists a page may satisfy: the query itself, plus - for two
    adjacent single-word groups that are not ASCII (Persian/Arabic) - the
    same query with those two words joined (a space typed where the document
    has a half-space).  Shared by the FTS5 expression and the fallback scan
    so both find exactly the same pages."""
    if not groups:
        return []
    alternatives = [groups]
    for i in range(len(groups) - 1):
        left, right = groups[i], groups[i + 1]
        if len(left) == 1 and len(right) == 1 and not left[0].isascii() and not right[0].isascii():
            alternatives.append(groups[:i] + [[left[0] + right[0]]] + groups[i + 2:])
    return alternatives


def fts_match_expression(groups: list[list[str]]) -> str:
    """FTS5 MATCH expression for parsed query groups.

    Groups are ANDed.  For two adjacent single-word groups that are not
    ASCII (Persian/Arabic), an alternative with the words joined is ORed in,
    so "می شود" (typed with a space) also finds "می‌شود" stored with a
    half-space (indexed as "میشود").  English words and numbers never get a
    joined alternative (no "drill pipe" -> "drillpipe" guessing).
    """
    expressions = [" AND ".join(_group_expression(g) for g in alt) for alt in query_alternatives(groups)]
    if len(expressions) <= 1:
        return expressions[0] if expressions else ""
    return " OR ".join(f"({expr})" for expr in expressions)


def _group_in(page_tokens: list, group: list) -> bool:
    wanted = [_fold(t) for t in group]
    if len(wanted) == 1:                         # single word: prefix of a word, like ``"word"*``
        return any(token.startswith(wanted[0]) for token in page_tokens)
    n = len(wanted)                              # phrase: exact adjacent tokens, like ``"a b c"``
    return any(page_tokens[i:i + n] == wanted for i in range(len(page_tokens) - n + 1))


def text_matches(text: str, groups: list[list[str]]) -> bool:
    """True if ``text`` satisfies the parsed query with the same semantics as
    ``fts_match_expression`` (used when FTS5 is unavailable): every group
    present - single words as word prefixes, phrases/identifiers as exact
    adjacent tokens - in the query or one of its half-space alternatives."""
    if not text or not groups:
        return False
    page_tokens = [_fold(t) for t in _TOKEN.findall(normalize(text))]
    return any(all(_group_in(page_tokens, g) for g in alt) for alt in query_alternatives(groups))


def _as_groups(groups) -> list[list[str]]:
    """Normalise a span query to folded token groups.

    Accepts the ``parse_query`` result (a sequence of token sequences) or plain
    strings. A string is one group of its own tokens, so ``"SYN-DEV-01"``
    stays an adjacent-token phrase and ``"cem"`` a single word.
    """
    result = []
    for item in groups or ():
        parts = [item] if isinstance(item, str) else list(item)
        group = [_fold(token) for part in parts for token in _TOKEN.findall(normalize(str(part)))]
        if group:
            result.append(group)
    return result


def find_spans(text: str, groups) -> list[tuple[int, int]]:
    """Spans ``(start, end)`` in the ORIGINAL ``text`` of every match of the
    query ``groups``, with the same semantics as ``fts_match_expression`` and
    ``text_matches`` (M47 - the span contract is group-aware):

    * a single-word group matches the start of a word (``cem`` -> the ``cem``
      of ``cement``);
    * a multi-token group (an identifier such as ``SYN-DEV-01`` or a quoted
      phrase) matches only the exact adjacent tokens, and its span covers the
      whole phrase including the original separators. ``SYN`` inside
      ``SYNTHETIC`` and ``SYN-DEV-012`` are not matches;
    * the half-space alternatives of ``query_alternatives`` are included, so
      "می شود" covers "می‌شود" including its ZWNJ.

    Matching is case-insensitive and normalisation-aware; spans are sorted,
    and overlapping or touching spans are merged, so the result is the same
    for any order or duplication of the groups.
    """
    groups = _as_groups(groups)
    if not text or not groups:
        return []
    normalised, origin = normalize_with_map(text)
    words = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(_fold(normalised))]
    page_tokens = [word[0] for word in words]
    found = []
    for alternative in query_alternatives(groups):
        for group in alternative:
            n = len(group)
            if n == 1:
                prefix = group[0]
                for token, start, _end in words:
                    if token.startswith(prefix):
                        found.append((origin[start], origin[start + len(prefix) - 1] + 1))
            else:
                for i in range(len(words) - n + 1):
                    if page_tokens[i:i + n] == group:
                        found.append((origin[words[i][1]], origin[words[i + n - 1][2] - 1] + 1))
    merged = []
    for start, end in sorted(set(found)):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def utf16_offset(text: str, position: int) -> int:
    """UTF-16 code-unit offset of code-point ``position`` (Qt text positions)."""
    prefix = (text or "")[:max(position, 0)]
    return position + sum(1 for char in prefix if ord(char) > 0xFFFF)


def line_of(text: str, position: int) -> int:
    """1-based line number of ``position`` within ``text``."""
    return (text or "").count("\n", 0, max(position, 0)) + 1


def make_snippet(text: str, groups, width: int = 90) -> str:
    """Snippet of the ORIGINAL text around the first match, matches in [ ]
    (``groups`` as for :func:`find_spans`)."""
    text = text or ""
    spans = find_spans(text, groups)
    if not spans:
        return text[: width * 2].replace("\n", " ")
    start = max(spans[0][0] - width, 0)
    end = min(start + width * 2, len(text))
    pieces, cursor = [], start
    for s, e in spans:
        if s < start or e > end:
            continue
        pieces.append(text[cursor:s])
        pieces.append("[" + text[s:e] + "]")
        cursor = e
    pieces.append(text[cursor:end])
    body = "".join(pieces).replace("\n", " ")
    return ("… " if start else "") + body + (" …" if end < len(text) else "")
