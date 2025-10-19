"""Timeslot service: generation and availability queries.

MR-TS-2 scope:
- Generate concrete timeslots from a schedule spec
- List available (not full, not past) timeslots for a form

Notes
- Stores times in UTC; converts from a provided/local time zone when generating.
- Enforces a hard cap of 100 total timeslots per form.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ez_scheduler.models.signup_form import SignupForm
from ez_scheduler.models.timeslot import RegistrationTimeslot, Timeslot

logger = logging.getLogger(__name__)


# Hard cap per plan: do not allow more than this many timeslots per form
MAX_TIMESLOTS_PER_FORM = 100


class TimeslotSchedule(BaseModel):
    """Schedule specification for generating timeslots.

    - days_of_week: names like "monday", "wednesday"
    - window_start/window_end: HH:MM (24h) strings in the local time zone
    - slot_minutes: length of each slot in minutes
    - weeks_ahead: how many weeks from start_from_date to include
    - start_from_date: ISO date (YYYY-MM-DD), defaults to today in time_zone
    - capacity_per_slot: capacity for each generated slot (default 1)
    - time_zone: IANA tz name (e.g., "America/New_York"), defaults to form.time_zone or UTC
    """

    days_of_week: List[str]
    window_start: str
    window_end: str
    slot_minutes: int
    weeks_ahead: int = Field(ge=1, le=12)
    start_from_date: Optional[date] = None
    capacity_per_slot: Optional[int] = Field(default=None)
    time_zone: Optional[str] = None

    @field_validator("days_of_week")
    @classmethod
    def _normalize_days(cls, v: Iterable[str]) -> List[str]:
        normalized = [d.strip().lower() for d in v]
        valid = {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
        for d in normalized:
            if d not in valid:
                raise ValueError(f"Invalid day_of_week '{d}'")
        return normalized

    @field_validator("slot_minutes")
    @classmethod
    def _validate_slot_minutes(cls, v: int) -> int:
        allowed = {15, 30, 45, 60, 90, 120, 180, 240}
        if v not in allowed:
            raise ValueError(f"slot_minutes must be one of {sorted(allowed)}, got {v}")
        return v

    @field_validator("capacity_per_slot")
    @classmethod
    def _validate_capacity(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if v < 1:
            raise ValueError("capacity_per_slot must be >= 1 when provided")
        return v


def _weekday_name_to_int(name: str) -> int:
    mapping = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    return mapping[name]


def _parse_hh_mm(value: str) -> time:
    try:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError
        h, m = int(parts[0]), int(parts[1])
        return time(hour=h, minute=m)
    except Exception:
        raise ValueError(f"Invalid HH:MM time string: '{value}'")


@dataclass
class GenerationResult:
    created: List[Timeslot]
    skipped_existing: int


@dataclass
class BookingResult:
    success: bool
    booked_ids: List[uuid.UUID]
    unavailable_ids: List[uuid.UUID]
    already_booked_ids: List[uuid.UUID]


class TimeslotService:
    """Service for generating and querying timeslots."""

    def __init__(self, db_session: Session):
        self.db = db_session

    # Generation
    def generate_slots(
        self,
        form_id: uuid.UUID,
        schedule: TimeslotSchedule,
        now: Optional[datetime] = None,
    ) -> GenerationResult:
        """Generate concrete timeslots for a form based on a schedule spec.

        - Converts local window times to UTC based on schedule.time_zone or form.time_zone.
        - Skips past windows when start_from_date is today.
        - Enforces MAX_TIMESLOTS_PER_FORM including existing slots; ignores duplicates by unique key.
        """

        form = self.db.get(SignupForm, form_id)
        if not form:
            raise ValueError("Signup form not found")

        tz_name = schedule.time_zone or form.time_zone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as e:  # invalid tz
            raise ValueError(f"Invalid time zone: {tz_name}") from e

        local_today = (
            schedule.start_from_date
            if schedule.start_from_date is not None
            else datetime.now(tz).date()
        )
        weeks_ahead = schedule.weeks_ahead
        start_date = local_today
        end_date = start_date + timedelta(days=weeks_ahead * 7)

        window_start_t = _parse_hh_mm(schedule.window_start)
        window_end_t = _parse_hh_mm(schedule.window_end)
        if datetime.combine(date.today(), window_start_t) >= datetime.combine(
            date.today(), window_end_t
        ):
            raise ValueError("window_start must be before window_end")

        wanted_weekdays = {_weekday_name_to_int(d) for d in schedule.days_of_week}
        slot_delta = timedelta(minutes=schedule.slot_minutes)
        now_local = now.astimezone(tz) if now else datetime.now(tz)

        # Preload existing total count and enforce limit conservatively
        existing_count = self.db.exec(
            select(func.count(Timeslot.id)).where(Timeslot.form_id == form_id)
        ).one()

        # Validate capacity consistency: all slots in a form must have the same capacity
        if existing_count > 0:
            existing_capacity_sample = self.db.exec(
                select(Timeslot.capacity).where(Timeslot.form_id == form_id).limit(1)
            ).first()
            if existing_capacity_sample != schedule.capacity_per_slot:
                raise ValueError(
                    f"Cannot add slots with capacity {schedule.capacity_per_slot}. "
                    f"Existing slots have capacity {existing_capacity_sample}. "
                    f"All slots in a form must have the same capacity."
                )

        candidates: list[tuple[datetime, datetime]] = []
        d = start_date
        while d < end_date:
            if d.weekday() in wanted_weekdays:
                # Build local window
                window_start_local = datetime.combine(d, window_start_t, tzinfo=tz)
                window_end_local = datetime.combine(d, window_end_t, tzinfo=tz)

                # Skip past starting points on the start day
                start_cursor = window_start_local
                if d == now_local.date() and start_cursor < now_local:
                    # Advance start_cursor to the next slot start >= now_local
                    elapsed = now_local - start_cursor
                    slots_passed = int(
                        elapsed.total_seconds() // slot_delta.total_seconds()
                    )
                    start_cursor = start_cursor + slot_delta * slots_passed
                    # If still before now, move one more step
                    if start_cursor < now_local:
                        start_cursor += slot_delta

                # Walk slots
                while True:
                    slot_end_local = start_cursor + slot_delta
                    if slot_end_local > window_end_local:
                        break
                    # Convert to UTC for storage
                    start_utc = start_cursor.astimezone(timezone.utc)
                    end_utc = slot_end_local.astimezone(timezone.utc)
                    candidates.append((start_utc, end_utc))
                    start_cursor = slot_end_local

            d += timedelta(days=1)

        if not candidates:
            return GenerationResult(created=[], skipped_existing=0)

        # Filter out duplicates by checking existing within min..max range
        min_start = min(s for s, _ in candidates)
        max_end = max(e for _, e in candidates)
        existing_rows = self.db.exec(
            select(Timeslot).where(
                Timeslot.form_id == form_id,
                Timeslot.start_at >= min_start,
                Timeslot.end_at <= max_end,
            )
        ).all()
        existing_pairs = {(r.start_at, r.end_at) for r in existing_rows}

        new_pairs = [(s, e) for s, e in candidates if (s, e) not in existing_pairs]
        skipped_existing = len(candidates) - len(new_pairs)

        # Enforce total cap
        total_after = existing_count + len(new_pairs)
        if total_after > MAX_TIMESLOTS_PER_FORM:
            raise ValueError(
                f"This operation would create {total_after} timeslots for the form, exceeding the limit of {MAX_TIMESLOTS_PER_FORM}. Please reduce scope or split across multiple forms."
            )

        created: list[Timeslot] = []
        for start_utc, end_utc in new_pairs:
            created.append(
                Timeslot(
                    form_id=form_id,
                    start_at=start_utc,
                    end_at=end_utc,
                    capacity=schedule.capacity_per_slot,
                )
            )

        if created:
            self.db.add_all(created)
            self.db.commit()
            for row in created:
                self.db.refresh(row)

        return GenerationResult(created=created, skipped_existing=skipped_existing)

    # Queries
    def list_available(
        self,
        form_id: uuid.UUID,
        now: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Timeslot]:
        """Return available (future and not full) timeslots for a form.

        - Filters: start_at >= now (UTC), booked_count < capacity
        - Optional range filtering on UTC datetimes
        - Ordered by start_at ascending
        """

        # Validate form existence for consistency with generate_slots
        form = self.db.get(SignupForm, form_id)
        if not form:
            raise ValueError("Signup form not found")

        now_utc = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)

        stmt = select(Timeslot).where(
            Timeslot.form_id == form_id,
            Timeslot.start_at >= now_utc,
            (
                (Timeslot.capacity.is_(None))
                | (Timeslot.booked_count < Timeslot.capacity)
            ),
        )
        if from_date is not None:
            stmt = stmt.where(Timeslot.start_at >= from_date)
        if to_date is not None:
            stmt = stmt.where(Timeslot.start_at < to_date)

        stmt = stmt.order_by(Timeslot.start_at.asc()).limit(limit).offset(offset)
        return list(self.db.exec(stmt).all())

    def list_upcoming(
        self,
        form_id: uuid.UUID,
        now: Optional[datetime] = None,
        limit: int = 200,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Timeslot]:
        """Return all upcoming timeslots for a form (including full ones).

        - Filters: start_at >= now (UTC)
        - Does NOT filter by capacity; caller can compute "full" status
        - Ordered by start_at ascending
        """

        # Validate form existence for consistency
        form = self.db.get(SignupForm, form_id)
        if not form:
            raise ValueError("Signup form not found")

        now_utc = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)

        stmt = select(Timeslot).where(
            Timeslot.form_id == form_id,
            Timeslot.start_at >= now_utc,
        )
        if from_date is not None:
            stmt = stmt.where(Timeslot.start_at >= from_date)
        if to_date is not None:
            stmt = stmt.where(Timeslot.start_at < to_date)

        stmt = stmt.order_by(Timeslot.start_at.asc()).limit(limit).offset(offset)
        return list(self.db.exec(stmt).all())

    # --------------------------
    # MR-TS-9: Add/Remove Schedules
    # --------------------------

    class TimeslotRemoveSpec(BaseModel):
        """Spec for removing generated timeslots in a draft.

        - days_of_week: required weekdays to match
        - window_start/window_end: optional HH:MM local time window; when provided,
          a slot matches if its local START time is within [start, end)
        - weeks_ahead or end_date: one must be provided to bound the range
        - start_from_date: local start date; defaults to 'today' in time_zone
        - time_zone: IANA tz used for interpretation; defaults to form.time_zone or UTC
        """

        days_of_week: List[str]
        window_start: Optional[str] = None
        window_end: Optional[str] = None
        weeks_ahead: Optional[int] = Field(default=None, ge=1, le=12)
        end_date: Optional[date] = None
        start_from_date: Optional[date] = None
        time_zone: Optional[str] = None

        @field_validator("days_of_week")
        @classmethod
        def _normalize_days(cls, v: Iterable[str]) -> List[str]:
            normalized = [d.strip().lower() for d in v]
            valid = {
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            }
            for d in normalized:
                if d not in valid:
                    raise ValueError(f"Invalid day_of_week '{d}'")
            if not normalized:
                raise ValueError("days_of_week must not be empty")
            return normalized

        @model_validator(mode="after")
        def _validate_window_and_range(self):  # type: ignore[override]
            if (self.window_start and not self.window_end) or (
                self.window_end and not self.window_start
            ):
                raise ValueError(
                    "Both window_start and window_end must be provided together or omitted"
                )
            if self.window_start and self.window_end:
                # Validate format and ordering
                _ = _parse_hh_mm(self.window_start)
                end = _parse_hh_mm(self.window_end)
                start = _parse_hh_mm(self.window_start)
                if datetime.combine(date.today(), start) >= datetime.combine(
                    date.today(), end
                ):
                    raise ValueError("window_start must be before window_end")

            if (self.weeks_ahead is None) and (self.end_date is None):
                raise ValueError(
                    "Provide either weeks_ahead or end_date to bound the range"
                )
            return self

    @dataclass
    class AddResult:
        added_count: int
        skipped_existing: int

    @dataclass
    class RemoveResult:
        removed_count: int
        skipped_booked: int

    def add_schedule(
        self,
        form_id: uuid.UUID,
        add_spec: TimeslotSchedule,
        now: Optional[datetime] = None,
    ) -> "TimeslotService.AddResult":
        """Add timeslots per the schedule spec. Wrapper over generate_slots."""
        res = self.generate_slots(form_id, add_spec, now=now)
        return TimeslotService.AddResult(
            added_count=len(res.created), skipped_existing=res.skipped_existing
        )

    def remove_schedule(
        self,
        form_id: uuid.UUID,
        remove_spec: "TimeslotService.TimeslotRemoveSpec",
    ) -> "TimeslotService.RemoveResult":
        """Remove unbooked slots matching the spec. Returns counts only.

        Matching logic:
        - Limit search to [start_date, end_date) in local tz, converted to UTC bounds
        - Match weekday against remove_spec.days_of_week
        - If a window is provided, match when slot's local START time is within [start, end)
        - Delete only when booked_count == 0; otherwise count as skipped_booked
        """

        form = self.db.get(SignupForm, form_id)
        if not form:
            raise ValueError("Signup form not found")

        tz_name = remove_spec.time_zone or form.time_zone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Invalid time zone: {tz_name}") from e

        local_start_date = (
            remove_spec.start_from_date
            if remove_spec.start_from_date is not None
            else datetime.now(tz).date()
        )
        if remove_spec.end_date is not None:
            local_end_date = remove_spec.end_date + timedelta(days=1)  # exclusive
        else:
            weeks = remove_spec.weeks_ahead or 1
            local_end_date = local_start_date + timedelta(days=weeks * 7)

        # UTC bounds for query
        start_bound_local = datetime.combine(local_start_date, time(0, 0), tzinfo=tz)
        end_bound_local = datetime.combine(local_end_date, time(0, 0), tzinfo=tz)
        start_utc = start_bound_local.astimezone(timezone.utc)
        end_utc = end_bound_local.astimezone(timezone.utc)

        # Prefetch slots in the bounded window
        stmt = (
            select(Timeslot)
            .where(
                Timeslot.form_id == form_id,
                Timeslot.start_at >= start_utc,
                Timeslot.start_at < end_utc,
            )
            .order_by(Timeslot.start_at.asc())
        )
        rows: List[Timeslot] = list(self.db.exec(stmt).all())

        days_set = {_weekday_name_to_int(d) for d in remove_spec.days_of_week}
        start_t = (
            _parse_hh_mm(remove_spec.window_start) if remove_spec.window_start else None
        )
        end_t = _parse_hh_mm(remove_spec.window_end) if remove_spec.window_end else None

        removed = 0
        skipped = 0

        for slot in rows:
            local_start = slot.start_at.astimezone(tz)
            # Weekday match
            if local_start.weekday() not in days_set:
                continue
            # Optional time-window: start time within [start_t, end_t)
            if start_t and end_t:
                lt = local_start.timetz().replace(tzinfo=None)
                if not (start_t <= lt < end_t):
                    continue
            # Only delete unbooked
            if slot.booked_count and slot.booked_count > 0:
                skipped += 1
                continue
            try:
                self.db.delete(slot)
                removed += 1
            except Exception:
                # Be safe; if delete fails, treat as skipped
                skipped += 1

        if removed:
            self.db.commit()

        return TimeslotService.RemoveResult(
            removed_count=removed, skipped_booked=skipped
        )

    # Booking with concurrency safety
    def book_slots(
        self, registration_id: uuid.UUID, timeslot_ids: List[uuid.UUID]
    ) -> BookingResult:
        """Attempt to book all given timeslot IDs for a registration.

        - Locks target timeslot rows using SELECT ... FOR UPDATE
        - Verifies each slot has remaining capacity
        - Inserts rows into registration_timeslots; increments booked_count atomically
        - All-or-nothing: if any slot is unavailable or duplicate, rollback and report

        Returns BookingResult with success flag and details.
        """

        if not timeslot_ids:
            return BookingResult(True, [], [], [])

        distinct_ids = list(dict.fromkeys(timeslot_ids))

        # Start a transaction (nested to tolerate an existing outer transaction)
        try:
            with self.db.begin_nested():
                # Lock the rows to avoid race conditions
                stmt = (
                    select(Timeslot)
                    .where(Timeslot.id.in_(distinct_ids))
                    .with_for_update()
                )
                rows: List[Timeslot] = list(self.db.exec(stmt).all())

                found_ids = {row.id for row in rows}
                missing_ids = [tid for tid in distinct_ids if tid not in found_ids]

                # Check duplicates for idempotency
                existing_map = {
                    r.timeslot_id
                    for r in self.db.exec(
                        select(RegistrationTimeslot).where(
                            RegistrationTimeslot.registration_id == registration_id,
                            RegistrationTimeslot.timeslot_id.in_(distinct_ids),
                        )
                    ).all()
                }

                # Capacity check
                full_ids = [
                    row.id
                    for row in rows
                    if (row.capacity is not None and row.booked_count >= row.capacity)
                ]

                if missing_ids or full_ids or existing_map:
                    # Abort to ensure atomic rollback
                    raise RuntimeError("booking_conflict")

                # Proceed: increment counts and create join rows
                for row in rows:
                    row.booked_count += 1
                    self.db.add(
                        RegistrationTimeslot(
                            registration_id=registration_id, timeslot_id=row.id
                        )
                    )

            # Commit the outer transaction so changes persist when not managed by caller
            self.db.commit()
            return BookingResult(True, distinct_ids, [], [])

        except (IntegrityError, RuntimeError):
            # Unique constraint on (registration_id, timeslot_id) or other DB issue
            self.db.rollback()
            # Recompute which ones already existed for this registration
            existing = {
                r.timeslot_id
                for r in self.db.exec(
                    select(RegistrationTimeslot).where(
                        RegistrationTimeslot.registration_id == registration_id,
                        RegistrationTimeslot.timeslot_id.in_(distinct_ids),
                    )
                ).all()
            }
            # Determine which are missing and which are full
            rows_now: List[Timeslot] = list(
                self.db.exec(
                    select(Timeslot).where(Timeslot.id.in_(distinct_ids))
                ).all()
            )
            found_ids = {row.id for row in rows_now}
            missing_ids = [tid for tid in distinct_ids if tid not in found_ids]
            full_ids = [
                row.id
                for row in rows_now
                if (row.capacity is not None and row.booked_count >= row.capacity)
            ]
            unavailable = missing_ids or full_ids
            return BookingResult(False, [], unavailable, list(existing))
