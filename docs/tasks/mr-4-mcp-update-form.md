# MR-4: MCP Tool — update_form

Status: Completed

Goal: Add an MCP tool to update draft forms, matching the behavior of the existing `/gpt/update-form` endpoint and reusing the `update_form_handler` logic.

Scope
- Add `update_form` tool to `server/src/ez_scheduler/routers/mcp_server.py`.
- Inputs: `user_id: str`, `update_description: str`, optional `form_id: str`, `url_slug: str`, `title_contains: str`.
- Behavior: Delegate to `ez_scheduler.tools.create_form.update_form_handler` with proper service wiring. Must enforce ownership and state rules via the handler/service.
- Output: Human-readable string with preview URL and next step guidance.

Implementation Notes
- Reuse `get_llm_client()` and `get_db()` to construct dependencies, as done for existing MCP tools.
- Construct `User(user_id=..., claims={})` and pass through.
- Use `SignupFormService` and `FormFieldService` for DB operations (same as REST endpoint).
- Keep parity with `/gpt/update-form` resolution order: `form_id → url_slug → title_contains (drafts) → latest draft`.

Files To Change
- `server/src/ez_scheduler/routers/mcp_server.py`

New/Existing Helpers
- `ez_scheduler.tools.create_form.update_form_handler`
- `ez_scheduler.services.signup_form_service.SignupFormService`
- `ez_scheduler.services.form_field_service.FormFieldService`

Tool Signature (FastMCP)
```
@mcp.tool()
async def update_form(
    user_id: str,
    update_description: str,
    form_id: str | None = None,
    url_slug: str | None = None,
    title_contains: str | None = None,
) -> str:
    ...
```

Acceptance Criteria
- `list_tools()` shows `update_form` with a sensible description and input schema.
- Calling the tool updates a draft form and returns a message containing the preview URL and publish guidance.
- Attempts to update archived forms are rejected with a clear message.
- Ownership is enforced.

Tests
- Add MCP integration tests similar to `server/tests/test_basic_mcp_server_connection.py`:
  - Tool is listed and has schema for `user_id` and `update_description`.
  - Happy path: create a draft, call tool to update title/fields, assert response mentions the preview URL.
  - Negative: attempt to update archived returns an error message.

Out of Scope
- No changes to REST endpoints.
- No changes to LLM prompts or schemas.

PR Checklist
- [ ] Tool implemented and registered.
- [ ] Unit/integration tests added and passing locally.
- [ ] Docs updated if needed.
- [ ] Small, focused diff; no unrelated changes.
