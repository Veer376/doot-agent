FROM python:3.13-slim

# Prevent Python from writing pyc files and ensure output is unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory for the API service
WORKDIR /agent_platform

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- Install core package (orbit-agent) in editable mode for imports like `core.*` ---
# Copy only what's needed for dependency resolution & core code for better layer caching
COPY pyproject.toml /orbit-agent/pyproject.toml
COPY core/ /orbit-agent/core/

RUN pip install --no-cache-dir -e /orbit-agent

# --- Install the agent_platform service as a package ---
# Copy the service code (contains its own langgraph.json now) and install it in editable mode
COPY services/agent_platform/ /agent_platform/
RUN pip install --no-cache-dir -e /agent_platform

# Expose port
EXPOSE 5000

# Ensure both projects are importable (explicit path; extend at runtime if needed)
ENV PYTHONPATH="/orbit-agent:/agent_platform"

# Run the API service
# Note: avoid --reload in containers by default; use a dev override if needed
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "5000"]
