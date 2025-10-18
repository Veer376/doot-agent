FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Pre-copy packages so we can install them in editable mode during build.
# At runtime, these paths will be bind-mounted for hot reload, which still works with -e installs.
COPY packages/orbit-core /app/packages/orbit-core
COPY packages/agent-platform /app/packages/agent-platform

# Copy langgraph.json for graph registry initialization
COPY langgraph.json /app/langgraph.json

# Install editable packages and their dependencies
RUN pip install --upgrade pip setuptools wheel \
    && pip install -e /app/packages/orbit-core \
    && pip install -e /app/packages/agent-platform

# Expose port
EXPOSE 5000

# Run the FastAPI app with reload for dev
CMD ["uvicorn", "agent_platform.api.main:app", "--host", "0.0.0.0", "--port", "5000", "--reload"]
