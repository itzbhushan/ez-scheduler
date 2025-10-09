# Conversational Form Flow - Quick Summary

## Core Concept

**Server automatically manages conversation context** - clients just send messages, server handles everything else.

## Architecture

```
Client sends message
    ↓
Server auto-detects conversation thread (30-min window)
    ↓
Loads conversation history from Redis (LangChain)
    ↓
Loads form state from Redis (JSON)
    ↓
Processes message with LLM (with full context)
    ↓
Updates form state
    ↓
Saves to Redis (automatic TTL)
    ↓
Returns response
```

## Key Design Decisions

### 1. **Thread Management: Server-Side (Transparent)**
- ✅ Client never sees `thread_id`
- ✅ Server uses `active_thread:{user_id}` Redis key for O(1) lookup
- ✅ One active conversation per user (30-minute window)

### 2. **Storage: All Redis**
- ✅ Conversation history: LangChain's `RedisChatMessageHistory`
- ✅ Form state: Redis with JSON (`form_state:{thread_id}`)
- ✅ Automatic 30-minute TTL (sliding window)

### 3. **Create vs Update: Check for form_id**
```python
if response.action == "create_form":
    form_id = response.form_state.get("form_id")

    if form_id:
        # UPDATE existing draft
        update_draft(form_id, form_state)
    else:
        # CREATE new draft
        new_form = create_draft(form_state)
        # Store for future updates
        form_state_manager.update_state(thread_id, {"form_id": str(new_form.id)})
```

### 4. **Error Handling: Simple & Pragmatic**
- ❌ Redis unavailable → HTTP 503 (no fallback)
- ❌ LangChain fails → HTTP 503 (no fallback)
- ✅ Corrupted data → Log + reset (recoverable)
- ✅ LLM error → Retry once, user-friendly message

## API Specification

### MCP Tool
```python
create_or_update_form(
    user_id: str,
    message: str
) -> str
```

### REST Endpoint
```python
POST /gpt/create-or-update-form
{
  "description": "Create a form for my birthday"
}

Response:
{
  "response": "I'd love to help! When is your birthday?"
}
```

## Example Conversation Flow

```
Turn 1: "Create a birthday form"
→ State: { title: "Birthday", is_complete: false }
→ "When is the party?"

Turn 2: "Dec 15 at Central Park"
→ State: { event_date: "2024-12-15", location: "Central Park", is_complete: true }
→ "Ready to create?"

Turn 3: "Yes"
→ form_id = null → CREATE draft (id: uuid-123)
→ State: { form_id: "uuid-123", ... }
→ "Draft created! Preview: https://..."

Turn 4: "Change date to Dec 20"
→ form_id = uuid-123 → UPDATE draft
→ "Updated! Preview: https://..."

Turn 5: "Add guest_count field"
→ form_id = uuid-123 → UPDATE draft
→ "Updated! Preview: https://..."

Turn 6: "Publish it"
→ Publish + clear state
→ "Published! Share: https://..."
```

## Implementation Phases

| Phase | Time | Description |
|-------|------|-------------|
| 1. Core Infrastructure | 2-3h | ConversationManager + FormStateManager (Redis) |
| 2. Conversation Handler | 4-5h | LLM integration with context awareness |
| 3. Unified Tool | 5-6h | MCP tool + REST endpoint |
| 4. Migration | 2-3h | Deprecate old tools, documentation |
| 5. Testing | 4-5h | Unit + integration + E2E tests |
| **Total** | **17-22h** | |

## Dependencies

```bash
uv add langchain-community redis
```

## Configuration

```python
# config.py
"redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0")
```

## Key Benefits

✅ **Transparent to clients** - no thread management needed
✅ **Persistent** - survives server restarts (Redis)
✅ **Distributed-ready** - works across multiple servers
✅ **Automatic cleanup** - Redis TTL handles expiration
✅ **Battle-tested** - LangChain is widely used
✅ **Simple** - ~100 lines of wrapper code

## Files to Create

1. `server/src/ez_scheduler/services/conversation_manager.py`
2. `server/src/ez_scheduler/services/form_state_manager.py`
3. `server/src/ez_scheduler/handlers/form_conversation_handler.py`
4. `server/src/ez_scheduler/tools/create_or_update_form.py`
5. Unit tests (4 files)

## Files to Modify

1. `server/src/ez_scheduler/system_prompts.py` (add conversation-aware prompt)
2. `server/src/ez_scheduler/routers/mcp_server.py` (register new tool)
3. `server/src/ez_scheduler/routers/gpt_actions.py` (new endpoint)

---

**Status**: Ready for Implementation
**Updated**: 2025-10-06
