# Timeslot Signup — Incremental Tasks (Phase 2: Draft Updates)

Last updated: 2025-09-24

---

## MR-TS-8: Performance & Safeguards (internal)

- DB
  - Add/adjust supporting indexes (e.g., partial indexes) for `list_available` queries if needed.
  - If unique `(form_id, start_at, end_at)` was not present initially, add a validating migration to fail on duplicates (but we target including it in MR-TS-1 to avoid cleanup).
- Model
  - Ensure SQLModel reflects any index/constraint updates.
- Acceptance
  - Query plans are efficient for listing slots by form/date; no behavior changes.

## MR-TS-9: TimeslotService — Add/Remove Schedules (internal)

- Add APIs
  - `add_schedule(form_id, add_spec)` → generates slots and inserts with ON CONFLICT DO NOTHING (or checks), returns `{added_count}`.
  - `remove_schedule(form_id, remove_spec)` → deletes unbooked matching slots, returns `{removed_count, skipped_booked}`.
- Helpers
  - Filter builder for (weekday, time-window, date range) matching.
- Acceptance
  - Removing a weekday/time window across N weeks deletes only unbooked slots.
  - Booked slots remain; `skipped_booked` reports the count.
  - Validate remove/add specs (caps on `weeks_ahead`, allowed `slot_minutes`, non-empty weekdays).
  - Enforce max of 100 total timeslots per form (existing + added). If adding would exceed the cap, return a clear error instructing the creator to split into multiple forms.

## MR-TS-10: Update Flow Integration (LLM/Router) — intent-based

- LLM (no new endpoint)
  - Extend `FORM_BUILDER_PROMPT` to allow `timeslot_mutations.add[]` and `timeslot_mutations.remove[]` in update flows.
- Tooling/Router
  - Extend `FormExtractionSchema` in `create_form.py` with `timeslot_mutations` models.
  - In `update_form_handler`, when form is `draft`, call TimeslotService add/remove per extracted mutations; accumulate a summary string.
- Acceptance
  - The example conversation (“remove Fridays; add Thursday 4–6pm for 2 weeks”) updates the draft and returns a summary.
  - No new endpoints; prompt changes limited to update addendum only.
  - Router surfaces 409 with unavailable ids when applicable; 422 on malformed specs.
  - If an add mutation would exceed 100 total slots, return a friendly message guiding the user to split forms.

## MR-TS-11: Template & Validation Adjustments (public form only)

- UI
  - Refresh available slots after mutations on preview; ensure the draft page reflects new/removed slots.
- Server
  - POST validation: for timeslot forms, require `timeslot_ids` only when there are available slots (no change when there are none).
- Acceptance
  - Draft page shows updated slots; published submission behavior unchanged.
  - Pagination for many slots works; grouping by date remains correct after mutations.

## MR-TS-12: Tests — Draft Edits

- Add tests
  - Generate Mon+Fri, then remove Fri; ensure only Mon remain.
  - Add Thu 4–6pm for 2 weeks → adds 4 1-hour slots.
  - Attempt removal where some slots are booked; assert counts and preservation.
- Acceptance
  - All tests pass; no duplicates on repeated adds.
  - Concurrency test: simulate 10 bookings against a single last slot; only 1 success.

---

See `docs/timeslot_signup_plan.md` for design details.
