# Timeslot Signup — Incremental Tasks (Phase 1)

Last updated: 2025-09-24

---

## MR-TS-1: Data Model & Migrations (no endpoint changes)

- Changes
  - Add SQLModel models: `Timeslot`, `RegistrationTimeslot` under `server/src/ez_scheduler/models/`.
  - Alembic migration in `server/alembic/versions/*_timeslots.py`:
    - Create `timeslots` table (see plan for columns and indexes).
    - Create `registration_timeslots` table with `UNIQUE(registration_id, timeslot_id)`.
    - Add `UNIQUE(form_id, start_at, end_at)` on `timeslots` to guarantee idempotent generation.
    - Useful indices: `idx_timeslots_form_start` on `(form_id, start_at)`; composite index `(form_id, status, start_at)` for status-driven queries; consider partial index `WHERE booked_count < capacity` to speed availability lookups.
    - Add optional column `signup_forms.time_zone` (IANA TZ string) to initialize timezone support early.
- Acceptance
  - Migrations apply cleanly; downgrade returns to prior schema.
  - Models import without circular deps; appears in metadata.
  - Unique constraints created successfully on new/empty tables (no data cleanup required).
  - Check constraints prevent negative counts and over-capacity values.

## MR-TS-2: Timeslot Service (generate + query) — internal only

- Changes
  - `server/src/ez_scheduler/services/timeslot_service.py`:
    - `generate_slots(form_id, schedule_spec)` returning created slots.
    - `list_available(form_id, now=None)` filtering past/full/cancelled.
  - Define Pydantic schedule spec types used by the service (add-only, internal).
  - Unit tests in `server/tests/` for generation (e.g., 5–9pm, 60m, Mon/Wed, 2 weeks → 16 slots).
- Acceptance
  - Deterministic generation across week boundaries; skips past windows on `start_from_date=today`.
  - No prompt changes in this MR.
  - Timezone conversion: generation stores UTC given a form time_zone; tests cover conversion basics.
  - Generation enforces a max of 100 total timeslots per form; attempts beyond the limit return a clear error to split across forms.

## MR-TS-3: Booking with Concurrency Safety — internal only

- Changes
  - `TimeslotService.book_slots(registration_id, timeslot_ids)`:
    - Transaction with row-level locking (`SELECT ... FOR UPDATE`) on chosen slots.
    - Check capacity; increment `booked_count`; insert into `registration_timeslots`.
    - Rollback all if any slot unavailable.
  - Tests: concurrent booking simulation or sequential checks validating no overbook.
  - No public routing changes; all code paths are unused until MR-TS-4 wires them.
- Acceptance
  - Overbooking avoided; precise error returned when slot is full.
  - No prompt changes in this MR.
  - Booking API returns unavailable ids for partial failures (to be surfaced as 409 by router later).

## MR-TS-4: Public Router + Template (POST /form/{slug} only)

- Changes
  - `server/src/ez_scheduler/routers/registration.py` (GET): fetch available slots and pass to template.
  - `server/src/ez_scheduler/templates/form.html`: add UI to select one or more slots (checkboxes), grouped by date.
  - `registration.py` (POST): read `timeslot_ids`, create `Registration`, call `book_slots`.
  - Success page displays the confirmed slots.
- Acceptance
  - Draft forms show disabled UI; published forms accept selections.
  - Selecting zero slots on a timeslot form returns validation error.
  - No prompt changes in this MR.
  - Security: verify all `timeslot_ids` belong to the form; reject otherwise (403/404).
  - Errors: 409 Conflict on booking race, include which ids failed; 422 for invalid payloads.

## MR-TS-5: LLM Integration for Creation (intent detection)

- Changes
  - Update `server/src/ez_scheduler/system_prompts.py` to extract `timeslot_schedule` when present (no new endpoints).
  - Extend `FormExtractionSchema` in `server/src/ez_scheduler/tools/create_form.py` with `timeslot_schedule` model.
  - In `_create_form(...)`: when schedule present, call `TimeslotService.generate_slots(...)` after form insert (same transaction).
- Acceptance
  - Prompt example (“1-1 soccer coaching … 5–9pm … Mon/Wed … 1h … next 2 weeks”) creates draft form with 16 slots.
  - Keep additions concise; preserve the strict JSON response contract.
  - Extract and apply `time_zone` if specified; default to form/user locale.

## MR-TS-6: Emails and Analytics

- Changes
  - `server/src/ez_scheduler/services/email_service.py`: include selected slots in registrant and creator emails.
  - `server/src/ez_scheduler/tools/get_form_analytics.py`: add metrics – total slots, booked slots, fill rate.
- Acceptance
  - Emails render slot lines like “Mon Oct 7, 5:00–6:00 PM”.
  - Analytics questions can summarize bookings for timeslot forms.
  - Times are formatted consistently in the form's time_zone.

## MR-TS-7 (Optional): UX Polish

- Changes
  - Show “Full”/“Cancelled” badges; hide past slots.
  - Add optional `max_slots_per_registration` on form.
- Acceptance
  - UI state reflects slot availability; server enforces max selection if set.

---

See the high-level design in `docs/timeslot_signup_plan.md`.
