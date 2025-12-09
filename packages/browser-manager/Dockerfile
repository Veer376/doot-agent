FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY browser_manager/ ./browser_manager/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e .

# Install Playwright (library only, no browsers needed)
RUN pip install --no-cache-dir playwright

# Create non-root user for security
RUN useradd -m -u 1000 browser-manager && \
    chown -R browser-manager:browser-manager /app

USER browser-manager

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "browser_manager.main:app", "--host", "0.0.0.0", "--port", "8000"]
