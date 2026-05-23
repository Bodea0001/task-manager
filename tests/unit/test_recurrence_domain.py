from datetime import datetime

import pytest

from domain.recurrences import recurrence_end_mode
from domain.value_objects.tasks import RecurrenceEndMode


def test_recurrence_end_mode_defaults_to_never() -> None:
    assert recurrence_end_mode(repeat_until=None, max_occurrences=None) == RecurrenceEndMode.NEVER


def test_recurrence_end_mode_uses_until_date() -> None:
    assert (
        recurrence_end_mode(
            repeat_until=datetime(2099, 1, 1, 0, 0),
            max_occurrences=None,
        )
        == RecurrenceEndMode.UNTIL_DATE
    )


def test_recurrence_end_mode_uses_count() -> None:
    assert (
        recurrence_end_mode(
            repeat_until=None,
            max_occurrences=10,
        )
        == RecurrenceEndMode.COUNT
    )


def test_recurrence_end_mode_rejects_multiple_end_conditions() -> None:
    with pytest.raises(ValueError):
        recurrence_end_mode(
            repeat_until=datetime(2099, 1, 1, 0, 0),
            max_occurrences=10,
        )
