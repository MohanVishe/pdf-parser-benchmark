"""Scoring: compare one parser's extraction with a hand-verified reference.

Every function here is pure (text in, numbers out) so it can be tested without
PDFs. The metrics, and what each one can and cannot tell you:

cer / wer     Character / word error rate (jiwer, Levenshtein) after normalize().
              Order-sensitive: a block emitted in the wrong place costs roughly
              twice its length. Can exceed 1.0 when the output has lots of
              extra text.
bow_f1        Bag-of-words F1, order-free. Separates "the text is missing or
              wrong" (low bow_f1) from "the text is there but out of order"
              (high bow_f1, high wer).
rows_intact   Table rows whose cells all appear, in order, on one output line.
cells_found   Table cells whose full text appears anywhere in the output.
rtl           Whether each right-to-left sentence comes out in logical order,
              fully reversed (visual order), or out of order.
indic         Whether each Devanagari / Bengali sentence survives intact, and
              what share of its words do.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

import jiwer

# Invisible presentation hints that carry no text: variation selectors and the
# soft hyphen. Zero-width joiners are kept: they are part of emoji sequences.
_DROP = dict.fromkeys(map(ord, "︎️­"))
# Arabic-script letter variants that share one glyph in joined positions. PDF
# fonts often map the initial/medial Arabic yeh glyph to Farsi yeh (and kaf to
# keheh), so a visually perfect extraction would otherwise score as wrong.
# Folded on both sides, so it never rewards a real error.
_FOLD = {ord("ی"): "ي", ord("ک"): "ك"}
# Dot leaders in tables of contents and tables, removed so their arbitrary
# length is not scored: a run of three or more dots (single spaces allowed)
# that starts after whitespace, or a run of four or more glued to a word. A
# sentence period followed by a space and then a leader is kept.
_LEADERS = re.compile(r"(?<!\S)\.(?: ?\.){2,}|(?<=\S)\.{4,}")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC (folds Arabic presentation forms and ligatures to base letters),
    fold yeh/kaf variants, drop invisible selectors, remove dot leaders,
    collapse all whitespace."""
    text = unicodedata.normalize("NFKC", text).translate(_DROP).translate(_FOLD)
    text = _LEADERS.sub(" ", text)
    return _WS.sub(" ", text).strip()


def _strip_punct(token: str) -> str:
    return "".join(ch for ch in token if not unicodedata.category(ch).startswith("P"))


def tokens(text: str) -> list[str]:
    """Whitespace tokens of the normalized text, punctuation removed."""
    out = []
    for tok in normalize(text).split(" "):
        tok = _strip_punct(tok)
        if tok:
            out.append(tok)
    return out


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not hyp:
        return 1.0  # every reference character was deleted
    return float(jiwer.cer(ref, hyp))


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not hyp:
        return 1.0  # jiwer rejects an empty hypothesis; every word was deleted
    return float(jiwer.wer(ref, hyp))


def bow_f1(reference: str, hypothesis: str) -> float:
    ref, hyp = Counter(normalize(reference).split()), Counter(normalize(hypothesis).split())
    overlap = sum((ref & hyp).values())
    if not overlap:
        return 0.0
    precision = overlap / sum(hyp.values())
    recall = overlap / sum(ref.values())
    return 2 * precision * recall / (precision + recall)


def _cell_pattern(cell: str) -> re.Pattern:
    # A cell must not be glued to neighbouring letters, digits or thousands
    # separators, so "998" does not match inside "1,998".
    return re.compile(r"(?<![\w,.])" + re.escape(cell) + r"(?![\w,])")


def _cells_in_order(line: str, cells: list[str]) -> bool:
    position = 0
    for cell in cells:
        match = _cell_pattern(cell).search(line, position)
        if not match:
            return False
        position = match.end()
    return True


def table_scores(hypothesis: str, rows: list[list[str]]) -> dict:
    """rows: each row is a list of cells. A cell that wraps onto several lines
    in the PDF is written with "\\n" at the wrap; the row check uses only the
    part before the first "\\n" (the text on the row's own line), the cell check
    uses the whole cell."""
    lines = [normalize(line) for line in hypothesis.splitlines()]
    whole = normalize(hypothesis)
    intact = sum(
        any(_cells_in_order(line, [normalize(c.split("\n")[0]) for c in row]) for line in lines)
        for row in rows
    )
    cells = [normalize(c) for row in rows for c in row]
    found = sum(bool(_cell_pattern(c).search(whole)) for c in cells)
    return {
        "rows_intact": intact, "rows_total": len(rows),
        "cells_found": found, "cells_total": len(cells),
    }


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def rtl_order(hypothesis: str, sentence: str) -> dict:
    """Classify how a right-to-left sentence came out."""
    want = tokens(sentence)
    have = tokens(hypothesis)
    backwards = [t[::-1] for t in reversed(want)]
    present = set(have)
    forward_share = sum(t in present for t in want) / len(want)
    reversed_share = sum(t in present for t in backwards) / len(want)
    if _contains_run(have, want):
        verdict = "logical order"
    elif _contains_run(have, backwards):
        verdict = "fully reversed"
    elif reversed_share >= 0.5:
        verdict = "out of order, letters reversed"
    elif forward_share >= 0.5:
        verdict = "out of order"
    else:
        verdict = "missing"
    return {
        "verdict": verdict,
        "words_forward": round(forward_share, 3),
        "words_letters_reversed": round(reversed_share, 3),
    }


def indic_intact(hypothesis: str, sentence: str) -> dict:
    """Whether a Devanagari/Bengali sentence survives, and the share of its
    words that come out exactly (broken conjuncts or reordered vowel signs
    make a word fail)."""
    want = tokens(sentence)
    present = set(tokens(hypothesis))
    return {
        "intact": normalize(sentence) in normalize(hypothesis),
        "words_exact": round(sum(t in present for t in want) / len(want), 3),
    }


def line_stats(hypothesis: str) -> dict:
    lines = [line for line in hypothesis.splitlines() if line.strip()]
    words = len(normalize(hypothesis).split()) if lines else 0
    return {
        "lines": len(lines),
        "words_per_line": round(words / len(lines), 2) if lines else 0.0,
    }
