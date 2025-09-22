# Signup Form Preview & Publish Plan


Last updated: 2025-09-22

---

## Overview

We will introduce a preview/publish lifecycle for signup forms so creators can iterate on content (title, description, date/time, custom fields), preview the result at the live URL, and publish when ready. Previewed (unpublished) forms render with a clear visual indicator and do not accept registrations. Only published forms accept registrations. The conversational agent will explicitly ask the user to publish and perform the publish action on confirmation.

Given there is only one production form and it can be manually patched, we will not maintain backward compatibility. We will immediately unify the archival flag and publish state under a single `status` field and enforce behavior consistently across GET and POST.

---

## Definitions

- Status: One of `draft`, `published`, `archived`.
- Draft (preview): Visible at `/form/{slug}`, shows a banner/indicator, and does not allow submission.
- Published: Visible at `/form/{slug}`, ready to share, accepts registrations.
- Archived: Not visible publicly; effectively replaces legacy `is_active=False`.

### Status Enum (DB + Model)

- Database: Use a PostgreSQL ENUM type named `signup_form_status` with values `('draft','published','archived')`.
- Model: Define a Python Enum `FormStatus(str, Enum)` with `DRAFT='draft'`, `PUBLISHED='published'`, `ARCHIVED='archived'` and map it using SQLAlchemy's `Enum` in the SQLModel field.
- Default: `draft` (DB server default and model default).

### State Transitions

- Allowed:
  - `draft` → `published`
  - `draft` → `archived`
  - `published` → `archived`
- Forbidden:
  - `published` → `draft` (per requirement)
  - `archived` → `draft`
  - `archived` → `published` (explicitly disallowed)

Serving rules:
- `draft` and `published` are publicly viewable (preview banner for `draft`).
- `archived` is not served publicly; GET `/form/{slug}` must return 404.

---

## Requirements → Implementation

- Preview changes until satisfied: Creator edits via existing update flow; URL remains stable via `url_slug`.
- Preview URL: Same URL `/form/{slug}` shows a banner if `status='draft'`.
- No registrations in preview: Server rejects POST unless `status='published'`; UI also disables CTA.
- Visual indicator: Prominent banner for `draft` forms; hide/disable submission controls.
- Conversational agent publish: New GPT action to publish/unpublish; prompt updated to ask user for publish confirmation.
- Only published forms accept registrations: Enforced at both router and service.

---

## Milestones and Merge Requests

Each item below is intended as a separate MR. Acceptance criteria and code touchpoints are listed for each.

### MR-0: Add this plan (Docs)
- Goal: Land a clear plan with no-backcompat scope and sequencing.
- Deliverables:
  - `docs/preview_publish_plan.md` (this file).
- Acceptance:
  - Team reviews and agrees on sequence.

### MR-1: Unify lifecycle — replace is_active with status
- Goal: Move to a single lifecycle field and immediate enforcement.
- Changes:
  - Model: `server/src/ez_scheduler/models/signup_form.py`
    - Define `FormStatus` Python Enum and map `status: FormStatus` via SQLAlchemy `Enum(FormStatus, name='signup_form_status', native_enum=True)`.
    - Remove `is_active` from the model.
  - Migration: `server/alembic/versions/*_replace_is_active_with_status.py`
    - Create enum type `signup_form_status` with values `('draft','published','archived')`.
    - Add `status` column of that enum with `server_default='draft'`, `nullable=False`.
    - Backfill: set `status='published'` for all existing rows.
    - Indexes:
      - Drop legacy index on `is_active` (e.g., `ix_signup_forms_is_active`).
      - Add single-column index on `status` (e.g., `ix_signup_forms_status`).
      - Add composite index to optimize slug lookups with status filter (e.g., `idx_signup_forms_url_slug_status` on `(url_slug, status)`).
      - Ensure existing `url_slug` unique/index remains intact.
    - Drop `is_active` column.
  - Services/Queries:
    - `SignupFormService.get_form_by_url_slug`: return form where `status IN ('draft','published')`.
    - `RegistrationService.create_registration`: require `status='published'`; raise clear error otherwise.
    - Soft delete → set `status='archived'` in delete method.
    - Transition validation helpers:
      - Implement `FormStatus.can_transition_to(new_status)` & a centralized validator in the service.
      - Enforce transitions: block `published` → `draft` and any transition out of `archived` (including `archived` → `published`) with a validation error.
      - Provide only `publish(form)` and `archive(form)` helpers.
  - Creation default:
    - `tools/create_form.py`: set `status='draft'` on create.
  - Prompts/Docs:
    - `system_prompts.py`: Update schema in `SQL_GENERATOR_PROMPT` to use `status` (enum) instead of `is_active`.
  - Tests impact and updates:
    - Replace test usage of `is_active=True/False` with `status='published'/'archived'`.
    - For tests that submit registrations or expect submit buttons, ensure forms are created with `status='published'` (via a helper/fixture).
    - For tests that assert form creation via agent, expect `status='draft'` as default.
    - Add tests for 403 on POST when `status='draft'` and for GET 404 when `status='archived'`.
    - Add tests that attempting `published` → `draft` fails.
- Acceptance:
  - DB migration applies; app starts.
  - GET `/form/{slug}` returns 200 for `draft` and `published`, 404 for `archived`.
  - POST `/form/{slug}` accepts only when `published`.
  - All tests updated and passing.

### MR-2: UI Preview Indicator
- Goal: Make draft forms visibly distinct and discourage submissions on the client.
- Changes:
  - Templates: `templates/form.html`, `templates/themes/golu_form.html`
    - If `form.status == 'draft'`, render a prominent banner: “Preview — registrations are disabled”.
    - Disable/hide submit buttons; intercept with client-side message.
  - Router GET: `routers/registration.py` already passes form; no extra changes needed beyond rendering.
- Acceptance:
  - GET `/form/{slug}` shows preview banner for draft forms.
  - Buttons are visibly disabled/hidden for draft forms.

### MR-3: Agent Integration (Publish/Archive)
- Goal: Let the conversational agent ask to publish and publish on confirmation.
- Changes:
  - Router: `routers/gpt_actions.py`
    - Add `POST /gpt/publish-form` and `POST /gpt/archive-form` (owner-only via `get_current_user`).
    - Accept `form_id` or `url_slug`; verify ownership.
    - If `status='archived'`, publishing returns a validation error (400/409) with guidance (e.g., duplicate the form instead).
  - Prompts: `system_prompts.py`
    - Update `FORM_RESPONSE_PROMPT` to clearly state preview state and ask: “Should I publish it now?”.
    - Ensure agent calls `publish-form` when user confirms.
    - Do not offer “unpublish to draft”; instead offer to archive if needed.
  - Auditability:
    - Emit audit logs for status changes initiated via agent.
- Acceptance:
  - Agent-created form reply mentions preview and asks to publish.
  - GPT endpoints toggle status with proper auth; tests cover ownership checks.

### MR-4: Polish and UX Enhancements (optional)
- Goal: Improve clarity for creators and visitors.
- Ideas:
  - “Published”/“Preview” chips on pages.
  - Share CTA only when published.
  - Analytics default to exclude `draft`.

### MR-5: Polish and UX Enhancements (optional)
- Goal: Improve clarity for creators and visitors.
- Ideas:
  - “Published”/“Preview” chips on pages.
  - Share CTA only when published.
  - Analytics default to exclude `draft`.

---

## Test Plan (incremental)

- MR-1:
  - Migration adds `status` and drops `is_active`.
  - Registration blocked for `draft`; allowed for `published`.
  - GET hidden for `archived`.
  - Fixtures/helpers: add `make_published_form(...)` and use it in tests that submit or verify registration; update existing assertions from `is_active` to `status`.
- MR-2: GET HTML shows preview banner and client-side CTA disable for draft.
 - MR-3: GPT publish/archive endpoints with ownership tests.
 - MR-4: Optional UI polish verifications (chips/banner visibility), no API changes.
  - Add negative tests: attempt to publish when `status='archived'` returns 400/409; attempting `published` → `draft` returns validation error.

---

## Rollout & Compatibility

- No backward-compat guarantees required.
- Migrations:
  - MR-1 adds `status`, migrates existing rows to `published`, and drops `is_active`.

---

## Code Touchpoints (by file)

- Models:
  - `server/src/ez_scheduler/models/signup_form.py`
- Services:
  - `server/src/ez_scheduler/services/signup_form_service.py`
  - `server/src/ez_scheduler/services/registration_service.py`
- Routers:
  - `server/src/ez_scheduler/routers/registration.py`
  - `server/src/ez_scheduler/routers/gpt_actions.py`
- Templates:
  - `server/src/ez_scheduler/templates/form.html`
  - `server/src/ez_scheduler/templates/themes/golu_form.html`
- Prompts:
  - `server/src/ez_scheduler/system_prompts.py`
- Migrations:
  - `server/alembic/versions/*_replace_is_active_with_status.py`

---

## Open Questions / Assumptions

- Public visibility of draft forms: OK as read-only preview (no registration). If this needs to be restricted to owners only, we can add an auth gate or preview token later.
- Status storage: Use DB enum immediately with Python Enum mapping in the model.
- Copy/styling: Refine banner text in MR-2 and polish in MR-4.

---

## Progress Checklist

- [x] MR-0: Plan documented (this file)
- [ ] MR-1: Unify lifecycle; status enforced; drop is_active
- [ ] MR-2: UI preview indicator
- [ ] MR-3: Agent integration
- [ ] MR-4: Polish/UX

---

## Next Session Starting Points

- Implement MR-1: Add `status` to model; add migration to create `status`, migrate rows to `published`, drop `is_active`; update services and queries to use `status`; enforce POST only on `published`; update tests.
- Update `system_prompts.py` schema notes from `is_active` → `status`.
- Ensure create flow sets `status='draft'` by default.
