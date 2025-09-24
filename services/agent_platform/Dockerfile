FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml first for dependency caching
COPY pyproject.toml /orbit-agent/pyproject.toml

# Install dependencies from pyproject.toml
RUN pip install --no-cache-dir -e /orbit-agent/

# Copy service-specific requirements if any
COPY services/api/app/ /app/

# Install the core package in editable mode (this will be mounted as volume)
# The actual core directory will be mounted from host
RUN mkdir -p /orbit-agent/core

# Expose port
EXPOSE 5000

# Set environment variables
ENV PYTHONPATH="/orbit-agent:$PYTHONPATH"
ENV PYTHONUNBUFFERED=1

# Command to run the API service with reload enabled
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--reload", "--reload-dir", "/orbit-agent/core", "--reload-dir", "/app"]
