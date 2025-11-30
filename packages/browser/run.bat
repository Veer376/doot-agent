@echo off
REM Install and run WebRTC browser streaming test

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Starting WebRTC signaling server...
echo Backend running on http://localhost:8765
echo Frontend should be at http://localhost:3000/browser-test
echo.
echo Press Ctrl+C to stop
echo.

uv run python webrtc_test.py
