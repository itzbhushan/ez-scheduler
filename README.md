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
