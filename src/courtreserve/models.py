from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field


class EventStatus(StrEnum):
    ANY = "any"
    OPEN = "open"
    FULL = "full"
    WAITLIST = "waitlist"


class OrganizationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    org_id: int
    name: str
    timezone: str
    cost_type_id: str
    app_base_url: str = "https://app.courtreserve.com"
    events_base_url: str = "https://events.courtreserve.com"


class EventSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    org_id: int
    number: str
    uq_id: str
    event_id: int
    reservation_id: int
    name: str
    event_type: str
    start: datetime
    end: datetime
    capacity: int | None = None
    signed_members: int | None = None
    waitlist_count: int | None = None
    is_full: bool
    registration_open: bool
    allow_waitlist: bool
    in_past: bool
    slots_info: str | None = None
    note: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def spots_remaining(self) -> int | None:
        if self.capacity is None or self.signed_members is None:
            return None
        return max(0, self.capacity - self.signed_members)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def details_url(self) -> str:
        return (
            f"https://app.courtreserve.com/Online/Events/Details/"
            f"{self.org_id}/{self.number}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def availability(self) -> str:
        if self.is_full:
            return "Waitlist" if self.allow_waitlist else "Full"
        if self.slots_info:
            return self.slots_info
        if self.registration_open and not self.in_past:
            return "Open"
        return "Closed"


class EventDetails(BaseModel):
    model_config = ConfigDict(frozen=True)

    org_id: int
    number: str
    name: str
    event_type: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    description: str | None = None
    note: str | None = None
    availability: str | None = None
    details_url: str
    enhanced: bool = Field(description="Whether structured ApiDetails data was available")
