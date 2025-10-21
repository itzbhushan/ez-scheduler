# EZ Scheduler

An MCP server that generates signup forms for various events.
EZ-Scheduler is an MCP server and custom GPT application that makes it easy to generate signup forms for any event. Organizers can quickly create events, while participants enjoy a seamless registration experience. Try the GPT-powered signup assistant [here](https://chatgpt.com/g/g-68c1f6c26dd8819187e04ad7d9fe50c9-signup-pro).

## High-Level Architecture

EZ-Scheduler leverages a modern, scalable architecture:

* **Server Bootstrapping**: Uses Python Fast MCP to initialize and manage the server environment.
* **Conversational Intelligence**: Leverages LangChain and Redis to handle and store multi-turn conversation context.
* **AI Processing**: Utilizes Anthropic’s Claude Sonnet 3.5 to interpret natural language instructions and dynamically create event forms.
* **Persistent Storage**: Stores registration events and user data in a PostgreSQL database for reliable data management.
* **Frontend Rendering**: Employs Alpine.js and Tailwind CSS to build and style interactive, responsive registration forms.
* **Authentication**: Secured with Auth0, managing user authentication and access control.
* **Event Notifications**: Uses Mailgun to deliver reliable email confirmations and reminders to participants.
* **Client Integration**: Supports interaction through clients like ChatGPT and Claude Desktop, allowing users to generate and manage signup forms via conversational and desktop interfaces.

This architecture enables seamless, AI-driven event signups with real-time interaction and reliable data storage.

## AI-assisted Development
* Humans (I) wrote less than 1% of the code, but reviewed almost all of it (~75%).
    * Almost all the code is written by Claude and Codex.
    * With [Claude code review github actions](https://docs.claude.com/en/docs/claude-code/github-actions) integrated, I had another (AI) reviewer to verify the changes.
    * When we (AI or humans) detected a bug or an anti-pattern, we asked Claude/Codex to fix it.
* With TDD (Test-driven development), I was confident that any newly generated code didn't cause any regression.
    * Invested most of time in identifying test cases where the system could break and then ask Claude/Codex to address the missing feature/fix the bug
    * Leveraged the staging and localhost environment to give me confidence that any code deployed in prod without breaking anything from the past.
* Documented everything in the `docs/` directory so that I/Claude/Codex can resume development from the previous checkpoint.
  * These documents are the most interesting piece of the repo. The code and the business logic can be trivially generated if you can clearly articulate the architecture to the coding agents.

## Security Architecture

EZ-Scheduler implements defense-in-depth security for LLM-powered applications:

### 1. Identity & Authentication
- **Trusted Identity Provider**: Uses Auth0 for authentication and authorization
- **JWT-based Authentication**: All API requests validated with signed JWT tokens
- **User Isolation**: Every database entity tagged with `user_id` for data segregation

### 2. Write Path Security (LLM Output → Database)
- **Never Trust LLM Output**: All LLM-generated content passes through validation layers
- **ORM-based Writes**: LLM outputs transformed into typed ORM objects before database writes
- **Business Logic Validation**: Application validates all fields before persistence:
  - Required field validation (date, location for events)
  - Type checking and data sanitization
  - Business rule enforcement (e.g., dates in valid range)
- **No Direct SQL**: LLM never generates write SQL queries—all writes go through SQLAlchemy ORM

### 3. Read Path Security (Database → LLM)
- **Row-Level Security**: All read queries filtered by `user_id` (similar to PostgreSQL RLS)
- **Multi-layer Validation**:
  1. **SQL Content Validation**: Generated queries must reference `signup_forms` table with user_id filter
  2. **Parameter Validation**: Queries must include `:user_id` parameter binding
  3. **Parameter Override**: User ID forcibly set to authenticated user (prevents exfiltration)
- **Read-Only Database User**: Analytics queries execute with read-only credentials
  - If LLM generates write commands (INSERT/UPDATE/DELETE), operations fail at database level
  - Additional layer of protection against prompt injection attacks

### 4. Defense-in-Depth Layers

**Layer 1 - Application**: Business logic validates LLM outputs
**Layer 2 - Query Validation**: SQL queries validated for user isolation patterns
**Layer 3 - Parameter Override**: User ID parameter forcibly overridden
**Layer 4 - Database**: Read-only credentials prevent writes

This multi-layered approach ensures that even if one security control fails, others prevent unauthorized access or data exfiltration.

## Quick Start

### Server Setup

```bash
cd server
uv sync
cp .env.example .env  # Configure your API keys
uv run pytest tests/  # Run tests
uv run python src/ez_scheduler/main.py  # Start server
```

## Development

Each component has its own development environment and dependencies:

- Server uses `uv` for Python dependency management
- Client will use `npm`/`yarn` for Node.js dependencies

## Features

- **MCP Server**: Model Context Protocol server for Claude Desktop integration
- **Form Generation**: LLM-powered conversational form creation
- **Event Management**: Signup forms with event details and RSVP tracking
- **HTTP Transport**: RESTful API with streamable HTTP transport

## Documentation

- [Server Documentation](./server/README.md)
- Client Documentation (coming soon)
