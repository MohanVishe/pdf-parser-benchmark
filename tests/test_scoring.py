import pytest

import scoring


# ---------------------------------------------------------------- normalize

def test_normalize_collapses_whitespace_and_line_breaks():
    assert scoring.normalize("  a\n\nb\t c  ") == "a b c"


def test_normalize_folds_arabic_presentation_forms():
    # "الكلب" written with presentation-form glyphs, as PDF text layers often are
    assert scoring.normalize("اﻟﻛﻠب") == "الكلب"


def test_normalize_folds_farsi_yeh_to_arabic_yeh():
    assert scoring.normalize("السریع") == "السريع"


def test_normalize_drops_variation_selectors_but_keeps_zwj():
    assert scoring.normalize("☺️") == "☺"
    assert "‍" in scoring.normalize("\U0001f642‍↕️")


def test_normalize_removes_dot_leaders_but_keeps_sentence_period():
    assert scoring.normalize("49 U.S.C. 14901(e) ........ Minimum penalty ...... 9,970") == "49 U.S.C. 14901(e) Minimum penalty 9,970"
    assert scoring.normalize("subsequent violations. ....... 3,988") == "subsequent violations. 3,988"
    assert scoring.normalize("evade regulation.......... 2,730") == "evade regulation 2,730"
    assert scoring.normalize("N.A.C.A. Report") == "N.A.C.A. Report"


# ------------------------------------------------------------- cer/wer/bow

def test_cer_and_wer_on_known_edits():
    assert scoring.cer("abcd", "abxd") == pytest.approx(0.25)
    assert scoring.wer("the quick brown fox", "the quick red fox") == pytest.approx(0.25)


def test_perfect_extraction_scores_zero_even_with_different_line_breaks():
    ref = "Name Occupation\nJohn Engineer"
    hyp = "Name   Occupation John\nEngineer\n"
    assert scoring.cer(ref, hyp) == 0.0
    assert scoring.wer(ref, hyp) == 0.0
    assert scoring.bow_f1(ref, hyp) == 1.0


def test_empty_output_is_total_loss_not_an_error():
    assert scoring.cer("some text", "") == 1.0
    assert scoring.wer("some text", "") == 1.0
    assert scoring.bow_f1("some text", "") == 0.0


def test_bow_f1_ignores_order_while_wer_does_not():
    ref = "alpha beta gamma delta"
    shuffled = "delta gamma beta alpha"
    assert scoring.bow_f1(ref, shuffled) == 1.0
    assert scoring.wer(ref, shuffled) == pytest.approx(1.0)


def test_bow_f1_penalises_extra_text():
    assert scoring.bow_f1("a b", "a b c d") == pytest.approx(2 * 0.5 * 1.0 / 1.5)


# ------------------------------------------------------------------- tables

ROWS = [["Name", "Occupation"], ["John", "Engineer"], ["Sarah", "Designer"]]


def test_table_rows_intact_when_each_row_is_one_line():
    hyp = "C) Table:\nName Occupation\nJohn Engineer\nSarah Designer\n"
    assert scoring.table_scores(hyp, ROWS) == {"rows_intact": 3, "rows_total": 3, "cells_found": 6, "cells_total": 6}


def test_one_cell_per_line_keeps_cells_but_loses_rows():
    hyp = "Name\nOccupation\nJohn\nEngineer\nSarah\nDesigner\n"
    assert scoring.table_scores(hyp, ROWS) == {"rows_intact": 0, "rows_total": 3, "cells_found": 6, "cells_total": 6}


def test_split_cell_text_is_not_found():
    hyp = "Name Occupation\nJohn Engineer\nSar ah Designer\n"
    scores = scoring.table_scores(hyp, ROWS)
    assert scores["rows_intact"] == 2
    assert scores["cells_found"] == 5


def test_cells_do_not_match_inside_other_numbers():
    rows = [["49 U.S.C. 14904(a)", "998"]]
    assert scoring.table_scores("49 U.S.C. 14904(a) 1,998", rows)["rows_intact"] == 0
    assert scoring.table_scores("49 U.S.C. 14904(a) ...... 998", rows)["rows_intact"] == 1


def test_wrapped_cell_uses_first_line_for_row_and_whole_text_for_cell():
    rows = [["49 U.S.C. 14903(a)", "Maximum penalty for each\nviolation.", "199,408"]]
    line_based = "49 U.S.C. 14903(a) ..... Maximum penalty for each 199,408\nviolation."
    scores = scoring.table_scores(line_based, rows)
    assert scores["rows_intact"] == 1
    assert scores["cells_found"] == 2  # the description is interleaved with the amount
    column_based = "49 U.S.C. 14903(a)\nMaximum penalty for each violation.\n199,408"
    assert scoring.table_scores(column_based, rows) == {"rows_intact": 0, "rows_total": 1, "cells_found": 3, "cells_total": 3}


# ---------------------------------------------------------------------- RTL

ARABIC = "الثعلب البني السريع يقفز فوق الكلب الكسول."


def test_rtl_logical_order():
    assert scoring.rtl_order(f"5. Arabic: {ARABIC}", ARABIC)["verdict"] == "logical order"


def test_rtl_one_word_per_line_is_still_logical_order():
    assert scoring.rtl_order("\n".join(ARABIC.split()), ARABIC)["verdict"] == "logical order"


def test_rtl_fully_reversed_visual_order():
    assert scoring.rtl_order(f"5. Arabic: {ARABIC[::-1]}", ARABIC)["verdict"] == "fully reversed"


def test_rtl_scattered_words_with_reversed_letters():
    words = [w[::-1] for w in ARABIC.rstrip(".").split()]
    scattered = f"{words[3]}\n\n{words[5]}\n5. Arabic:\n{words[0]} other text {words[1]} {words[6]}\n{words[2]}"
    result = scoring.rtl_order(scattered, ARABIC)
    assert result["verdict"] == "out of order, letters reversed"
    assert result["words_letters_reversed"] == pytest.approx(6 / 7, abs=1e-3)


def test_rtl_missing():
    assert scoring.rtl_order("nothing here", ARABIC)["verdict"] == "missing"


# -------------------------------------------------------------------- Indic

HINDI = "तेज भूरा लोमड़ी सुस्त कुत्ते पर कूदता है।"


def test_indic_intact_and_broken_conjuncts():
    assert scoring.indic_intact(f"3. Hindi: {HINDI}", HINDI) == {"intact": True, "words_exact": 1.0}
    broken = "3. Hindi: तेज भूरा लोमड़ी सु त कु े पर कूदता है।"
    result = scoring.indic_intact(broken, HINDI)
    assert result["intact"] is False
    assert result["words_exact"] == pytest.approx(6 / 8)


def test_line_stats_detects_one_word_per_line():
    assert scoring.line_stats("The\nquick\nbrown\n\nfox") == {"lines": 4, "words_per_line": 1.0}
    assert scoring.line_stats("") == {"lines": 0, "words_per_line": 0.0}
