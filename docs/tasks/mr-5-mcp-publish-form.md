# MR-5: MCP Tool — publish_form

Goal: Add an MCP tool to publish draft forms, matching the behavior of `/gpt/publish-form`.

Scope
- Add `publish_form` tool to `server/src/ez_scheduler/routers/mcp_server.py`.
- Inputs: `user_id: str`, optional `form_id: str`, `url_slug: str`, `title_contains: str`.
- Behavior: Resolve form similarly to REST `_resolve_form_or_ask` parity. Ownership required. If archived → return conflict message. If already published → return idempotent message. Otherwise set `status=PUBLISHED` via `SignupFormService.update_signup_form`.
- Output: Human-readable string confirming publish or explaining why not.

Implementation Notes
- Follow the existing wiring pattern (db session via `get_db()`).
- Reuse existing `FormStatus` and service logic to enforce transitions.
- Keep messages consistent with REST responses to minimize UX differences.

Files To Change
- `server/src/ez_scheduler/routers/mcp_server.py`

Tool Signature (FastMCP)
```
@mcp.tool()
async def publish_form(
    user_id: str,
    form_id: str | None = None,
    url_slug: str | None = None,
    title_contains: str | None = None,
) -> str:
    ...
```

Acceptance Criteria
- `list_tools()` shows `publish_form` with a clear description and expected input schema.
- Publishing a draft returns success.
- Publishing an archived form returns a conflict/validation message.
- Publishing an already published form returns an idempotent message.

Tests
- MCP integration tests:
  - Tool listed and schema validated.
  - Publish from draft → success.
  - Publish archived → conflict message.
  - Publish already published → idempotent message.

Out of Scope
- Creating new state transitions beyond the current rules.

PR Checklist
- [ ] Tool implemented and registered.
- [ ] Tests added and passing locally.
- [ ] Docs updated if needed.
- [ ] Small, focused diff; no unrelated changes.
