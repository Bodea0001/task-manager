from datetime import datetime

from langchain.tools import tool


@tool(
    "get_current_datetime",
    description="Get the current date and time for interpreting relative task deadlines.",
)
async def get_current_datetime() -> str:
    """Get the current date and time.

    Use this before interpreting relative dates such as today, tomorrow, next week,
    or weekdays without an explicit date.
    """
    now = datetime.now().astimezone()
    utc_offset = now.strftime("%z")
    formatted_offset = f"{utc_offset[:3]}:{utc_offset[3:]}" if utc_offset else ""

    return (
        f"{now.date().isoformat()} {now.time().isoformat(timespec='seconds')} "
        f"{formatted_offset} {now.strftime('%A')}"
    )
