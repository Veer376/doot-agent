FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    WS_ENDPOINT_FILE=/var/run/playwright-ws-endpoint \
    DISPLAY=:0

# Install system dependencies including VNC stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    xvfb \
    x11vnc \
    fluxbox \
    xterm \
    x11-utils \
    fonts-liberation \
    xfonts-base \
    supervisor \
    net-tools \
    socat \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright Python and browsers + system deps
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir "playwright>=1.49.0,<2" websockify \
    && playwright install --with-deps chromium

# Install noVNC
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /opt/noVNC \
    && git clone --depth 1 https://github.com/novnc/websockify /opt/noVNC/utils/websockify \
    && ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html

# Create runtime dir for writing ws endpoint file
RUN mkdir -p /var/run && chmod 777 /var/run

# Create fluxbox config directory and basic init file
RUN mkdir -p /root/.fluxbox && \
    echo "session.screen0.toolbar.visible: false" > /root/.fluxbox/init && \
    echo "session.screen0.slit.autoHide: true" >> /root/.fluxbox/init && \
    echo "session.screen0.defaultDeco: NONE" >> /root/.fluxbox/init && \
    echo "session.screen0.tabs.usePixmap: false" >> /root/.fluxbox/init && \
    echo "[app] (name=chromium) [Deco] {NONE}" > /root/.fluxbox/apps && \
    echo "[app] (name=chrome) [Deco] {NONE}" >> /root/.fluxbox/apps && \
    echo "[app] (class=Chromium) [Deco] {NONE}" >> /root/.fluxbox/apps && \
    echo "[app] (class=Google-chrome) [Deco] {NONE}" >> /root/.fluxbox/apps

WORKDIR /app

# Copy supervisor config and server
COPY packages/browser/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY packages/browser/browser/server.py /app/server.py

# Expose ports: CDP, VNC, noVNC web
EXPOSE 9223 5900 6080

# Start all services via supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
