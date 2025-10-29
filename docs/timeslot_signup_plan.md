# Timeslot-Based Signup Forms — Plan

Last updated: 2025-09-24

---

## Overview

Enable creators to generate a signup form that contains concrete bookable timeslots (e.g., “1-1 soccer coaching between 5–9pm on Mondays and Wednesdays with 1 hour slots for the next 2 weeks”). The system generates the slots (4 per day × 2 days × 2 weeks = 16 total in this example), publishes them with the form, and allows registrants to select one or more slots across days.

Scope is additive: existing single-date forms continue to work. Timeslot forms become a new capability that reuses the current form, registration, and LLM-driven creation flows.

---

## Entry Points & Intent Detection

- Creator entry points remain unchanged:
  - REST: `POST /gpt/create-or-update-form`, `POST /gpt/archive-form`.
  - MCP tools: reuse existing tools; no new tool endpoints required for timeslots.
- Intent detection happens inside the existing LLM-driven handlers (`create_form_handler`, `update_form_handler`). The LLM extracts either:
  - Single-date event fields (title, date/time, etc.), or
  - A `timeslot_schedule`/`timeslot_mutations` spec for timeslot forms.
- Registration remains: `POST /form/{url_slug}`. The public router adapts to the form type:
  - Single-date forms: unchanged behavior.
  - Timeslot forms: require `timeslot_ids` on submission; template renders available slots.

---

## Prompt Changes & Timing

- No prompt changes in MR-TS-1..4 (schema, services, UI wiring). Quality remains unchanged.
- MR-TS-5: Extend form creation extraction to support `timeslot_schedule` (intent-based). Keep additions concise and preserve the "return ONLY valid JSON" contract.
- MR-TS-10: Extend update flow with `timeslot_mutations` (add/remove) guidance for draft edits. Keep examples minimal (1–2).
- Optional (Phase 3): Modularize the prompt (base + timeslot addenda) and trim redundant guidance to reduce tokens and latency.

---

## Goals

- Convert natural-language scheduling requests into a schedule spec and concrete timeslots.
- Store timeslots with capacity control (default 1 per slot) and safe booking.
- Render available timeslots on the public form; allow selecting one or more.
- Persist selections and show them in confirmation and emails.
- Keep creator UX consistent (preview/publish lifecycle, analytics).

---

## Data Model

New/updated tables (SQLModel + Alembic):

- timeslots
  - id (UUID, PK)
  - form_id (UUID, FK → signup_forms.id, indexed, cascade delete)
  - start_at (TIMESTAMP WITH TIME ZONE, stored in UTC)
  - end_at (TIMESTAMP WITH TIME ZONE, stored in UTC)
  - capacity (INT, default 1, CHECK capacity >= 1)
  - booked_count (INT, default 0, CHECK booked_count >= 0 AND booked_count <= capacity)
  - status (optional ENUM: available, full, cancelled). Availability is primarily computed as booked_count < capacity; keep status only if needed for cancellations.
  - created_at, updated_at (UTC)

- registration_timeslots
  - id (UUID, PK)
  - registration_id (UUID, FK → registrations.id, indexed, cascade delete)
  - timeslot_id (UUID, FK → timeslots.id, indexed, cascade delete)
  - UNIQUE(registration_id, timeslot_id)

Notes
- We keep existing `signup_forms.event_date/start_time/end_time` for non-timeslot forms. For timeslot forms these are not used for booking display.
- Form type is inferred: a form is considered a timeslot form if it has one or more timeslots; otherwise it's a single-date form.
- Add `signup_forms.time_zone` (IANA TZ string, e.g., "America/New_York") to anchor interpretation of schedule specs; store slots in UTC.
- Consider adding optional `form_time_zone` (IANA string). For v1 we assume server/local TZ in generation and store UTC.

---

## LLM Extraction Schema (Additions)

Extend the form creation schema to support schedules:

- timeslot_schedule (creation intent)
  - days_of_week: ["monday", "wednesday", ...]
  - window_start: "17:00" (ISO 8601 time, HH:MM)
  - window_end: "21:00" (ISO 8601 time, HH:MM)
  - slot_minutes: 60
  - weeks_ahead: 2  (or explicit end_date)
  - start_from_date: optional ISO date (defaults to today)
  - capacity_per_slot: optional int (default 1)
  - time_zone: optional IANA TZ name; default to form.time_zone if omitted

Generation algorithm
- Build date range [start_from_date, start_from_date + weeks_ahead*7).
- For each date whose weekday ∈ days_of_week, step from window_start to window_end by slot_minutes creating [start_at, end_at) slots.
- Skip past times (if start_from_date is today and window already passed).
- Convert local times (time_zone) to UTC for storage; display converted back to local for UI and emails.

---

## APIs and Services

- TimeslotService
  - generate_slots(form_id, schedule_spec) → List[Timeslot]
  - list_available(form_id, now=utcnow, limit=100, offset=0, from_date=None, to_date=None)
  - book_slots(registration_id, [timeslot_ids]) with transaction/locking:
    - SELECT ... FOR UPDATE on rows; verify not full/cancelled; increment booked_count atomically; insert into registration_timeslots.

- Registration flow (public POST /form/{slug})
  - Accept `timeslot_ids` as a multi-value or JSON array.
  - Create Registration row, then attempt `book_slots`.
  - Validate that all provided timeslot_ids belong to the target form. If any mismatch, respond 403/404.
  - If any slot cannot be booked, rollback with clear error; respond 409 with the specific unavailable slot ids; otherwise commit all.
  - Hard cap: if a form has more than 100 total timeslots (existing + to-be-added), reject creation/update with a helpful message asking to split across multiple forms.

- Creator flows
  - On create via LLM: if `timeslot_schedule` present, create form (draft) then generate slots.
  - Optional future endpoints: cancel a slot, change capacity.

---

## UI/Template

- Form page lists available slots grouped by date (checkboxes for multi-select). Disable or hide full/cancelled/past slots.
- Validation: require at least one slot when the form has timeslots.
- Success and emails display selected slots (date + start–end times).
- No submission allowed for draft forms (existing behavior retained).
- Pagination/limit: show next N days by default with a "load more" affordance if there are many slots.
 - If a request would create >100 total timeslots, surface a clear message: "This form exceeds the current limit of 100 timeslots. Please split into multiple forms."

---

## Emails & Analytics

- Emails (to registrant and creator): include a section “Your selected timeslots” with a bullet list.
- Analytics additions: number of slots generated, slots booked, unique registrants, fill rate.
 - Timezone clarity: format times in the form's time_zone with clear abbreviations.

---

## Error Handling & Concurrency

- Enforce atomic booking using DB transactions and row-level locking.
- Return actionable errors with details: 409 Conflict and the list of timeslot_ids that failed.
- Idempotency: repeated submission with same registration ID should not overbook (unique join constraint + checks).
 - Validate schedule specs: cap `weeks_ahead` (e.g., <= 12), restrict `slot_minutes` to sensible values (e.g., 15, 30, 45, 60, 90, 120), ensure `window_start < window_end`.
 - Rate limiting is handled externally (reverse proxy/WAF); no app-level throttling changes required here.

---

## Incremental Tasks (Suggested MRs)

1) Data model + migrations
- Add `timeslots` and `registration_timeslots` tables via Alembic.
- Add SQLModel classes and basic indices.
- Include unique `(form_id, start_at, end_at)` from the start for idempotency.
- Add CHECK constraints for capacity/booked_count; add optional `signup_forms.time_zone`.
- Indexing: `idx_timeslots_form_start (form_id, start_at)`; composite index `(form_id, status, start_at)` to support explicit status queries; consider a partial index on `(form_id, start_at)` WHERE `booked_count < capacity` for fast availability scans.

2) Timeslot service
- Slot generation from schedule spec; list and DTOs.
- Booking with transactional locking; unit tests.
- Enforce spec validation (caps and allowed values); convert local TZ to UTC.
 - Enforce max 100 total timeslots per form (existing + newly generated). If exceeded, return a clear error instructing the creator to split across multiple forms.

3) Public router + template
- Render available slots on GET; accept `timeslot_ids` on POST.
- Persist selections; show them on success page.
 - Enforce form ownership of timeslot_ids; return 409 on conflicts, 422 on validation errors.
 - Add pagination/limit for slot listing.

4) LLM integration
- Update prompts (FORM_BUILDER_PROMPT) to extract `timeslot_schedule` when found in natural language.
- Extend `FormExtractionSchema` and `create_form_handler` to call slot generation.

5) Emails
- Include selected slots in registrant confirmation and creator notification.

6) Analytics
- Extend analytics tool to report slots, bookings, fill rate.
 - Add questions/metrics that consider time zones and scale (100+ slots).

7) Polish (optional)
- “Full”/“Cancelled” indicators, filtering/hiding past slots, capacity > 1.
- Optional form-level setting to limit max slots per registration.
 - Add housekeeping: optional job to archive/hide past slots and compress analytics.

---

## Incrementality Checklist

- MR-TS-1 to MR-TS-3 introduce schema and services only; no public behavior changes.
- MR-TS-4 is the first public change: template renders slots; POST `/form/{slug}` accepts `timeslot_ids`.
- MR-TS-5 is creator-facing but reuses existing `/gpt` and MCP tools; no new endpoints.
- MR-TS-6 and MR-TS-7 add non-breaking enhancements (emails/analytics/polish).
- Phase 2 (MR-TS-8..12) only augments draft-mode editing and internal logic; public endpoints remain the same.

---

## Acceptance Examples

- Creation: “Create a signup form for 1-1 soccer coaching between 5–9pm on Mondays and Wednesdays with 1 hour slots for the next 2 weeks.”
  - Creates draft form + 16 slots; preview shows slots disabled until published.

- Booking: Visitor selects one or more slots across days; submission succeeds; confirmation shows chosen slots.

- Overbook prevention: Ten concurrent submissions to the last slot → one succeeds, nine receive 409 with the unavailable slot id.
- Timezone: "5–9pm EST shows correctly for a user in PST (times converted to EST on the form)."
- Scale: "Forms with 100+ timeslots page quickly and paginate cleanly."

---

## Out of Scope (v1)

- Rescheduling/cancelling individual slots via creator UI; bulk edits.
- Time zone customization per form; daylight saving transitions.
- Payment integration and reminders.

---

## Draft Edits & Differential Updates

Creators can adjust timeslots while a form is in `draft`. Changes are additive or subtractive against the existing set of generated slots:

- Add schedules: Generate additional slots based on a new schedule spec and append them, deduped by `(form_id, start_at, end_at)`.
- Remove schedules: Remove all matching unbooked slots within a described window (e.g., specific weekdays and time ranges across N weeks); booked slots are preserved and reported back.

Constraints
- Only allowed while `status='draft'`.
- Never delete or shrink a slot that has bookings; instead skip and surface counts in the response.
- Deduplicate via a unique constraint `(form_id, start_at, end_at)` to make “add the same schedule” idempotent.

LLM extraction additions (for updates)
- timeslot_mutations
  - add: [TimeslotAddSpec]
  - remove: [TimeslotRemoveSpec]

TimeslotAddSpec (same as creation `timeslot_schedule`)
- days_of_week: ["monday", "wednesday", ...]
- window_start: "17:00"
- window_end: "21:00"
- slot_minutes: 60
- weeks_ahead: 2
- start_from_date: optional ISO date (default today)
- capacity_per_slot: optional int (default 1)

TimeslotRemoveSpec
- days_of_week: ["friday", ...]
- window_start: "17:00" (optional)
- window_end: "21:00" (optional)
- weeks_ahead: 4  (or end_date)
- start_from_date: optional ISO date (default today)

Service operations
- TimeslotService.add_schedule(form_id, add_spec) → upsert new slots (ignore duplicates by unique constraint).
- TimeslotService.remove_schedule(form_id, remove_spec) → delete unbooked matching slots; return counts `{removed, skipped_booked}`.

Router/handler integration
- Update `update_form_handler` to pass any extracted `timeslot_mutations` to TimeslotService when the target form is `draft`.
- Response messaging summarizes how many slots were added/removed and any booked slots that were preserved.

Example conversation (draft)
- User: “Create a signup for 1-1 soccer lessons from 5–9pm on Monday and Friday for the next 4 weeks.”
- System: “Draft created. Preview here: <link>. Say ‘publish’ when ready.”
- User: “Remove Fridays, but add Thursday 4–6pm for the next 2 weeks.”
- System: “Updated the draft: removed Friday slots (kept 0 booked), added Thursday slots (4 total). Now it includes Mondays 5–9pm for 4 weeks and Thursdays 4–6pm for 2 weeks.”

Testing
- Remove spec deletes only unbooked; booked remain and are reported.
- Re-adding the same schedule is idempotent (no duplicates).
- Publishing after edits keeps the final set of slots consistent.
