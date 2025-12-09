"""In-memory session storage for browser sessions"""
from datetime import datetime
from typing import Optional
import uuid


class SessionStore:
    """In-memory session storage (user-based)"""
    
    def __init__(self):
        self.sessions: dict = {}
        self.user_sessions: dict[str, list[str]] = {}  # user_id -> [session_ids]
    
    def create_session(
        self, 
        user_id: str,
        pod_name: str,
        cdp_url: str,
        vnc_url: str
    ) -> str:
        """Create a new session for user"""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        
        self.sessions[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "pod_name": pod_name,
            "cdp_url": cdp_url,
            "vnc_url": vnc_url,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "status": "active",
        }
        
        # Track user's sessions
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = []
        self.user_sessions[user_id].append(session_id)
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by ID"""
        return self.sessions.get(session_id)
    
    def get_session_by_user(self, user_id: str) -> Optional[dict]:
        """Get active session for user (reuse existing)"""
        session_ids = self.user_sessions.get(user_id, [])
        
        for session_id in session_ids:
            session = self.sessions.get(session_id)
            if session and session["status"] == "active":
                return session
        
        return None
    
    def update_activity(self, session_id: str):
        """Update last activity timestamp"""
        if session_id in self.sessions:
            self.sessions[session_id]["last_activity"] = datetime.utcnow().isoformat()
    
    def delete_session(self, session_id: str):
        """Delete a session"""
        if session_id in self.sessions:
            user_id = self.sessions[session_id]["user_id"]
            del self.sessions[session_id]
            
            # Remove from user's session list
            if user_id in self.user_sessions:
                if session_id in self.user_sessions[user_id]:
                    self.user_sessions[user_id].remove(session_id)
                if not self.user_sessions[user_id]:
                    del self.user_sessions[user_id]
    
    def list_all(self) -> list:
        """List all sessions"""
        return list(self.sessions.values())
    
    def get_idle_sessions(self, idle_threshold_seconds: int) -> list[dict]:
        """Get sessions that have been idle for longer than threshold"""
        now = datetime.utcnow()
        idle_sessions = []
        
        for session in self.sessions.values():
            try:
                last_activity = datetime.fromisoformat(session["last_activity"])
                age = (now - last_activity).seconds
                
                if age > idle_threshold_seconds and session["status"] == "active":
                    idle_sessions.append(session)
            except (ValueError, KeyError):
                continue
        
        return idle_sessions
