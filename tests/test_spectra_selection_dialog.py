# tests/test_spectra_selection_dialog.py
#
# Tests for the pure-logic helpers behind the "Select Spectra" dialog's
# text-search and common-root-name modes (src/views/dialogs/misc/
# spectra_selection_dialog.py). These are plain functions with no Qt
# widget construction, so they're tested directly without a QApplication
# — the dialog's widget wiring itself is not covered here, matching this
# repo's existing convention of testing the underlying logic rather than
# the GUI plumbing.

import pytest

from src.views.dialogs.misc.spectra_selection_dialog import (
    derive_root_name, group_by_root_name, compute_text_search_indices,
)


# ── derive_root_name ────────────────────────────────────────────────────

@pytest.mark.parametrize("label,expected", [
    ("Chlorella [r23_c24]", "Chlorella"),
    ("Chlorella [r00_c00]", "Chlorella"),
    ("Raman_DNA_conc_dep : sp001", "Raman_DNA_conc_dep"),
    ("Raman_DNA_conc_dep : 3", "Raman_DNA_conc_dep"),
    ("sample_012", "sample"),
    ("spectrum-3", "spectrum"),
    ("run#7", "run"),
    ("plain_unique_name", "plain_unique_name"),
    ("no_trailing_number_here", "no_trailing_number_here"),
])
def test_derive_root_name(label, expected):
    assert derive_root_name(label) == expected


def test_derive_root_name_strips_surrounding_whitespace():
    assert derive_root_name("  Chlorella [r1_c1]  ") == "Chlorella"


def test_derive_root_name_bracket_takes_priority_over_trailing_number():
    # A label could in principle match more than one rule; the bracketed
    # suffix should win since it's the most specific/unambiguous signal.
    assert derive_root_name("Chlorella_2 [r1_c1]") == "Chlorella_2"


# ── group_by_root_name ──────────────────────────────────────────────────

def test_group_by_root_name_basic_grouping():
    labels = [
        "Chlorella [r0_c0]",
        "Chlorella [r0_c1]",
        "Raman_DNA_conc_dep : sp001",
        "Raman_DNA_conc_dep : sp002",
        "Raman_DNA_conc_dep : sp003",
        "unrelated_spectrum",
    ]
    groups = group_by_root_name(labels)
    as_dict = dict(groups)
    assert set(as_dict.keys()) == {"Chlorella", "Raman_DNA_conc_dep", "unrelated_spectrum"}
    assert as_dict["Chlorella"] == [0, 1]
    assert as_dict["Raman_DNA_conc_dep"] == [2, 3, 4]
    assert as_dict["unrelated_spectrum"] == [5]


def test_group_by_root_name_sorted_largest_group_first():
    labels = ["A [r0_c0]", "B [r0_c0]", "B [r0_c1]", "B [r0_c2]"]
    groups = group_by_root_name(labels)
    # "B" has 3 members, "A" has 1 — B's group must come first
    assert groups[0][0] == "B"
    assert len(groups[0][1]) == 3
    assert groups[1][0] == "A"


def test_group_by_root_name_every_index_accounted_for_exactly_once():
    labels = [f"series_{i}" for i in range(10)] + ["Other [r1_c1]", "Other [r1_c2]"]
    groups = group_by_root_name(labels)
    seen = sorted(idx for _, indices in groups for idx in indices)
    assert seen == list(range(len(labels)))


def test_group_by_root_name_empty_input():
    assert group_by_root_name([]) == []


# ── compute_text_search_indices ─────────────────────────────────────────

def test_substring_search_case_insensitive_by_default():
    labels = ["Raman_map_01", "raman_map_02", "IR_map_01", "Chlorella"]
    assert compute_text_search_indices(labels, "raman") == [0, 1]


def test_substring_search_case_sensitive():
    labels = ["Raman_map_01", "raman_map_02", "IR_map_01"]
    assert compute_text_search_indices(labels, "raman", case_sensitive=True) == [1]


def test_substring_search_matches_anywhere_in_label():
    labels = ["Chlorella [r1_c1]", "Raman_DNA_conc_dep : sp001", "other"]
    assert compute_text_search_indices(labels, "Chlor") == [0]
    assert compute_text_search_indices(labels, "conc_dep") == [1]


def test_substring_search_empty_pattern_matches_nothing():
    labels = ["a", "b", "c"]
    assert compute_text_search_indices(labels, "") == []


def test_regex_search_basic():
    labels = ["sp001", "sp002", "sp010", "other"]
    # anchor to exactly three digits after "sp"
    assert compute_text_search_indices(labels, r"^sp\d{3}$", use_regex=True) == [0, 1, 2]


def test_regex_search_case_insensitive_by_default():
    labels = ["RAMAN_01", "raman_02", "ir_03"]
    assert compute_text_search_indices(labels, "raman", use_regex=True) == [0, 1]


def test_regex_search_case_sensitive():
    labels = ["RAMAN_01", "raman_02", "ir_03"]
    assert compute_text_search_indices(
        labels, "raman", use_regex=True, case_sensitive=True) == [1]


def test_regex_search_invalid_pattern_raises_re_error():
    import re
    with pytest.raises(re.error):
        compute_text_search_indices(["a", "b"], "(unclosed", use_regex=True)
