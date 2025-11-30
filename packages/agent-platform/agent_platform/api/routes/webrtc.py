"""
WebRTC endpoints for browser streaming.

This module streams real browser content by fetching BrowserContext from
the browser_registry (which is initialized at app startup).

Flow:
1. App startup (main.py) creates browser sessions via browser_registry
2. WebRTC /offer endpoint fetches the context by session_id
3. BrowserVideoTrack captures screenshots and streams via WebRTC
"""
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel
from typing import Set, Optional
import logging
import numpy as np
from PIL import Image
import io

from ...browser_registry import browser_registry

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
    from av import VideoFrame
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False

logger = logging.getLogger("agent_platform")

if not AIORTC_AVAILABLE:
    logger.warning("aiortc not installed. WebRTC functionality will be limited.")

webrtc_router = APIRouter(prefix="", tags=["webrtc"])


class RTCSessionDescriptionModel(BaseModel):
    """WebRTC Session Description (SDP)"""
    sdp: str
    type: str  # "offer" or "answer"


class BrowserVideoTrack(VideoStreamTrack):
    """
    Video track that streams real browser screenshots.
    Fetches frames from the BrowserContext stored in browser_registry.
    """

    def __init__(self, browser_context):
        super().__init__()
        self.browser_context = browser_context
        self._page = None
        logger.info("BrowserVideoTrack initialized with real browser context")

    async def recv(self):
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
            return frame
            
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            # Return error indicator frame (dark gray)
            img_array = np.zeros((720, 1280, 3), dtype=np.uint8)
            img_array[:, :] = [50, 50, 50]
            frame = VideoFrame.from_ndarray(img_array, format='rgb24')
            frame.pts = pts
            frame.time_base = time_base
            return frame


class DummyVideoTrack(VideoStreamTrack):
    """Fallback dummy track when no browser context is available."""

    def __init__(self):
        super().__init__()
        self.counter = 0
        logger.info("DummyVideoTrack initialized (no browser)")

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        
        # Blue gradient pattern
        img = np.zeros((720, 1280, 3), dtype=np.uint8)
        offset = (self.counter * 2) % 256
        img[:, :, 0] = offset
        img[:, :, 1] = 100
        img[:, :, 2] = 200
        self.counter += 1

        frame = VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


# Global state for peer connections
peer_connections: Set[RTCPeerConnection] = set()


@webrtc_router.post("/offer")
async def handle_webrtc_offer(
    offer: RTCSessionDescriptionModel = Body(...),
    session_id: str = Query(default="test_user", description="Browser session ID (user_id)")
) -> RTCSessionDescriptionModel:
    """
    Handle WebRTC offer from frontend.
    
    Fetches the browser context from browser_registry by session_id,
    then streams real browser screenshots via WebRTC.
    
    If no browser session exists, falls back to dummy video track.
    """
    if not AIORTC_AVAILABLE:
        raise HTTPException(
            status_code=503, 
            detail="aiortc not installed. Run: pip install aiortc av numpy pillow"
        )
    
    logger.info(
        "Received WebRTC offer: type=%s, session_id=%s, sdp_length=%s",
        offer.type,
        session_id,
        len(offer.sdp) if offer.sdp else 0,
    )
    
    try:
        # Try to get browser context from registry
        browser_context = await browser_registry.get_session(session_id)
        
        # Create peer connection
        # Force UDP port range for Docker compatibility
        pc = RTCPeerConnection()
        peer_connections.add(pc)
        
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("WebRTC connection state: %s", pc.connectionState)
            if pc.connectionState in ["failed", "closed"]:
                await pc.close()
                peer_connections.discard(pc)
                logger.info("Peer connection closed and removed from registry")
        
        # Add video track based on whether we have a browser context
        if browser_context:
            logger.info(f"Using real browser context for session: {session_id}")
            video_track = BrowserVideoTrack(browser_context)
        else:
            logger.warning(f"No browser session found for {session_id}, using dummy track")
            video_track = DummyVideoTrack()
        
        pc.addTrack(video_track)
        
        # Set remote description from offer
        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=offer.sdp, type=offer.type)
        )
        
        # Create answer
        answer = await pc.createAnswer()
        
        # Munge SDP to replace internal Docker IP with localhost
        # This allows the host browser to connect to the mapped UDP ports
        if answer.sdp:
            # Replace 172.x.x.x with 127.0.0.1 in candidate lines
            # This is a hack for dev environment where browser is on host and api is in docker
            import re
            # Find the internal IP (likely 172.18.0.x)
            # We'll just replace any private IP that isn't 127.0.0.1 with 127.0.0.1
            # But simpler: just replace the connection address if it's the container IP
            # Actually, aiortc generates candidates. We need to patch them.
            
            # Simple regex to replace the IP in candidate lines
            # candidate:1 1 UDP 2122260223 172.18.0.5 56304 typ host
            answer.sdp = re.sub(
                r"(candidate:\S+ \d+ UDP \d+) (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}) (\d+ typ host)",
                r"\1 127.0.0.1 \3",
                answer.sdp
            )
            # Also replace c=IN IP4 ...
            answer.sdp = re.sub(
                r"c=IN IP4 (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"c=IN IP4 127.0.0.1",
                answer.sdp
            )
            logger.info("Munged SDP to use localhost for Docker compatibility")

        await pc.setLocalDescription(answer)
        
        logger.info("WebRTC answer created successfully")
        
        return RTCSessionDescriptionModel(
            sdp=pc.localDescription.sdp,
            type=pc.localDescription.type
        )
        
    except Exception as e:
        logger.error(f"Error handling WebRTC offer: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"WebRTC error: {str(e)}")


@webrtc_router.get("/webrtc/status")
async def webrtc_status():
    """Get WebRTC connection status."""
    return {
        "status": "ready" if AIORTC_AVAILABLE else "aiortc_not_installed",
        "active_connections": len(peer_connections),
        "aiortc_available": AIORTC_AVAILABLE,
        "browser_sessions": browser_registry.list_sessions(),
    }


@webrtc_router.post("/webrtc/cleanup")
async def cleanup_connections():
    """Cleanup all peer connections."""
    logger.info("Cleaning up WebRTC connections")
    count = len(peer_connections)
    for pc in list(peer_connections):
        await pc.close()
    peer_connections.clear()
    return {"status": "cleaned", "closed_connections": count}


@webrtc_router.post("/browser/session")
async def create_browser_session(
    session_id: str = Query(..., description="Session ID (user_id)"),
    initial_url: str = Query(default="https://www.google.com", description="Initial URL to navigate to")
):
    """Create a new browser session for a user."""
    try:
        await browser_registry.create_session(session_id, initial_url=initial_url)
        return {
            "status": "created",
            "session_id": session_id,
            "initial_url": initial_url,
        }
    except Exception as e:
        logger.error(f"Failed to create browser session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@webrtc_router.delete("/browser/session")
async def delete_browser_session(
    session_id: str = Query(..., description="Session ID to delete")
):
    """Delete a browser session."""
    removed = await browser_registry.remove_session(session_id)
    if removed:
        return {"status": "deleted", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")


@webrtc_router.get("/browser/sessions")
async def list_browser_sessions():
    """List all active browser sessions."""
    return {
        "sessions": browser_registry.list_sessions(),
    }
