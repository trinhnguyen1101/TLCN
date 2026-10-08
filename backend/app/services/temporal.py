"""UTC query bounds. End dates include the entire day; end instants are inclusive."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

Resolution = Literal["3h", "daily", "monthly"]


class InvalidDashboardQuery(Exception):
    """Invalid user bounds, distinct from invalid source data."""


def utc_bound(value: str, end=False) -> datetime:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    instant = instant.astimezone(timezone.utc)
    if len(value) == 10 and end:
        instant += timedelta(days=1) - timedelta(microseconds=1)
    return instant


@dataclass(frozen=True)
class DashboardQuery:
    resolution: Resolution = "3h"
    start: str | None = None
    end: str | None = None

    def bounds(self, latest: str) -> tuple[datetime, datetime]:
        end = utc_bound(self.end, end=True) if self.end else utc_bound(latest)
        start = utc_bound(self.start) if self.start else (
            end.replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=6 if self.resolution == "3h" else 30)
        )
        if start > end:
            raise ValueError("start must be before or equal to end")
        limit = 31 if self.resolution == "3h" else 366
        if self.resolution != "monthly" and end - start >= timedelta(days=limit):
            raise ValueError(f"{self.resolution} queries support at most {limit} days")
        return start, end
