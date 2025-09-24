# MR-6: MCP Tool — archive_form

Status: Completed

Goal: Add an MCP tool to archive forms, matching the behavior of `/gpt/archive-form`.

Scope
- Add `archive_form` tool to `server/src/ez_scheduler/routers/mcp_server.py`.
- Inputs: `user_id: str`, optional `form_id: str`, `url_slug: str`, `title_contains: str`.
- Behavior: Resolve target form; enforce ownership. If already archived → idempotent message. Otherwise set `status=ARCHIVED` via `SignupFormService.update_signup_form`.
- Output: Human-readable string confirming archive or explaining why not.

Implementation Notes
- Same DB and service wiring patterns as other tools.
- Ensure public GET of archived forms remains 404 and that this tool does not attempt to unarchive.

Files To Change
- `server/src/ez_scheduler/routers/mcp_server.py`

Tool Signature (FastMCP)
```
@mcp.tool()
async def archive_form(
    user_id: str,
    form_id: str | None = None,
    url_slug: str | None = None,
    title_contains: str | None = None,
) -> str:
    ...
```

Acceptance Criteria
- `list_tools()` shows `archive_form` with expected schema.
- Archiving a published or draft form returns success message.
- Archiving an already archived form returns idempotent message.

Tests
- MCP integration tests confirm the above behaviors and schema.

Out of Scope
- Unarchive functionality (explicitly disallowed by lifecycle rules).

PR Checklist
- [ ] Tool implemented and registered.
- [ ] Tests added and passing locally.
- [ ] Docs updated if needed.
- [ ] Small, focused diff; no unrelated changes.
