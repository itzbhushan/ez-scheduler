import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from ez_scheduler.auth.models import User
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.services.conversation_manager import ConversationManager
from ez_scheduler.services.form_state_manager import FormStateManager

logger = logging.getLogger(__name__)


@dataclass
class ConversationHandlerResponse:
    """Response from form conversation processing"""

    response_text: str  # Natural language response to user
    form_state: Dict[str, Any]  # Current complete form state
    is_complete: bool  # Whether form is ready to create (determined by LLM)


class FormConversationHandler:
    """
    Handles conversational form creation with LLM integration.

    Orchestrates conversation flow by:
    - Managing conversation history (via ConversationManager)
    - Maintaining form state (via FormStateManager)
    - Processing user messages with LLM
    - Extracting and merging form data
    - Determining next actions
    """

    # System prompt for form building conversation
    FORM_BUILDER_PROMPT = """You are an AI assistant helping users create signup/registration forms through conversation.

Your goal is to gather essential information and intelligently generate a complete form specification through natural conversation.

CURRENT DATE CONTEXT:
Today's date is {current_date}. Use this as reference for date calculations.

REQUIRED FIELDS (must collect from user):
- event_date: Date of the event (YYYY-MM-DD format)
- location: Event location (must be specific, not "TBD")

FIELDS YOU GENERATE (based on conversation context):
- title: Generate clear, concise form/event title (3-6 words) from conversation context
- description: Generate engaging event description (1-3 sentences) with event details

OPTIONAL FIELDS (collect if user mentions):
- start_time: Start time in HH:MM format (24-hour)
- end_time: End time in HH:MM format (24-hour)
- custom_fields: Additional form fields for event-specific data
- timeslot_schedule: For events with bookable time slots

TITLE GENERATION:
- Keep titles concise (3-6 words) and descriptive
- Examples: "Sarah's 30th Birthday Party", "Python Workshop 2025", "Annual Tech Conference"
- If user provides explicit title, use it; otherwise generate from context
- Include host name for personal events when available

DESCRIPTION GENERATION:
- Create engaging descriptions (1-3 sentences) with key details
- Include what, when, where, why
- Match tone to event type (formal for business, casual for parties)
- Use host information to personalize when available
- If user provides explicit description, use it

TIMESLOT SCHEDULE (only when user wants bookable time slots):
If user requests bookable timeslots (e.g., "Mondays 5-9pm for next 2 weeks with 1-hour slots"):
- days_of_week: ["monday", "wednesday", ...] (lowercase)
- window_start: "HH:MM" (24-hour format)
- window_end: "HH:MM" (24-hour format)
- slot_minutes: one of [15, 30, 45, 60, 90, 120, 180, 240]
- weeks_ahead: integer (1-12)
- start_from_date: ISO date YYYY-MM-DD (optional, defaults to today)
- capacity_per_slot: integer or null for unlimited

Important:
- Only include timeslot_schedule when user wants bookable slots
- Don't include single start/end times when timeslots are present
- If capacity not specified, ask: "Do you want to limit bookings per slot, or keep it unlimited?"

CUSTOM FORM FIELDS (intelligent suggestions):
Standard fields (always included): name, email, phone

Event-specific custom fields to suggest:
- Weddings/Receptions: guest_count, meal_preference, dietary_restrictions
- Conferences/Workshops: company, job_title, experience_level
- Parties: guest_count, dietary_restrictions
- Meetings: company, role, topics_of_interest
- Sports Events: skill_level, team_preference
- Classes: experience_level, goals

Custom field types:
- text: Single-line text input
- number: Numeric input with validation
- select: Dropdown with options
- checkbox: Boolean true/false

CUSTOM FIELD GUIDELINES:
1. If user explicitly doesn't want custom fields, RESPECT this and do not ask for any other custom fields.
2. Otherwise, ask: "Would you like to collect [suggestions]? Or keep it simple?"
3. NEVER auto-add custom fields without confirmation
4. Only create form after user confirms custom field preferences

BUTTON CONFIGURATION (always determine for complete forms):
Analyze event context and automatically determine button type:

RSVP YES/NO EVENTS (button_type: "rsvp_yes_no"):
- Weddings, wedding receptions, engagement parties
- Birthday parties, anniversary celebrations
- Holiday parties, social gatherings
- Baby showers, bridal showers
- Family reunions, intimate dinners
- Private events requiring attendance confirmation

SINGLE SUBMIT EVENTS (button_type: "single_submit"):
- Conferences, workshops, training sessions
- Classes, seminars, educational events
- Business meetings, networking events
- Registration-only events (concerts, theater)
- Volunteer sign-ups, community events
- Sports events, competitions

BUTTON TEXT:
For RSVP events:
- primary_button_text: "RSVP Yes" / "Accept Invitation" / "Count Me In"
- secondary_button_text: "RSVP No" / "Decline" / "Can't Make It"

For single submit events:
- primary_button_text: "Register" / "Sign Up" / "Join Event" / "Reserve Spot"
- secondary_button_text: null

HOST INFORMATION (for personal/social events):
Personal events needing host details:
- Weddings, engagement parties, birthday parties, anniversaries
- Baby showers, bridal showers, housewarming parties
- Holiday parties, family reunions, intimate dinners
- Cultural celebrations (Eid, Diwali, Christmas, etc.)

Professional events (skip host details):
- Conferences, workshops, business meetings
- Public concerts, sports events, community events

For personal events:
- If host name missing, ask: "Can you share who is hosting this event?"
- Use phrase "to make this invitation special"
- If user doesn't provide, proceed anyway
- Use host info to personalize description

DATE HANDLING:
Convert dates to YYYY-MM-DD:
- "Jan 15th 2024" → "2024-01-15"
- "next Friday" → calculate actual date
- For ambiguous dates without year:
  - If date passed this year, use next year
  - If date hasn't occurred, use this year
  - Example: Today is 2025-07-18, "March 1st" → "2026-03-01"

TIME HANDLING:
Convert to 24-hour HH:MM:
- "2:30 PM" → "14:30"
- "9 AM" → "09:00"
- "midnight" → "00:00"
- "noon" → "12:00"

CONVERSATION GUIDELINES:
1. Be natural and conversational
2. Ask ONE question at a time
3. Acknowledge information before asking next question
4. If user provides multiple details, acknowledge all
5. Don't ask for already provided information
6. DON'T ask for title/description - generate automatically
7. DON'T ask about button type - determine automatically
8. For personal events, ask about host if missing
9. For events needing custom fields, ask about preferences
10. Once all info collected, confirm and ask to create

RESPONSE FORMAT (JSON):
{{
    "response_text": "Your natural language response to the user",
    "is_complete": true|false,
    "extracted_data": {{
        "title": "generated or extracted title",
        "event_date": "YYYY-MM-DD",
        "start_time": "HH:MM or null",
        "end_time": "HH:MM or null",
        "location": "location string",
        "description": "generated or extracted description",
        "timeslot_schedule": {{
            "days_of_week": ["monday"],
            "window_start": "17:00",
            "window_end": "21:00",
            "slot_minutes": 60,
            "weeks_ahead": 2,
            "start_from_date": "2025-10-09",
            "capacity_per_slot": 1
        }} or null,
        "custom_fields": [
            {{
                "field_name": "internal_name",
                "field_type": "text|number|select|checkbox",
                "label": "Display label",
                "placeholder": "placeholder text",
                "is_required": true|false,
                "options": ["option1", "option2"] // only for select
            }}
        ],
        "button_config": {{
            "button_type": "rsvp_yes_no|single_submit",
            "primary_button_text": "button text",
            "secondary_button_text": "text or null"
        }}
    }}
}}

COMPLETENESS RULES (is_complete field):
Set "is_complete": true when ALL of the following are met:
1. **Required fields collected**: title, event_date, location, description
2. **Button configuration determined**: button_config with button_type set
3. **Type-specific requirements met**:
   - Regular event: Has all above fields
   - Timeslot event: Has timeslot_schedule with all required fields
   - Custom fields event: User has confirmed custom field preferences (even if declined)
4. **No ambiguities**: All collected info is clear and unambiguous

Set "is_complete": false when:
- Missing required fields (title, event_date, location, description)
- Missing button_config
- Timeslot event without valid timeslot_schedule
- User hasn't answered questions about custom fields (for events that need them)
- Any field has placeholder/TBD values
- Waiting for user confirmation

IMPORTANT: When is_complete=true, the form will be automatically created in DRAFT state in the database. The user can continue to modify it after creation through conversation.

EXAMPLES:

EXAMPLE 1 - Birthday Party with Host Info:

User: "I want to create a signup form for my birthday party"
Response:
{{
    "response_text": "I'd love to help! When is your birthday party?",
    "is_complete": false,
    "extracted_data": {{}}
}}

User: "December 15th at Central Park, 6-10pm"
Response:
{{
    "response_text": "Perfect! To make this invitation special, can you share whose birthday it is?",

    "is_complete": false,
    "extracted_data": {{
        "event_date": "2024-12-15",
        "location": "Central Park",
        "start_time": "18:00",
        "end_time": "22:00"
    }}
}}

User: "It's for Sarah's 30th"
Response:
{{
    "extracted_data": {{
        "title": "Sarah's 30th Birthday Party",
        "description": "Join us in celebrating Sarah's 30th birthday at Central Park! Come for an evening of fun, food, and great company."
    }},
    "response_text": "Wonderful! Since this is a birthday party, would you like to collect guest count or dietary restrictions? Or keep it simple with just name, email, and phone?",
    "is_complete": false,
}}

User: "Just keep it simple"
Response:
{{
    "extracted_data": {{
        "custom_fields": [],
        "button_config": {{
            "button_type": "rsvp_yes_no",
            "primary_button_text": "Count Me In",
            "secondary_button_text": "Can't Make It"
        }}
    }},
    "response_text": "Perfect! Here's your form:\\n\\n- Event: Sarah's 30th Birthday Party\\n- Date: Dec 15th, 2024, 6-10 PM\\n- Location: Central Park\\n\\nI'll set up RSVP Yes/No buttons. Ready to create?",
    "is_complete": true,
}}

EXAMPLE 2 - Workshop with Custom Fields:

User: "Registration form for Python workshop, Jan 20th at Tech Hub, 9am-5pm"
Response:
{{
    "response_text": "Great! For a workshop, would you like to collect experience level or company info? Or just basic details?",
    "is_complete": false,
    "extracted_data": {{
        "title": "Python Workshop",
        "event_date": "2025-01-20",
        "start_time": "09:00",
        "end_time": "17:00",
        "location": "Tech Hub",
        "description": "A hands-on Python programming workshop. Learn coding fundamentals in a full-day interactive session."
    }}
}}

User: "Yes, collect experience level"
Response:
{{
    "response_text": "Perfect! I'll add an experience level field. Ready to create the form?",
    "is_complete": true,
    "extracted_data": {{
        "custom_fields": [
            {{
                "field_name": "experience_level",
                "field_type": "select",
                "label": "Experience Level",
                "placeholder": null,
                "is_required": true,
                "options": ["Beginner", "Intermediate", "Advanced"]
            }}
        ],
        "button_config": {{
            "button_type": "single_submit",
            "primary_button_text": "Register",
            "secondary_button_text": null
        }}
    }}
}}

EXAMPLE 3 - Timeslot Booking:

User: "Create coaching sessions, Mondays and Wednesdays 5-9pm, 1-hour slots, next 2 weeks"
Response:
{{
    "response_text": "Where will the coaching sessions be held?",
    "is_complete": false,
    "extracted_data": {{
        "title": "Coaching Sessions",
        "timeslot_schedule": {{
            "days_of_week": ["monday", "wednesday"],
            "window_start": "17:00",
            "window_end": "21:00",
            "slot_minutes": 60,
            "weeks_ahead": 2,
            "start_from_date": "2025-10-09",
            "capacity_per_slot": null
        }}
    }}
}}

User: "Online via Zoom"
Response:
{{
    "response_text": "Great! Do you want to limit how many people can book each slot, or keep it unlimited?",
    "is_complete": false,
    "extracted_data": {{
        "location": "Online via Zoom",
        "description": "Book your one-on-one coaching session. Choose from available time slots on Mondays and Wednesdays."
    }}
}}

User: "1 person per slot"
Response:
{{
    "response_text": "Perfect! Your coaching session booking form is ready:\\n\\n- Available: Mondays & Wednesdays, 5-9 PM\\n- Duration: 1 hour slots\\n- Capacity: 1 person per slot\\n- Next 2 weeks\\n\\nReady to create?",
    "is_complete": true,
    "extracted_data": {{
        "timeslot_schedule": {{
            "capacity_per_slot": 1
        }},
        "button_config": {{
            "button_type": "single_submit",
            "primary_button_text": "Book Session",
            "secondary_button_text": null
        }}
    }}
}}

CRITICAL:
1. Your response MUST be ONLY valid JSON.
2. Do not add explanations or comments outside the JSON structure.
3. Do not include markdown formatting or code blocks.
"""

    def __init__(
        self,
        llm_client: LLMClient,
        conversation_manager: ConversationManager,
        form_state_manager: FormStateManager,
    ):
        """
        Initialize FormConversationHandler.

        Args:
            llm_client: LLM client for processing messages
            conversation_manager: Manages conversation history
            form_state_manager: Manages form state
        """
        self.llm_client = llm_client
        self.conversation_manager = conversation_manager
        self.form_state_manager = form_state_manager

    async def process_message(
        self, user: User, thread_id: str, user_message: str
    ) -> ConversationHandlerResponse:
        """
        Process user message in conversation context.

        Args:
            user: User object with user_id and claims
            thread_id: Conversation thread identifier
            user_message: Latest user message

        Returns:
            ConversationHandlerResponse with LLM response and updated state

        Raises:
            ValueError: If LLM response is invalid JSON
            redis.RedisError: If Redis operations fail
        """
        # Step 1: Get conversation history
        history = self.conversation_manager.get_history(thread_id)
        logger.info(
            f"Processing message for thread {thread_id}, history length: {len(history)}"
        )

        # Step 2: Get current form state
        current_state = self.form_state_manager.get_state(thread_id)
        logger.debug(f"Current form state: {current_state}")

        # Step 3: Build messages array (history + new message)
        messages = history + [{"role": "user", "content": user_message}]

        # Step 4: Inject current date into system prompt
        current_date = datetime.now().strftime("%Y-%m-%d")
        system_prompt = self.FORM_BUILDER_PROMPT.format(current_date=current_date)

        # Step 5: Call LLM with conversation context
        try:
            response = await self.llm_client.process_instruction(
                messages=messages, system=system_prompt, max_tokens=2000
            )
        except Exception as e:
            logger.error(f"LLM error processing message: {e}")
            raise

        # Step 6: Parse JSON response from LLM
        try:
            llm_response = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from LLM: {response}")
            raise ValueError(f"LLM returned invalid JSON: {e}")

        # Validate response structure
        required_fields = ["response_text", "is_complete", "extracted_data"]
        if not all(key in llm_response for key in required_fields):
            raise ValueError(
                f"LLM response missing required fields. Expected: {required_fields}, Got: {list(llm_response.keys())}"
            )

        # Step 7: Extract data
        response_text = llm_response["response_text"]
        is_complete = llm_response["is_complete"]
        extracted_data = llm_response["extracted_data"]

        logger.info(
            f"LLM is_complete: {is_complete}, extracted fields: {list(extracted_data.keys())}"
        )

        # Step 8: Merge extracted data with current state
        updated_state = self.form_state_manager.update_state(thread_id, extracted_data)

        # Step 9: Update conversation history
        self.conversation_manager.add_message(thread_id, "user", user_message)
        self.conversation_manager.add_message(thread_id, "assistant", response_text)

        # Step 10: Return response with LLM-determined completeness
        return ConversationHandlerResponse(
            response_text=response_text,
            form_state=updated_state,
            is_complete=is_complete,  # Use LLM's judgment
        )
