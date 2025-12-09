#!/bin/bash
# Helper script to get WebSocket endpoint and run test

# Get WebSocket endpoint from running container
WS_PATH=$(docker logs orbit-test 2>&1 | grep "ws://localhost:" | tail -1 | awk '{print $NF}' | sed 's|ws://localhost:[0-9]*/|/|')

if [ -z "$WS_PATH" ]; then
    echo "❌ Could not find WebSocket path in container logs"
    exit 1
fi

echo "📡 Found WebSocket path: $WS_PATH"
echo "🔗 Full endpoint: ws://localhost:3500$WS_PATH"

# Update test file with correct path
sed -i "s|ws://localhost:3500/[^\"]*|ws://localhost:3500$WS_PATH|" test_novnc.py

# Run test
uv run python test_novnc.py
