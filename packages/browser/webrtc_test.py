"""
WebRTC browser streaming test server.

This is a standalone server that:
1. Connects to a remote browser via WSS (e.g., ws://localhost:3500/)
2. Captures real browser screenshots
3. Streams them via WebRTC to the frontend

Run this separately from the main FastAPI app to test real browser streaming
without the Windows/Playwright subprocess issues.

Usage:
    # First, start the browser container:
    docker run --rm -p 3500:3500 --name orbit-browser orbit-browser
    
    # Then run this server:
    export BROWSER_WSS_URL=ws://localhost:3500/
    uv run python packages/browser/webrtc_test.py
    
    # Frontend connects to http://localhost:8765/offer
"""

import asyncio
import json
import os
import logging
from typing import Optional, Set
from fractions import Fraction

from aiohttp import web
import numpy as np
from PIL import Image
import io

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

# Add orbit-core to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "orbit-core"))

from orbit_core.browser_use.browser import Browser, BrowserConfig
from orbit_core.browser_use.context import BrowserContext, BrowserContextConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BrowserVideoTrack(VideoStreamTrack):
    """Video track that streams real browser screenshots."""
    
    def __init__(self, browser_context: BrowserContext):
        super().__init__()
        self.browser_context = browser_context
        self.counter = 0
        self._page = None
        logger.info("BrowserVideoTrack initialized with real browser context")
    
    async def recv(self):
        """Capture and send browser screenshot as video frame."""
        pts, time_base = await self.next_timestamp()
        
        try:
            # Get current page (cache it)
            if self._page is None:
                self._page = await self.browser_context.get_agent_current_page()
            
            # Take screenshot
            screenshot_bytes = await self._page.screenshot(type='png')
            
            # Convert to video frame
            img = Image.open(io.BytesIO(screenshot_bytes))
            # Ensure RGB format (no alpha)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img_array = np.array(img)
            
            # Create video frame
            frame = VideoFrame.from_ndarray(img_array, format='rgb24')
            frame.pts = pts
            frame.time_base = time_base
            
            self.counter += 1
            return frame
            
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            # Return blank frame on error
            img_array = np.zeros((720, 1280, 3), dtype=np.uint8)
            img_array[:, :] = [50, 50, 50]  # Dark gray to indicate error
            frame = VideoFrame.from_ndarray(img_array, format='rgb24')
            frame.pts = pts
            frame.time_base = time_base
            return frame


# Global state
browser: Optional[Browser] = None
browser_context: Optional[BrowserContext] = None
peer_connections: Set[RTCPeerConnection] = set()


async def get_or_create_browser_context() -> BrowserContext:
    """Get or create browser context connected to remote browser via WSS."""
    global browser, browser_context
    
    if browser_context is not None:
        return browser_context
    
    # Get WSS URL from environment
    wss_url = os.environ.get("BROWSER_WSS_URL", "ws://localhost:3500/")
    logger.info(f"Connecting to browser at: {wss_url}")
    
    config = BrowserConfig(
        wss_url=wss_url,
        headless=False,
    )
    
    browser = Browser(config=config)
    
    browser_context = await browser.new_context(
        config=BrowserContextConfig(
            window_width=1280,
            window_height=720,
            highlight_elements=False,
        )
    )
    
    # Navigate to initial page
    page = await browser_context.get_agent_current_page()
    await page.goto("https://www.google.com")
    logger.info("Browser context created and navigated to Google")
    
    return browser_context


async def handle_offer(request):
    """Handle WebRTC offer from frontend."""
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    
    logger.info(f"Received WebRTC offer: type={offer.type}")
    
    try:
        # Get browser context
        context = await get_or_create_browser_context()
        
        # Create peer connection
        pc = RTCPeerConnection()
        peer_connections.add(pc)
        
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state: {pc.connectionState}")
            if pc.connectionState in ["failed", "closed"]:
                await pc.close()
                peer_connections.discard(pc)
        
        # Add video track with real browser screenshots
        video_track = BrowserVideoTrack(context)
        pc.addTrack(video_track)
        
        # Set remote description from offer
        await pc.setRemoteDescription(offer)
        
        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        logger.info("WebRTC answer created successfully")
        
        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type,
            })
        )
        
    except Exception as e:
        logger.error(f"Error handling offer: {e}", exc_info=True)
        return web.Response(
            status=500,
            content_type="application/json",
            text=json.dumps({"error": str(e)})
        )


async def handle_status(request):
    """Return server status."""
    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "status": "ready",
            "browser_connected": browser_context is not None,
            "active_connections": len(peer_connections),
            "wss_url": os.environ.get("BROWSER_WSS_URL", "ws://localhost:3500/"),
        })
    )


@web.middleware
async def cors_middleware(request, handler):
    """CORS middleware for cross-origin requests."""
    if request.method == "OPTIONS":
        return web.Response(
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
        )
    
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


async def on_shutdown(app):
    """Cleanup on shutdown."""
    global browser, browser_context
    
    # Close all peer connections
    for pc in list(peer_connections):
        await pc.close()
    peer_connections.clear()
    
    # Close browser
    if browser:
        await browser.close()
        browser = None
        browser_context = None
    
    logger.info("Cleanup complete")


async def main():
    """Run the WebRTC test server."""
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_post("/offer", handle_offer)
    app.router.add_get("/status", handle_status)
    app.on_shutdown.append(on_shutdown)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("WEBRTC_PORT", "8765"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"WebRTC test server running on http://localhost:{port}")
    logger.info(f"Browser WSS URL: {os.environ.get('BROWSER_WSS_URL', 'ws://localhost:3500/')}")
    logger.info("Press Ctrl+C to stop")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
