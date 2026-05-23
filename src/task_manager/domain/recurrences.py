from datetime import datetime

from domain.value_objects.tasks import RecurrenceEndMode


def recurrence_end_mode(
    *, repeat_until: datetime | None, max_occurrences: int | None
) -> RecurrenceEndMode:
    if repeat_until is not None and max_occurrences is not None:
        raise ValueError("repeat_until and max_occurrences cannot both be provided")

    if max_occurrences is not None:
        return RecurrenceEndMode.COUNT
    if repeat_until is not None:
        return RecurrenceEndMode.UNTIL_DATE
    return RecurrenceEndMode.NEVER
