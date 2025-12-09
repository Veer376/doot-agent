"""Main FastAPI application for browser-manager"""
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
import asyncio
import uuid

from browser_manager.config import config
from browser_manager.k8s_pod_manager import KubernetesPodManager
from browser_manager.session_store import SessionStore
from browser_manager.playwright_manager import PlaywrightManager

# Global instances
pod_manager: KubernetesPodManager = None
session_store: SessionStore = None
playwright_mgr: PlaywrightManager = None
cleanup_task = None


async def cleanup_worker():
    """Background task to cleanup stale sessions and pods"""
    while True:
        try:
            await asyncio.sleep(config.cleanup_interval_seconds)
            
            # Cleanup idle sessions
            idle_sessions = session_store.get_idle_sessions(config.idle_timeout_seconds)
            for session in idle_sessions:
                session_id = session["session_id"]
                print(f"🧹 Cleaning up idle session: {session_id}")
                
                try:
                    # Close Playwright
                    await playwright_mgr.close_session(session_id)
                    
                    # Delete pod
                    pod_manager.delete_pod(session["pod_name"])
                    
                    # Remove from store
                    session_store.delete_session(session_id)
                except Exception as e:
                    print(f"⚠️ Error cleaning up session {session_id}: {e}")
            
            # Cleanup stale pods (safety net)
            pod_manager.cleanup_stale_pods(config.max_lifetime_seconds)
            
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle"""
    global pod_manager, session_store, playwright_mgr, cleanup_task
    
    print("🚀 Starting Browser Manager (Kubernetes-native)...")
    print(f"   Namespace: {config.namespace}")
    print(f"   Browser Image: {config.browser_image}")
    print(f"   Max Browsers: {config.max_browsers}")
    
    # Initialize managers
    pod_manager = KubernetesPodManager(config)
    session_store = SessionStore()
    playwright_mgr = PlaywrightManager()
    
    await playwright_mgr.start()
    
    # Start background cleanup task
    cleanup_task = asyncio.create_task(cleanup_worker())
    
    print("✅ Browser Manager ready")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down Browser Manager...")
    
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    
    # Cleanup all active sessions
    active_sessions = session_store.list_all()
    print(f"   Cleaning up {len(active_sessions)} active sessions...")
    
    for session in active_sessions:
        try:
            await playwright_mgr.close_session(session["session_id"])
            pod_manager.delete_pod(session["pod_name"])
        except Exception as e:
            print(f"⚠️ Error cleaning up session {session['session_id']}: {e}")
    
    await playwright_mgr.stop()
    
    print("✅ Browser Manager stopped")


app = FastAPI(
    title="Browser Manager",
    description="Kubernetes-native browser orchestration service",
    version="0.1.0",
    lifespan=lifespan,
)


# Request/Response models
class CreateSessionRequest(BaseModel):
    user_id: str


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    cdp_url: str
    vnc_url: str
    status: str
    pod_name: str


class HealthResponse(BaseModel):
    status: str
    active_sessions: int
    max_capacity: int
    environment: str


# Routes
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "browser-manager",
        "version": "0.1.0",
        "status": "running",
        "active_sessions": len(session_store.list_all()),
        "max_capacity": config.max_browsers,
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        active_sessions=len(session_store.list_all()),
        max_capacity=config.max_browsers,
        environment=config.environment,
    )


@app.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    Create or reuse browser session for user.
    If a session already exists for the user, it will be reused.
    """
    
    # Check if session exists for user (reuse)
    existing = session_store.get_session_by_user(request.user_id)
    if existing:
        session_store.update_activity(existing["session_id"])
        print(f"♻️ Reusing existing session for user {request.user_id}: {existing['session_id']}")
        return SessionResponse(**existing)
    
    # Check capacity
    active_count = len(session_store.list_all())
    if active_count >= config.max_browsers:
        raise HTTPException(
            status_code=503, 
            detail=f"Browser capacity exceeded ({active_count}/{config.max_browsers})"
        )
    
    try:
        # Generate session ID
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        
        # Create Kubernetes Pod
        print(f"📦 Creating browser pod for user {request.user_id} (session: {session_id})...")
        pod_info = pod_manager.create_browser_pod(
            session_id=session_id,
            user_id=request.user_id
        )
        
        # Create session in store
        created_session_id = session_store.create_session(
            user_id=request.user_id,
            pod_name=pod_info["pod_name"],
            cdp_url=pod_info["cdp_url"],
            vnc_url=pod_info["vnc_url"],
        )
        
        # Connect Playwright
        print(f"🔗 Connecting Playwright to browser...")
        await playwright_mgr.connect_to_browser(
            created_session_id, 
            pod_info["cdp_url"]
        )
        
        session = session_store.get_session(created_session_id)
        print(f"✅ Session created: {created_session_id}")
        
        return SessionResponse(**session)
    
    except Exception as e:
        print(f"❌ Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session details by ID"""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(**session)


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Terminate session and cleanup resources"""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        print(f"🗑️ Deleting session: {session_id}")
        
        # Close Playwright context
        await playwright_mgr.close_session(session_id)
        
        # Delete Kubernetes Pod
        pod_manager.delete_pod(session["pod_name"])
        
        # Remove from store
        session_store.delete_session(session_id)
        
        print(f"✅ Session deleted: {session_id}")
        return {"status": "deleted", "session_id": session_id}
    
    except Exception as e:
        print(f"❌ Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions/{session_id}/heartbeat")
async def session_heartbeat(session_id: str):
    """Update session activity (prevents idle timeout)"""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_store.update_activity(session_id)
    return {"status": "ok", "session_id": session_id}


@app.get("/sessions")
async def list_sessions():
    """List all active sessions"""
    sessions = session_store.list_all()
    return {
        "total": len(sessions),
        "sessions": [SessionResponse(**s) for s in sessions]
    }


@app.get("/admin/pods")
async def list_pods():
    """Admin: List all browser pods"""
    pods = pod_manager.list_browser_pods()
    return {
        "total": len(pods),
        "pods": [
            {
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "pod_ip": pod.status.pod_ip,
                "labels": pod.metadata.labels,
                "created_at": pod.metadata.annotations.get("created-at"),
            }
            for pod in pods
        ]
    }


@app.post("/admin/cleanup")
async def force_cleanup():
    """Admin: Force cleanup of stale sessions and pods"""
    print("🧹 Force cleanup triggered...")
    
    # Cleanup idle sessions
    idle_sessions = session_store.get_idle_sessions(config.idle_timeout_seconds)
    for session in idle_sessions:
        session_id = session["session_id"]
        try:
            await playwright_mgr.close_session(session_id)
            pod_manager.delete_pod(session["pod_name"])
            session_store.delete_session(session_id)
        except Exception as e:
            print(f"⚠️ Error cleaning up session {session_id}: {e}")
    
    # Cleanup stale pods
    pod_manager.cleanup_stale_pods(config.max_lifetime_seconds)
    
    return {
        "status": "cleanup_complete",
        "idle_sessions_cleaned": len(idle_sessions)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.host, port=config.port)
