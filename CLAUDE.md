# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server that accepts user instructions and generates signup/registration forms. The server engages in conversational form building, provides live preview capabilities, and includes analytics for form management.

## Technology Stack

- **Backend:** Python 3.11+ with MCP framework
- **Web Framework:** FastAPI (async)
- **Database:** PostgreSQL with SQLAlchemy ORM
- **Frontend:** Server-side rendered HTML with Alpine.js and TailwindCSS
- **Storage:** Redis for session management and caching
- **Templates:** Jinja2 for form generation

## Development Commands

```bash
# Start local development environment
docker-compose up -d

# Run database migrations
alembic upgrade head

# Start MCP server in development mode
uv run python run_server.py

# Run tests (ALWAYS use uv as package manager)
uv run pytest tests/

# Run linting and formatting
black .
flake8 .
mypy .

# Generate new migration
alembic revision --autogenerate -m "description"

# Install dependencies (ALWAYS use uv as package manager)
uv add package-name
uv add --dev package-name  # for development dependencies
```

## Architecture Overview

The system consists of:
1. **MCP Server**: Handles client communication via stdio transport
2. **Conversation Engine**: Manages back-and-forth form building conversations
3. **Form Generator**: Creates HTML forms from conversation context
4. **Registration System**: Handles public form submissions
5. **Analytics Engine**: Provides registration data and insights

## Critical Development Guidelines

### Coding Standards

**Import Organization**: All imports MUST be placed at the top of the file, never within functions or methods.

- **DO**: Place all imports at the top of the file in the following order:
- **DON'T**: Import modules within functions, methods, or conditional blocks
- **DO**: Group imports logically and separate groups with blank lines
- **DO**: Use absolute imports for all local modules (NEVER use relative imports)
- **DON'T**: Use relative imports like `from ..models import User` or `from .config import test_config`

**Python Package Management**: ALWAYS use `uv` as the Python package manager for all operations.

- **DO**: Use `uv run pytest` for running tests
- **DO**: Use `uv add package-name` for installing dependencies
- **DO**: Use `uv run python script.py` for running Python scripts
- **DON'T**: Use `pip`, `poetry`, or other package managers in this project

#### Example Implementation
```python
# CORRECT: All imports at top of file with absolute imports
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select
from fastapi import HTTPException

from ez_scheduler.models.user import User  # CORRECT: Absolute import

class UserService:
    def __init__(self, db_session: Session):
        self.db = db_session
```

```python
# INCORRECT: Relative imports and imports within functions
class UserService:
    def create_user(self, email: str):
        from ..models.user import User  # Wrong! Relative import
        from .config import test_config  # Wrong! Relative import
        import uuid  # Wrong! Import within function
        # ... rest of method
```

### LLM-First Instruction Processing
**NEVER manually parse user instructions in code.** Always use an LLM to understand user instructions and return structured responses.

- **DO**: Use LLM API calls to process natural language instructions
- **DON'T**: Write regex patterns or manual text parsing for user input
- **DO**: Design structured JSON schemas for LLM responses
- **DON'T**: Rely on keyword matching or string manipulation

### LLM Integration Pattern
1. Send user instructions to LLM with structured prompt
2. Request JSON response with specific schema
3. Validate and use the structured response
4. Handle LLM errors gracefully with fallback responses

### Example Implementation
```python
# CORRECT: LLM-based processing
response = await llm_client.process_instruction(
    instruction=user_message,
    schema=FormExtractionSchema
)

# INCORRECT: Manual parsing
if "date" in user_message.lower():
    # Manual extraction logic
```

## Data Models

- **Conversations**: Store user interaction sessions
- **Messages**: Individual conversation messages with metadata
- **SignupForms**: Form definitions with event details (date, location required)
- **FormFields**: Dynamic form field configurations
- **Registrations**: User submissions with name, email, phone (required)

## Core MCP Tools Status

### ✅ Completed Tools (MVP READY)
- `create_form` - Initiates form creation conversation using LLM
- `get_form_analytics` - Queries registration data using natural language

### ⏳ Next Priority Tools
- `list_forms` - Shows all forms for the user
- `modify_form` - Updates existing form properties
- `activate_form` - Enables/disables form submissions

## Development Milestones

### ✅ Milestone 1: Core MCP Server Foundation (COMPLETED)
- [x] Plan created and documented
- [x] Basic MCP server setup with stdio transport
- [x] Database schema and migrations (Users, SignupForms, Registrations)
- [x] Database indexes for performance
- [x] User management system

### ✅ Milestone 2: Conversational Form Builder (COMPLETED)
- [x] Intelligent conversation flow for gathering requirements
- [x] Form validation logic (ensures date and location)
- [x] LLM-based form generation from conversation context
- [x] Form storage and retrieval system

### ✅ Milestone 3: Registration System (COMPLETED)
- [x] Public registration form rendering with templates
- [x] Registration data collection and validation
- [x] Registration confirmation messages
- [x] Registration data storage with indexes

### ✅ Milestone 4: Analytics & Reporting (COMPLETED)
- [x] Analytics query system via MCP using natural language
- [x] SQL generation for registration queries
- [x] Registration count and form analytics

### 🚧 Next Phase: Form Management & Enhancement
- [ ] `list_forms` MCP tool implementation
- [ ] Form modification capabilities via MCP
- [ ] Form activation/deactivation controls
- [ ] Bulk operations for forms

### Milestone 6: Multi-Environment Deployment (2-3 days)
- [ ] Docker containerization
- [ ] Environment-specific configurations
- [ ] CI/CD pipeline setup
- [ ] Monitoring and logging

## Environment Configuration

### Local Development
- Docker Compose setup with PostgreSQL, Redis, and app containers
- Volume mounts for hot-reloading
- SQLite option for lightweight development

### Staging Environment
- Cloud-hosted PostgreSQL and Redis
- Container registry for image management
- Subdomain deployment
- Automated deployment from main branch

### Production Environment
- High-availability PostgreSQL with read replicas
- Redis cluster for session management
- CDN for static assets
- Load balancer with SSL termination
- Monitoring with health checks and alerts

## Testing Strategy

Each milestone includes:
- Unit tests for core functionality
- Integration tests for MCP protocol compliance
- End-to-end tests with Claude desktop client
- Performance and load testing
- Cross-browser compatibility testing

## Form Requirements

All generated forms must include:
- Event date (required)
- Event location (required)
- User name field (required)
- User email field (required)
- User phone number field (required)

## Analytics Capabilities

The system supports queries like:
- "How many registrations does event X have?"
- "What is the deadline to register for event Z?"
- "List all pending registrations"
- "Export registration data for event Y"

## Success Metrics

- **✅ MVP ACHIEVED**: Core functionality completed (form creation, registration, analytics)
- **Next Target**: Enhanced form management and deployment ready
- **Performance**: <200ms response time for MCP calls, <2s form loading
- **Scalability**: Handle 100+ concurrent form submissions

## 🎯 MVP STATUS: COMPLETE

**Core Features Working:**
- ✅ Conversational form creation via MCP
- ✅ Public form registration with templates
- ✅ Registration confirmation system
- ✅ Natural language analytics queries
- ✅ Database with proper indexing
- ✅ SQL generation for complex queries

## 🚀 What to Work on Next

### Priority 1: Complete Form Management Tools (2-3 days)
1. **`list_forms` MCP tool** - Show all user's forms with filtering options
2. **`modify_form` MCP tool** - Update form properties (title, date, location, etc.)
3. **`activate_form`/`deactivate_form` tools** - Control form availability

### Priority 2: User Experience Enhancements (3-4 days)
1. **Form Templates** - Pre-built templates for common events (meetings, parties, workshops)
2. **Bulk Operations** - Archive multiple forms, export multiple registrations
3. **Form Cloning** - Duplicate existing forms with modifications
4. **Registration Limits** - Set maximum number of registrations per form

### Priority 3: Production Readiness (4-5 days)
1. **Docker Containerization** - Production-ready containers
2. **Environment Configuration** - Staging/production configs
3. **Monitoring & Logging** - Health checks, metrics, error tracking
4. **Email Integration** - SMTP setup for registration confirmations
5. **Rate Limiting** - Protect against abuse

### Priority 4: Advanced Features (5-7 days)
1. **Form Customization** - Custom fields, styling options
2. **Registration Export** - CSV/Excel export functionality
3. **Waitlist Support** - Queue system when forms are full
4. **Multi-language Support** - I18n for forms and confirmations

**Recommended Next Step:** Start with `list_forms` tool implementation to complete the core MCP functionality suite.

---

*This file will be updated as development progresses and tools are completed.*
