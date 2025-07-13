# EZ Scheduler Server

MCP Server for Signup Form Generation and Management.

## Setup

1. Install dependencies:
```bash
uv sync
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. Run tests:
```bash
uv run pytest tests/
```

4. Start server:
```bash
uv run python src/ez_scheduler/main.py
```
