"""
Journal entry-template schema contract.

A journal can carry plain text that pre-fills every new entry written in it
(e.g. a few fixed questions). These tests pin how that text is normalised and
how an update distinguishes "leave unchanged" from "remove".
"""

import pytest
from pydantic import ValidationError

from app.schemas.journal import (
    ENTRY_TEMPLATE_MAX_LENGTH,
    JournalCreate,
    JournalUpdate,
    normalize_entry_template,
)


def test_template_defaults_to_none():
    assert JournalCreate(title="Daily").entry_template is None


def test_template_keeps_layout_but_unifies_line_endings():
    created = JournalCreate(
        title="Daily",
        entry_template="Mood:\r\n\r\n  One win:\rTomorrow:   \n\n",
    )
    assert created.entry_template == "Mood:\n\n  One win:\nTomorrow:"


@pytest.mark.parametrize("blank", ["", "   ", "\n\n", " \r\n "])
def test_blank_template_means_no_template(blank):
    assert JournalCreate(title="Daily", entry_template=blank).entry_template is None
    assert normalize_entry_template(blank) is None


def test_template_length_is_capped():
    JournalCreate(title="Daily", entry_template="x" * ENTRY_TEMPLATE_MAX_LENGTH)
    with pytest.raises(ValidationError):
        JournalCreate(title="Daily", entry_template="x" * (ENTRY_TEMPLATE_MAX_LENGTH + 1))


def test_update_distinguishes_omitted_from_cleared():
    omitted = JournalUpdate(title="Renamed")
    assert "entry_template" not in omitted.model_fields_set

    cleared = JournalUpdate(entry_template=None)
    assert "entry_template" in cleared.model_fields_set
    assert cleared.entry_template is None

    blanked = JournalUpdate(entry_template="  ")
    assert "entry_template" in blanked.model_fields_set
    assert blanked.entry_template is None
