# Conversational Form Flow - Task Breakdown (Updated with LangChain + Redis)

This document provides detailed task descriptions for implementing the conversational form flow feature using LangChain's RedisChatMessageHistory and Redis backend. Each task includes input specifications, output specifications, and detailed business logic.

---

## Phase 1: Core Infrastructure (Redis + LangChain)

### Task 1.1: ConversationManager Service

**Priority**: P0 (Critical - Foundation)
**Estimated Time**: 1.5 hours
**File**: `server/src/ez_scheduler/services/conversation_manager.py`

#### Input Specifications

```python
from langchain_community.chat_message_histories import RedisChatMessageHistory
import redis
from typing import Dict, List, Literal, Optional

class ConversationManager:
    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = 1800,  # 30 minutes
        max_messages_per_thread: int = 20
    )

    def get_or_create_thread_for_user(
        self,
        user_id: str
    ) -> str

    def add_message(
        self,
        thread_id: str,
        role: Literal["user", "assistant"],
        content: str
    ) -> None

    def get_history(
        self,
        thread_id: str
    ) -> List[Dict[str, str]]

    def clear_history(
        self,
        thread_id: str
    ) -> None
```

**Input Parameters:**
- `redis_url`: Redis connection URL (e.g., `redis://localhost:6379/0`)
- `ttl_seconds`: Time-to-live in seconds (default: 1800 = 30 minutes)
- `max_messages_per_thread`: Maximum messages to retain per thread (default: 20)
- `user_id`: User identifier for thread auto-detection
- `thread_id`: Conversation thread identifier
- `role`: Either "user" or "assistant"
- `content`: The message text

#### Output Specifications

**`get_or_create_thread_for_user()` returns:**
```python
"user123::conv::abc456def789"  # Auto-detected or newly created thread_id
```

**`get_history()` returns:**
```python
[
    {
        "role": "user",
        "content": "Create a form for my birthday party"
    },
    {
        "role": "assistant",
        "content": "I'd love to help! When is your birthday?"
    },
    # ... up to max_messages_per_thread
]
```

#### Business Logic

1. **Initialization**:
   ```python
   def __init__(self, redis_url: str, ttl_seconds: int, max_messages_per_thread: int):
       self.redis_url = redis_url
       self.ttl_seconds = ttl_seconds
       self.max_messages_per_thread = max_messages_per_thread
       self.redis_client = redis.from_url(redis_url)
   ```

2. **LangChain Integration**:
   ```python
   def _get_history(self, thread_id: str) -> RedisChatMessageHistory:
       """Get LangChain's RedisChatMessageHistory instance."""
       return RedisChatMessageHistory(
           session_id=thread_id,
           url=self.redis_url,
           ttl=self.ttl_seconds  # LangChain handles TTL automatically
       )
   ```

3. **Active Thread Tracking**:
   - Maintain `active_thread:{user_id}` Redis key
   - Value: Most recent thread_id for the user
   - TTL: Same as conversation TTL (30 minutes, sliding window)
   - Updated on every `add_message` call

4. **Thread Auto-Detection** (`get_or_create_thread_for_user`):
   ```python
   # Step 1: Check for active thread
   key = f"active_thread:{user_id}"
   active_thread = redis_client.get(key)

   # Step 2: If found, verify it still has messages
   if active_thread:
       history = self._get_history(active_thread)
       if history.messages:
           return active_thread  # Continue existing conversation

   # Step 3: No active thread, create new one
   new_thread_id = f"{user_id}::conv::{uuid.uuid4().hex[:12]}"
   redis_client.setex(key, ttl_seconds, new_thread_id)
   return new_thread_id
   ```

5. **Message Addition**:
   ```python
   def add_message(self, thread_id: str, role: str, content: str):
       history = self._get_history(thread_id)

       # Add message (LangChain handles serialization)
       if role == "user":
           history.add_user_message(content)
       else:
           history.add_ai_message(content)

       # Trim to max messages
       messages = history.messages
       if len(messages) > self.max_messages_per_thread:
           history.clear()
           for msg in messages[-self.max_messages_per_thread:]:
               if msg.type == "human":
                   history.add_user_message(msg.content)
               else:
                   history.add_ai_message(msg.content)

       # Update active thread tracker
       user_id = thread_id.split("::")[0]
       self.redis_client.setex(
           f"active_thread:{user_id}",
           self.ttl_seconds,
           thread_id
       )
   ```

6. **History Retrieval**:
   ```python
   def get_history(self, thread_id: str) -> List[Dict[str, str]]:
       history = self._get_history(thread_id)
       messages = history.messages

       # Convert LangChain format to simple dict
       return [
           {
               "role": "user" if msg.type == "human" else "assistant",
               "content": msg.content
           }
           for msg in messages
       ]
   ```

7. **Clear History**:
   ```python
   def clear_history(self, thread_id: str):
       history = self._get_history(thread_id)
       history.clear()  # LangChain clears from Redis

       # Clear active thread tracker if this was the active one
       user_id = thread_id.split("::")[0]
       key = f"active_thread:{user_id}"
       current_active = self.redis_client.get(key)
       if current_active and current_active.decode() == thread_id:
           self.redis_client.delete(key)
   ```

#### Redis Keys Created

```
# LangChain message storage (managed by LangChain)
message_store:user123::conv::abc456
  - LangChain's internal format (list of messages)
  - TTL: 30 minutes (sliding window on access)

# Active thread tracker (custom)
active_thread:user123
  - String: "user123::conv::abc456"
  - TTL: 30 minutes (sliding window via setex)
```

#### Error Handling

- **Redis unavailable**: Raise ConnectionError → HTTP 503 (service unavailable)
- **LangChain errors**: Raise exception → HTTP 503 (service unavailable)
- **Invalid role**: Raise ValueError → HTTP 400
- **Empty content**: Raise ValueError → HTTP 400

**Note**: Redis and LangChain are critical dependencies. If either fails, the service cannot function.

#### Testing Requirements

```python
def test_get_or_create_thread_new_user()
def test_get_or_create_thread_existing_active()
def test_get_or_create_thread_expired()
def test_add_message_user()
def test_add_message_assistant()
def test_add_message_trimming()
def test_get_history()
def test_get_history_empty_thread()
def test_clear_history()
def test_active_thread_updates_on_add_message()
```

#### Dependencies

```bash
uv add langchain-community redis
```

---

### Task 1.2: FormStateManager Service

**Priority**: P0 (Critical - Foundation)
**Estimated Time**: 1.5 hours
**File**: `server/src/ez_scheduler/services/form_state_manager.py`

#### Input Specifications

```python
import redis
import json
from typing import Any, Dict, List, Optional

class FormStateManager:
    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = 1800  # 30 minutes
    )

    def get_state(
        self,
        thread_id: str
    ) -> Dict[str, Any]

    def update_state(
        self,
        thread_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]

    def clear_state(
        self,
        thread_id: str
    ) -> None

    def is_complete(
        self,
        state: Dict[str, Any]
    ) -> bool
```

**Input Parameters:**
- `redis_url`: Redis connection URL
- `ttl_seconds`: Time-to-live in seconds (default: 1800 = 30 minutes)
- `thread_id`: Conversation thread identifier
- `updates`: Dictionary of form fields to update
- `state`: Form state dictionary to validate

#### Output Specifications

**`get_state()` returns:**
```python
{
    "title": "Sarah's Birthday Party",
    "event_date": "2024-12-15",
    "start_time": "18:00",
    "end_time": "22:00",
    "location": "Central Park",
    "description": "Join us for...",
    "custom_fields": [
        {
            "field_name": "guest_count",
            "field_type": "number",
            "label": "Number of guests",
            "is_required": True
        }
    ],
    "button_config": {
        "button_type": "rsvp_yes_no",
        "primary_button_text": "RSVP Yes",
        "secondary_button_text": "RSVP No"
    },
    "timeslot_schedule": None,
    "is_complete": False,
    "form_id": None
}
```

**`update_state()` returns:**
- Updated complete state dictionary after merge

**`is_complete()` returns:**
- Boolean indicating if form has all required fields

#### Business Logic

1. **Redis Key Pattern**:
   ```python
   def _state_key(self, thread_id: str) -> str:
       return f"form_state:{thread_id}"
   ```

2. **Get State**:
   ```python
   def get_state(self, thread_id: str) -> Dict[str, Any]:
       key = self._state_key(thread_id)
       state_json = self.redis_client.get(key)

       if not state_json:
           return self._empty_state_template()

       try:
           return json.loads(state_json)
       except json.JSONDecodeError:
           logger.error(f"Corrupted state for {thread_id}")
           return self._empty_state_template()
   ```

3. **Update State** (with sliding TTL):
   ```python
   def update_state(self, thread_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
       # Get current
       current_state = self.get_state(thread_id)

       # Merge
       merged_state = self._merge_state(current_state, updates)

       # Update completeness
       merged_state["is_complete"] = self.is_complete(merged_state)

       # Save with TTL (sliding window)
       key = self._state_key(thread_id)
       self.redis_client.setex(
           key,
           self.ttl_seconds,
           json.dumps(merged_state)
       )

       return merged_state
   ```

4. **Merge Logic**:
   ```python
   def _merge_state(self, current: Dict, updates: Dict) -> Dict:
       merged = current.copy()

       for key, value in updates.items():
           if key == "custom_fields" and isinstance(value, list):
               # Merge custom fields by field_name
               merged[key] = self._merge_custom_fields(
                   merged.get("custom_fields", []),
                   value
               )
           elif key == "button_config" and isinstance(value, dict):
               # Merge button config
               current_config = merged.get("button_config", {})
               merged[key] = {**current_config, **value}
           else:
               # Simple overwrite
               merged[key] = value

       return merged
   ```

5. **Completeness Validation**:
   ```python
   def is_complete(self, state: Dict[str, Any]) -> bool:
       required = ["title", "event_date", "location", "description"]

       for field in required:
           value = state.get(field)
           if not value or (isinstance(value, str) and not value.strip()):
               return False

       button_config = state.get("button_config", {})
       if not button_config.get("button_type") or not button_config.get("primary_button_text"):
           return False

       return True
   ```

6. **Empty State Template**:
   ```python
   def _empty_state_template(self) -> Dict[str, Any]:
       return {
           "title": None,
           "event_date": None,
           "start_time": None,
           "end_time": None,
           "location": None,
           "description": None,
           "custom_fields": [],
           "button_config": None,
           "timeslot_schedule": None,
           "is_complete": False,
           "form_id": None
       }
   ```

#### Redis Keys Created

```
# Form state storage
form_state:user123::conv::abc456
  - JSON string of form state
  - TTL: 30 minutes (sliding window via setex)
```

#### Error Handling

- **Redis unavailable**: Raise ConnectionError → HTTP 503 (service unavailable)
- **Corrupted JSON in Redis**: Log error, return empty state template (recoverable)
- **Invalid updates format**: Raise ValueError → HTTP 400

**Note**: Redis is a critical dependency. If Redis fails, the service cannot function.

#### Testing Requirements

```python
def test_get_state_new_thread()
def test_get_state_existing()
def test_update_state_simple_fields()
def test_update_state_custom_fields_merge()
def test_update_state_button_config_merge()
def test_is_complete_missing_fields()
def test_is_complete_all_present()
def test_clear_state()
def test_ttl_sliding_window()
```

#### Dependencies

```bash
uv add redis
```

---

## Phase 2: Conversation Handler (4-5 hours)

### Task 2.1: FormConversationHandler

**Priority**: P0 (Critical - Core Logic)
**Estimated Time**: 4 hours
**File**: `server/src/ez_scheduler/handlers/form_conversation_handler.py`

#### Input Specifications

```python
from ez_scheduler.auth.dependencies import User
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.services.conversation_manager import ConversationManager
from ez_scheduler.services.form_state_manager import FormStateManager

class FormConversationHandler:
    def __init__(
        self,
        llm_client: LLMClient,
        conversation_manager: ConversationManager,
        form_state_manager: FormStateManager
    )

    async def process_message(
        self,
        user: User,
        thread_id: str,
        user_message: str
    ) -> ConversationHandlerResponse
```

**Input Parameters:**
- `user`: User object with `user_id` and `claims`
- `thread_id`: Conversation identifier (from ConversationManager)
- `user_message`: Latest user message

#### Output Specifications

```python
@dataclass
class ConversationHandlerResponse:
    response_text: str  # Natural language response
    action: Literal["continue", "create_form", "publish_form"]
    form_state: Dict[str, Any]  # Current complete form state
    is_complete: bool  # Whether form is ready to create

# Example
ConversationHandlerResponse(
    response_text="Perfect! I have all the details. Ready to create the form?",
    action="continue",
    form_state={...},
    is_complete=True
)
```

#### Business Logic

1. **Context Building**:
   ```python
   # Get conversation history
   history = conversation_manager.get_history(thread_id)

   # Get current form state
   current_state = form_state_manager.get_state(thread_id)
   ```

2. **LLM Invocation with History**:
   ```python
   # Build messages array (history + new message)
   messages = history + [{"role": "user", "content": user_message}]

   # Call LLM with conversation-aware prompt
   response = await llm_client.process_instruction(
       messages=messages,
       system=FORM_BUILDER_CONVERSATION_PROMPT,
       max_tokens=2000
   )
   ```

3. **Parse and Merge**:
   ```python
   # Parse JSON from LLM
   llm_response = json.loads(response)

   # Extract data
   response_text = llm_response["response_text"]
   action = llm_response["action"]
   extracted_data = llm_response["extracted_data"]

   # Merge with current state
   updated_state = form_state_manager.update_state(thread_id, extracted_data)
   ```

4. **Update History**:
   ```python
   # Add both messages to history
   conversation_manager.add_message(thread_id, "user", user_message)
   conversation_manager.add_message(thread_id, "assistant", response_text)
   ```

5. **Return Response**:
   ```python
   return ConversationHandlerResponse(
       response_text=response_text,
       action=action,
       form_state=updated_state,
       is_complete=updated_state["is_complete"]
   )
   ```

#### Error Handling

- **LLM timeout/error**: Retry once, then return user-friendly error message
- **Invalid JSON from LLM**: Log error, return "Please rephrase your request"
- **Corrupted state**: Log error, reset to empty state, start fresh conversation
- **Empty user message**: Raise ValueError → HTTP 400

#### Testing Requirements

```python
def test_process_message_new_conversation()
def test_process_message_with_history()
def test_process_message_state_merge()
def test_process_message_llm_error()
def test_complete_conversation_flow()
```

---

### Task 2.2: Update System Prompt

**Priority**: P0 (Critical - LLM Behavior)
**Estimated Time**: 1 hour
**File**: `server/src/ez_scheduler/system_prompts.py`

#### Changes Required

Add new constant `FORM_BUILDER_CONVERSATION_PROMPT` based on existing `FORM_BUILDER_PROMPT` with these additions:

1. **CONVERSATION CONTEXT AWARENESS** section
2. **INCREMENTAL STATE BUILDING** section
3. **SMART QUESTION ASKING** section
4. **Multi-turn conversation examples**

Key instructions to add:
- Don't ask for information already in history
- Build upon partial state incrementally
- Reference previous messages naturally
- Make reasonable inferences from context

---

## Phase 3: Unified Tool Implementation (5-6 hours)

### Task 3.1: create_or_update_form MCP Tool

**Priority**: P0 (Critical - User-Facing)
**Estimated Time**: 4 hours
**File**: `server/src/ez_scheduler/tools/create_or_update_form.py`

#### MCP Tool Signature

```python
@mcp.tool()
async def create_or_update_form(
    user_id: str,
    message: str,
    action: Optional[str] = None  # "create" | "publish" | None
) -> str:
    """
    Create or update a signup form through natural conversation.
    Server automatically manages conversation context - no thread_id needed!
    """
```

#### Business Logic

1. **Auto-detect thread** (transparent to client):
   ```python
   thread_id = conversation_manager.get_or_create_thread_for_user(user_id)
   ```

2. **Process message**:
   ```python
   response = await handler.process_message(user, thread_id, message)
   ```

3. **Handle actions**:
   - `continue`: Return response text
   - `create_form`:
     - Check if `form_id` exists in `response.form_state`
     - If exists → **UPDATE** existing draft
     - If not exists → **CREATE** new draft, store `form_id` in state
   - `publish_form`: Publish draft, clear conversation state

#### Key Implementation Details

**Store form_id after creation:**
```python
# After creating new draft
form_state_manager.update_state(thread_id, {"form_id": str(new_form.id)})
```

**Check for existing draft before creating:**
```python
form_id = response.form_state.get("form_id")
if form_id:
    # UPDATE existing draft (form already in DB)
    updated_form = await _update_existing_draft(...)
else:
    # CREATE new draft
    new_form = await _create_draft_form(...)
```

**Draft remains DRAFT until published:**
- Multiple updates allowed to same draft
- Only PUBLISHED forms are immutable
- Draft can be updated via conversation until user says "publish"

**Clear state after publish:**
```python
# After successful publish
conversation_manager.clear_history(thread_id)
form_state_manager.clear_state(thread_id)
# Next message starts fresh
```

---

### Task 3.2: /gpt/create-or-update-form REST Endpoint

**Priority**: P0 (Critical - GPT Integration)
**Estimated Time**: 2 hours
**File**: `server/src/ez_scheduler/routers/gpt_actions.py`

#### Request/Response

```python
# Request (matches existing /gpt/create-form format)
class GPTFormRequest(BaseModel):
    description: str = Field(
        ...,
        description="Natural language description of the form or conversation message"
    )

# Example request body
{
  "description": "Create a form for my birthday"
}

# Response (matches existing GPTResponse format)
{
  "response": "I'd love to help! When is your birthday?"
}
```

#### Implementation

```python
@router.post(
    "/create-or-update-form",
    summary="Create or Update Signup Form (Conversational)",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": False},
)
async def gpt_create_or_update_form(
    request: GPTFormRequest,  # Reuse existing model
    user: User = Depends(get_current_user),
    db_session=Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """
    Create or update a signup form using natural language.
    Server automatically manages conversation context.
    """
    # Initialize services
    conversation_manager = ConversationManager(
        redis_url=config["redis_url"],
        ttl_seconds=1800
    )
    form_state_manager = FormStateManager(
        redis_url=config["redis_url"],
        ttl_seconds=1800
    )

    # Auto-detect thread (transparent to client)
    thread_id = conversation_manager.get_or_create_thread_for_user(user.user_id)

    # Call handler
    response_text = await create_or_update_form_handler(
        user=user,
        message=request.description,  # Use 'description' field
        llm_client=llm_client,
        conversation_manager=conversation_manager,
        form_state_manager=form_state_manager,
        # ... other dependencies
    )

    return GPTResponse(response=response_text)
```

#### Business Logic

1. Reuse existing `GPTFormRequest` model (with `description` field)
2. Reuse existing `GPTResponse` model (with `response` field)
3. Auto-detect thread transparently
4. Return simple response (consistent with current `/gpt/create-form`)
5. All conversation state management happens server-side

**Note**: Keep API interface identical to existing `/gpt/create-form` for consistency. The only difference is server-side conversation management.

---

## Phase 4: Migration & Deprecation (2-3 hours)

### Task 4.1: Update MCP Tool Registration

Update `server/src/ez_scheduler/routers/mcp_server.py`:
- Register `create_or_update_form`
- Mark `create_form` and `update_form` as `[DEPRECATED]`

### Task 4.2: Migration Documentation

Create `docs/migration_to_conversational_flow.md` with examples

---

## Phase 5: Testing & Validation (4-5 hours)

### Task 5.1: Unit Tests for ConversationManager
### Task 5.2: Unit Tests for FormStateManager
### Task 5.3: Integration Tests for create_or_update_form
### Task 5.4: End-to-End Conversation Tests

---

## Summary

**Total Estimated Time**: 17-22 hours

**New Files** (6):
1. `server/src/ez_scheduler/services/conversation_manager.py` (LangChain wrapper)
2. `server/src/ez_scheduler/services/form_state_manager.py` (Redis + JSON)
3. `server/src/ez_scheduler/handlers/form_conversation_handler.py`
4. `server/src/ez_scheduler/tools/create_or_update_form.py`
5. Unit tests (4 files)

**Modified Files** (3):
1. `server/src/ez_scheduler/system_prompts.py` (add conversation prompt)
2. `server/src/ez_scheduler/routers/mcp_server.py` (new tool)
3. `server/src/ez_scheduler/routers/gpt_actions.py` (new endpoint)

**Dependencies**:
```bash
uv add langchain-community redis
```

**Config**:
```python
# Add to config
"redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0")
```

---

**Document Version**: 2.0 (Updated with LangChain + Redis)
**Last Updated**: 2025-10-06
**Status**: Ready for Implementation
