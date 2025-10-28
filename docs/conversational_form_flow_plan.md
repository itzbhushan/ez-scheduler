# Conversational Form Flow Plan

## Problem Statement

Currently, the MCP server tools (`create_form` and `update_form`) alongside their `/gpt/*` REST API equivalents do not utilize conversation history while creating forms. This creates a suboptimal conversational experience:

- **Multiple back-and-forth interactions**: Users must provide information in small chunks across many turns
- **Context loss**: Each request is processed independently without memory of prior exchanges
- **User frustration**: Many users give up before completing form creation
- **Inefficient information gathering**: The LLM cannot build upon previous responses

## Goal

Enable the system to utilize user and system conversation history during form creation, allowing the LLM to:
- Remember all previously discussed form properties
- Build upon earlier responses without re-asking questions
- Make intelligent inferences based on conversation context
- Reduce the number of round trips needed to create a complete form

## Constraints

1. **In-memory form state**: Form properties are held in-memory until published (no temporary DB storage for drafts in progress)
2. **Single unified tool**: Replace `create_form` and `update_form` with `create_or_update_form`
3. **Published forms are immutable**: Once published, forms cannot be updated
4. **Deprecation path**: Once the new tool is stable, deprecate old tools

## Technology Decision: LangChain + Redis

After researching third-party libraries and evaluating implementation approaches, we've decided on **LangChain's RedisChatMessageHistory with Redis backend** for the following reasons:

### Why LangChain + Redis?

1. **Battle-tested**: LangChain's message history is widely used and well-maintained
2. **Redis already available**: We already use Redis, no new infrastructure needed
3. **Automatic TTL**: Redis handles expiration natively with sliding window support
4. **Persistence**: Conversations survive server restarts (useful for distributed deployments)
5. **Zero custom TTL logic**: No manual cleanup code needed
6. **Distributed-ready**: Works across multiple servers out of the box
7. **Simple integration**: ~100 lines of wrapper code vs ~300+ lines of custom implementation

### Our Approach: Redis-Backed Conversation Storage

We'll use Redis for both conversation history and form state:
- **ConversationManager**: Wraps LangChain's `RedisChatMessageHistory` for message storage
- **FormStateManager**: Uses Redis directly with JSON serialization for form state
- **Active thread tracking**: Simple Redis key to track user's most recent conversation
- **Automatic expiration**: 30-minute TTL with sliding window (resets on activity)

This approach:
- ✅ Minimal custom code (thin wrappers around proven libraries)
- ✅ Easy to understand and maintain
- ✅ Fast to implement (leverage existing tools)
- ✅ Sufficient for our use case (linear conversation flow)
- ✅ Compatible with both MCP and REST endpoints
- ✅ Production-ready (distributed, persistent, scalable)

## Architecture Overview

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
│  ┌─────────────────┐          ┌──────────────────┐         │
│  │  MCP Client     │          │  GPT REST API    │         │
│  │  (Claude.app)   │          │  (ChatGPT)       │         │
│  └────────┬────────┘          └────────┬─────────┘         │
└───────────┼──────────────────────────────┼──────────────────┘
            │                              │
            └──────────────┬───────────────┘
                           │
┌──────────────────────────┼───────────────────────────────────┐
│                          ▼                                    │
│            create_or_update_form(                            │
│                user_id,                                       │
│                message                                        │
│            )                                                  │
│            // No thread_id needed - server auto-detects!     │
│                          │                                    │
│            ┌─────────────▼────────────┐                      │
│            │ ConversationManager      │                      │
│            │ (LangChain + Redis)      │                      │
│            │ - get_or_create_thread() │                      │
│            │ - get_history()          │                      │
│            │ - add_message()          │                      │
│            └─────────────┬────────────┘                      │
│                          │                                    │
│            ┌─────────────▼────────────┐                      │
│            │ FormStateManager         │                      │
│            │ (Redis JSON)             │                      │
│            │ - get_state()            │                      │
│            │ - update_state()         │                      │
│            └─────────────┬────────────┘                      │
│                          │                                    │
│            ┌─────────────▼────────────┐                      │
│            │ FormConversationHandler  │                      │
│            │ - process_message(...)   │                      │
│            │ - extract_form_data(...) │                      │
│            │ - merge_form_state(...)  │                      │
│            └─────────────┬────────────┘                      │
│                          │                                    │
│            ┌─────────────▼────────────┐                      │
│            │      LLMClient           │                      │
│            │ - process_instruction()  │                      │
│            │   (with message history) │                      │
│            └──────────────────────────┘                      │
│                                                               │
│            All conversation data stored in Redis             │
│            with automatic 30-minute TTL                      │
└───────────────────────────────────────────────────────────────┘
```

### Session Management

```
Redis Storage Structure:

# Conversation messages (managed by LangChain)
message_store:user123::conv::abc456
  - List of serialized messages (LangChain's RedisChatMessageHistory)
  - TTL: 30 minutes (sliding window on every access)

# Active thread tracker (for quick lookup)
active_thread:user123
  - Value: "user123::conv::abc456" (most recent thread)
  - TTL: 30 minutes (sliding window)

# Form state (JSON)
form_state:user123::conv::abc456
  - JSON: {
      "title": "Birthday Party",
      "event_date": "2024-12-15",
      "location": "TBD",
      "custom_fields": [...],
      "is_complete": false,
      ...
    }
  - TTL: 30 minutes (sliding window)
```

## Implementation Plan: Task Breakdown

### Phase 1: Core Infrastructure (2-3 hours)

#### Task 1.1: Create ConversationManager Service
**Input:**
- `redis_url` (str): Redis connection URL
- `ttl_seconds` (int, default=1800): Time-to-live in seconds (30 minutes)
- `max_messages_per_thread` (int, default=20): Maximum messages to retain

**Output:**
- Thin wrapper around LangChain's RedisChatMessageHistory

**Business Logic:**
1. Use LangChain's `RedisChatMessageHistory` for message storage
2. Maintain `active_thread:{user_id}` key for quick lookup of user's current conversation
3. Automatic TTL handled by Redis (sliding window on access)
4. Methods:
   - `get_or_create_thread_for_user(user_id) -> str` (auto-detect active thread)
   - `get_history(thread_id) -> List[dict]`
   - `add_message(thread_id, role, content) -> None`
   - `clear_history(thread_id) -> None`

**Files to create:**
- `server/src/ez_scheduler/services/conversation_manager.py`

**Dependencies:**
- `langchain-community` (RedisChatMessageHistory)
- `redis`

---

#### Task 1.2: Create FormStateManager
**Input:**
- `redis_url` (str): Redis connection URL
- `ttl_seconds` (int, default=1800): Time-to-live in seconds (30 minutes)

**Output:**
- Redis-backed form state manager with JSON serialization

**Business Logic:**
1. Store form state in Redis with key pattern `form_state:{thread_id}`
2. Serialize/deserialize state as JSON
3. Automatic TTL handled by Redis (sliding window via `setex`)
4. Deep merge logic for custom_fields and button_config
5. Methods:
   - `get_state(thread_id) -> dict`
   - `update_state(thread_id, updates: dict) -> dict`
   - `clear_state(thread_id) -> None`
   - `is_complete(state: dict) -> bool`

**Files to create:**
- `server/src/ez_scheduler/services/form_state_manager.py`

**Dependencies:**
- `redis`

---

### Phase 2: Conversation Handler (4-5 hours)

#### Task 2.1: Create FormConversationHandler
**Input:**
- `user` (User): Current user object
- `thread_id` (str): Conversation thread identifier
- `user_message` (str): Latest user message
- `llm_client` (LLMClient): LLM client instance
- `conversation_manager` (ConversationManager): Conversation history manager
- `form_state_manager` (FormStateManager): Form state manager

**Output:**
- `ConversationResponse` with:
  - `response_text` (str): Message to user
  - `extracted_data` (FormExtractionSchema): Extracted/updated form data
  - `action` (str): "continue" | "create_form" (publish handled in browser flow)
  - `form_state` (dict): Current complete form state

**Business Logic:**
1. Retrieve conversation history from ConversationManager
2. Retrieve current form state from FormStateManager
3. Build context message with:
   - Conversation history (last 10-20 messages)
   - Current form state (if any)
   - User's new message
4. Send to LLM with updated system prompt
5. Parse LLM response (JSON with FormExtractionSchema)
6. Merge extracted data with existing form state
7. Add both user message and assistant response to history
8. Update form state
9. Return response

**Files to create:**
- `server/src/ez_scheduler/handlers/form_conversation_handler.py`

**Dependencies:**
- ConversationManager
- FormStateManager
- LLMClient
- Existing FormExtractionSchema

---

#### Task 2.2: Update System Prompt for Conversation Context
**Input:**
- Existing `FORM_BUILDER_PROMPT`

**Output:**
- Enhanced system prompt that understands conversation context

**Business Logic:**
1. Add instructions for processing conversation history
2. Add instructions for partial form state awareness
3. Add guidance on not re-asking for information already provided
4. Add examples of multi-turn conversations
5. Instructions on when to ask clarifying questions vs. making reasonable assumptions

**Changes:**
```
New sections to add:
- "CONVERSATION CONTEXT": How to use message history
- "FORM STATE AWARENESS": How to reference existing partial state
- "INCREMENTAL UPDATES": Merge new info with existing
- "SMART DEFAULTS": When to infer vs. ask
```

**Files to modify:**
- `server/src/ez_scheduler/system_prompts.py`

**Dependencies:**
- None

---

### Phase 3: Unified Tool Implementation (5-6 hours)

#### Task 3.1: Implement create_or_update_form MCP Tool
**Input:**
- `user_id` (str): Auth0 user identifier
- `message` (str): User's message
- `action` (str, optional): "create" | "publish" | None (auto-detect)

**Output:**
- String response to user with:
  - Natural language response
  - Form preview URL (if draft created/updated)
  - Publishing confirmation (if published)
  - Next steps or questions

**Business Logic:**
1. **Auto-detect thread**: Call `conversation_manager.get_or_create_thread_for_user(user_id)`
   - Returns existing active thread within 30 min window, or creates new one
   - Client doesn't need to track thread_id!
2. Load conversation history and form state using detected thread
3. Process message through FormConversationHandler
4. Based on handler response action:
   - **continue**: Return response to user (keep iterating)
   - **create_form**: Check for existing draft:
     - If `form_id` exists in state → **UPDATE** existing draft
     - If no `form_id` → **CREATE** new draft, store `form_id` in state
   - **(removed) publish_form**: Publishing now occurs via the browser UI once drafts are complete
5. Conversation history automatically maintained by ConversationManager

**Create vs Update Logic:**
```python
if response.action == "create_form" and response.is_complete:
    form_id = response.form_state.get("form_id")

    if form_id:
        # UPDATE existing draft
        updated_form = await _update_existing_draft(
            form_id=form_id,
            form_state=response.form_state,
            signup_form_service=signup_form_service,
            form_field_service=form_field_service
        )
        return f"Updated your draft! Preview: {preview_url}"
    else:
        # CREATE new draft
        new_form = await _create_draft_form(...)
        # Store form_id for future updates
        form_state_manager.update_state(thread_id, {"form_id": str(new_form.id)})
        return f"Draft created! Preview: {preview_url}"
```

**Files to create:**
- `server/src/ez_scheduler/tools/create_or_update_form.py` (new file)

**Dependencies:**
- ConversationManager (LangChain + Redis)
- FormStateManager (Redis)
- FormConversationHandler
- SignupFormService
- FormFieldService

---

#### Task 3.2: Implement /gpt/create-or-update-form REST Endpoint
**Input:**
- Request body (matches current `/gpt/create-form` format):
  ```json
  {
    "description": "User's message/description"
  }
  ```
- User from Auth0 token (no thread_id needed!)

**Output:**
- Response (matches current format):
  ```json
  {
    "response": "Natural language response"
  }
  ```

**Business Logic:**
1. **Auto-detect thread**: Server automatically finds/creates thread for user
2. Call create_or_update_form handler with user_id and description
3. Return simple response object (consistent with existing `/gpt/create-form`)
4. Client just sends messages, server manages conversation continuity transparently

**Files to modify:**
- `server/src/ez_scheduler/routers/gpt_actions.py`

**Dependencies:**
- Same as Task 3.1

**Note**: Keep response format simple and consistent with existing GPT endpoints. Status/preview_url/form_id can be extracted from the response text.

---

### Phase 4: Migration & Deprecation (2-3 hours)

#### Task 4.1: Update MCP Tool Registration
**Input:**
- Existing MCP server configuration

**Output:**
- Updated tool registry with new tool

**Business Logic:**
1. Register `create_or_update_form` tool
2. Mark `create_form` and `update_form` as deprecated
3. Add deprecation warnings to old tools
4. Update tool descriptions

**Files to modify:**
- `server/src/ez_scheduler/routers/mcp_server.py`

**Dependencies:**
- Completed Task 3.1

---

#### Task 4.2: Create Migration Documentation
**Input:**
- Old tool usage patterns
- New tool usage patterns

**Output:**
- Migration guide document

**Business Logic:**
1. Document differences between old and new tools
2. Provide example conversations
3. Document thread_id management
4. Provide code examples for both MCP and REST clients

**Files to create:**
- `docs/migration_to_conversational_flow.md`

**Dependencies:**
- None

---

### Phase 5: Testing & Validation (4-5 hours)

#### Task 5.1: Unit Tests for ConversationManager
**Test Cases:**
1. Adding messages to new conversation
2. Retrieving conversation history
3. History trimming (max messages)
4. Clearing conversation
5. Stale conversation cleanup
6. Multiple concurrent conversations

**Files to create:**
- `server/tests/test_conversation_manager.py`

---

#### Task 5.2: Unit Tests for FormStateManager
**Test Cases:**
1. Creating new form state
2. Updating partial state
3. Merging updates
4. Completeness validation
5. Clearing state
6. Concurrent state management

**Files to create:**
- `server/tests/test_form_state_manager.py`

---

#### Task 5.3: Integration Tests for create_or_update_form
**Test Cases:**
1. Complete single-turn form creation
2. Multi-turn form creation (3-4 exchanges)
3. Form updates in conversation
4. Publishing from conversation
5. Conversation context preservation
6. Error handling and recovery
7. Thread isolation (different users)

**Files to create:**
- `server/tests/test_create_or_update_form_mcp.py`
- `server/tests/test_create_or_update_form_gpt.py`

---

#### Task 5.4: End-to-End Conversation Tests
**Test Cases:**
1. Realistic wedding form creation (5+ turns)
2. Conference form with custom fields (4+ turns)
3. Form creation with timeslots (6+ turns)
4. Error correction in conversation
5. Changing decisions mid-conversation

**Files to create:**
- `server/tests/test_conversational_flows.py`

---

## Data Flow Example

### Draft Create vs Update Flow

```
┌─────────────────────────────────────────────────────────────┐
│          User sends message in conversation                  │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
         ┌────────────────────┐
         │ Process with LLM   │
         │ (with history)     │
         └────────┬───────────┘
                  │
                  ▼
         ┌────────────────────┐
         │ Action = ?         │
         └────────┬───────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
   "continue"        "create_form"
        │                   │
        │                   ▼
        │          ┌────────────────────┐
        │          │ Check form_state   │
        │          │ for form_id?       │
        │          └────────┬───────────┘
        │                   │
        │          ┌────────┴────────┐
        │          │                 │
        │          ▼                 ▼
        │    form_id EXISTS    NO form_id
        │          │                 │
        │          ▼                 ▼
        │  ┌──────────────┐   ┌──────────────┐
        │  │ UPDATE       │   │ CREATE       │
        │  │ existing     │   │ new draft    │
        │  │ draft in DB  │   │ in DB        │
        │  └──────┬───────┘   └──────┬───────┘
        │         │                  │
        │         │                  ▼
        │         │          ┌──────────────────┐
        │         │          │ Store form_id    │
        │         │          │ in form_state    │
        │         │          └──────┬───────────┘
        │         │                 │
        │         └─────────┬───────┘
        │                   │
        ▼                   ▼
   Return response    Return response
   (keep chatting)    (draft created/updated)
```

### Example: Multi-Turn Birthday Party Form Creation

**Turn 1:**
```
User: "Create a signup form for my birthday party"

Thread ID: "thread_abc123"
History: []
Form State: {}

→ LLM processes with empty context
→ Response: "I'd love to help! When is your birthday and where will it be?"

Updated History: [
  {role: "user", content: "Create a signup form for my birthday party"},
  {role: "assistant", content: "I'd love to help! When is..."}
]

Updated Form State: {
  title: "Birthday Party",
  event_date: null,
  location: null,
  description: null,
  is_complete: false
}
```

**Turn 2:**
```
User: "December 15th at Central Park"

Thread ID: "thread_abc123"
History: [previous 2 messages]
Form State: {title: "Birthday Party", ...}

→ LLM processes WITH conversation context
→ Knows this is continuing the birthday party form
→ Response: "Perfect! To make this invitation special, whose birthday is it?"

Updated Form State: {
  title: "Birthday Party",
  event_date: "2024-12-15",
  location: "Central Park",
  description: null,
  is_complete: false
}
```

**Turn 3:**
```
User: "It's for Sarah, she's turning 30"

Thread ID: "thread_abc123"
History: [previous 4 messages]
Form State: {title: "Birthday Party", event_date: "2024-12-15", ...}

→ LLM processes WITH full context
→ Knows: birthday party, Dec 15, Central Park, for Sarah turning 30
→ Response: "Great! Would you like to add any custom fields like guest count or dietary preferences?"

Updated Form State: {
  title: "Sarah's 30th Birthday Party",
  event_date: "2024-12-15",
  location: "Central Park",
  description: "Join us in celebrating Sarah's 30th birthday...",
  is_complete: false (waiting for custom fields decision)
}
```

**Turn 4:**
```
User: "No additional fields needed, just keep it simple"

Thread ID: "thread_abc123"
History: [previous 6 messages]
Form State: {title: "Sarah's 30th Birthday Party", ..., is_complete: true, form_id: null}

→ LLM processes WITH full context
→ Marks form as complete
→ Action: "create_form"

Handler checks: form_id exists? NO
→ CREATE new draft in database
→ form_id: uuid-form-123
→ Store in state: {form_id: "uuid-form-123", ...}
→ Response: "Draft created! Preview: https://.../sarahs-birthday-abc123"
```

**Turn 5: User Makes Changes**
```
User: "Change the date to December 20th"

Thread ID: "thread_abc123" (same thread)
Form State: {form_id: "uuid-form-123", event_date: "2024-12-15", ...}

→ LLM extracts: {event_date: "2024-12-20"}
→ Action: "create_form"

Handler checks: form_id exists? YES → uuid-form-123
→ UPDATE existing draft (not create new!)
→ Response: "Updated your draft! Preview: https://..."
```

**Turn 6: More Changes**
```
User: "Add a guest_count field"

Form State: {form_id: "uuid-form-123", ...}

Handler checks: form_id exists? YES
→ UPDATE existing draft
→ Response: "Updated! Preview: https://..."
```

**Turn 7: Publish**
```
User: "Publish it"

→ Action: "continue" (LLM reminds user to publish via browser UI)
→ Response: "Open the draft in your browser and click Publish to make it live."
```

## Session Cleanup Strategy

### Automatic Cleanup (Redis Native TTL)
- **Trigger**: Automatic, handled by Redis
- **Mechanism**: All keys have 30-minute TTL (sliding window)
- **Sliding Window**: TTL resets on every access/update
- **No Background Tasks Needed**: Redis handles expiration natively
- **Keys Auto-Expire**:
  - `message_store:*` (LangChain messages)
  - `active_thread:*` (thread tracking)
  - `form_state:*` (form state)

### Manual Cleanup
- **Trigger**: Explicit API call or after form publish
- **Options**:
  - Clear specific thread: `conversation_manager.clear_history(thread_id)` + `form_state_manager.clear_state(thread_id)`
  - Clear on publish: Automatically clear both conversation and state after successful publish

## Performance Considerations

### Memory Management (Redis)
- **Conversation History**: Max 20 messages per thread × ~500 chars = ~10KB per thread
- **Form State**: ~2KB per thread (JSON serialized)
- **Redis Memory**: ~12KB per active conversation
- **Estimated Capacity**: Redis can handle 10,000+ concurrent conversations easily
- **TTL Cleanup**: Automatic expiration keeps memory usage bounded
- **Scalable**: Redis can be scaled independently if needed

### Token Usage
- **Per Request**: ~1000-2000 tokens (history + new message + system prompt)
- **Cost Impact**: Minimal for typical conversations (3-5 turns)
- **Optimization**: Trim very old messages if conversation exceeds 20 turns

### Redis Performance
- **Key Operations**: O(1) lookup for active thread and form state
- **Message History**: O(N) where N = message count (max 20)
- **Network Latency**: Local Redis <1ms, remote Redis <10ms
- **Throughput**: Redis handles 100K+ ops/sec easily

## Error Handling

### Critical Dependencies (No Fallback)
1. **Redis Unavailable**: System unavailable - Redis is required for operation
2. **LangChain Fails**: System unavailable - LangChain is required for conversation storage
3. **Both are critical infrastructure** - If either fails, the service cannot function

### Recoverable Errors
1. **Corrupted State**: Log error, return empty state template, start fresh conversation
2. **LLM Errors**: Retry once, then return user-friendly error message
3. **Expired Session**: User message starts new conversation automatically (transparent)
4. **Invalid User Input**: Validate and return clear error messages

### Error Response Pattern
```python
# Redis/LangChain failures → HTTP 503 Service Unavailable
# LLM failures → Retry once, then user-friendly message
# Data corruption → Log + reset, inform user gracefully
# Validation errors → HTTP 400 with clear message
```

## Success Metrics

### Conversation Efficiency
- **Target**: Average 3-4 turns to create complete form (down from 6-8 currently)
- **Measure**: Track turns per form creation
- **Goal**: 40% reduction in conversation length

### User Satisfaction
- **Target**: Reduce form creation abandonment rate by 50%
- **Measure**: Track completion rate (forms created / conversations started)
- **Goal**: >70% completion rate

### Context Accuracy
- **Target**: LLM correctly references previous messages >95% of the time
- **Measure**: Manual review of conversations
- **Goal**: No repeated questions for already-provided info

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Core Infrastructure (Redis + LangChain) | 2-3 hours | None |
| Phase 2: Conversation Handler | 4-5 hours | Phase 1 |
| Phase 3: Unified Tool | 5-6 hours | Phase 1, 2 |
| Phase 4: Migration | 2-3 hours | Phase 3 |
| Phase 5: Testing | 4-5 hours | All previous |
| **Total** | **17-22 hours** | |

**Note**: Reduced from 18-23 hours due to using LangChain instead of custom implementation

## Next Steps

1. ✅ Review and approve this plan
2. ⏳ Start with Phase 1: ConversationManager implementation
3. Test each phase independently before moving to next
4. Deploy to staging for real-world testing
5. Monitor metrics and iterate
6. Deprecate old tools once stable

## Architecture Decisions Summary

1. **Thread ID Management**: ✅ Server auto-detects threads transparently
   - Client never sees or manages thread_id
   - Server uses `active_thread:{user_id}` Redis key for O(1) lookup
   - One active conversation per user (30-minute window)

2. **Persistence**: ✅ Redis with 30-minute TTL (sliding window)
   - Conversations survive server restarts
   - Automatic cleanup via Redis TTL
   - Distributed-ready for multi-server deployments

3. **Storage Backend**: ✅ All Redis (LangChain + native Redis)
   - ConversationManager: LangChain's `RedisChatMessageHistory`
   - FormStateManager: Redis with JSON serialization
   - Consistent storage strategy

4. **Context Window**: ✅ 20 messages maximum
   - Sufficient for form creation conversations
   - Keeps token usage manageable
   - Can be tuned based on real-world usage

5. **Future Enhancement**: Topic detection for parallel form creation
   - Use LLM to detect when user starts new topic
   - Create new thread automatically
   - Feature-flagged for gradual rollout

---

**Document Version**: 1.0
**Created**: 2025-10-06
**Author**: Claude Code Assistant
**Status**: Ready for Review
