# EZ Scheduler

A comprehensive signup form generation and management system with MCP server and React client.

## Architecture

This project is organized as a monorepo with separate server and client applications:

- **`server/`** - Python MCP server for form generation and management
- **`client/`** - React web application (future implementation)

## Quick Start

### Server Setup

```bash
cd server
uv sync
cp .env.example .env  # Configure your API keys
uv run pytest tests/  # Run tests
uv run python src/ez_scheduler/main.py  # Start server
```

### Client Setup

```bash
cd client
# Future React setup instructions
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
