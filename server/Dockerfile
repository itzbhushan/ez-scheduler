FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY .env ./

# Install Python dependencies
RUN uv sync --frozen

# Expose port (changed from 8000 to 8080 to match server)
EXPOSE 8080

# Run the application
CMD ["uv", "run", "python", "src/ez_scheduler/main.py"]