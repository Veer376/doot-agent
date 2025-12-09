#!/bin/bash
# Start Node.js Playwright server and forward its WebSocket to 0.0.0.0:3500

# Start playwright server in background, capture its output
npx playwright launch-server --browser chromium 2>&1 | tee /tmp/playwright.log &
PLAYWRIGHT_PID=$!

# Wait for WebSocket endpoint to appear
echo "Waiting for Playwright server to start..."
for i in {1..30}; do
    if grep -q "ws://" /tmp/playwright.log 2>/dev/null; then
        WS_URL=$(grep -o "ws://[^[:space:]]*" /tmp/playwright.log | head -1)
        echo "Playwright server started: $WS_URL"
        
        # Extract port and path from ws://localhost:PORT/PATH
        LOCAL_PORT=$(echo "$WS_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
        WS_PATH=$(echo "$WS_URL" | sed -n 's/.*:[0-9]*\(\/.*\)/\1/p')
        
        echo "Local Playwright port: $LOCAL_PORT"
        echo "WebSocket path: $WS_PATH"
        
        # Write the forwarded endpoint (accessible from host)
        echo "ws://0.0.0.0:3500$WS_PATH" > /var/run/playwright-ws-endpoint
        
        # Use socat to forward port 3500 to the local playwright port
        # This preserves the WebSocket upgrade and path
        echo "Starting socat forwarder: 0.0.0.0:3500 -> 127.0.0.1:$LOCAL_PORT"
        exec socat TCP-LISTEN:3500,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:$LOCAL_PORT
    fi
    sleep 0.5
done

echo "ERROR: Playwright server failed to start"
kill $PLAYWRIGHT_PID 2>/dev/null
exit 1
