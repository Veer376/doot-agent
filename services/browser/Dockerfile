FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    WS_ENDPOINT_FILE=/var/run/playwright-ws-endpoint \
    PLAYWRIGHT_PORT=3000 \
    PLAYWRIGHT_HOST=0.0.0.0

# Basic OS deps and cleanup
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright Python and browsers + system deps
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir "playwright>=1.54.0,<2" \
    && playwright install --with-deps chromium

# Create runtime dir for writing ws endpoint file
RUN mkdir -p /var/run && chmod 777 /var/run

WORKDIR /app

# Copy the small server wrapper that exposes the ws endpoint
COPY services/browser/server.py /app/server.py

EXPOSE 3000

# Default: start Playwright server via wrapper to capture ws endpoint
CMD ["python", "/app/server.py"]
