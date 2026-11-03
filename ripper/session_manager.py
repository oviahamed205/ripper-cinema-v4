"""
Session Sentinel & Auto-Refresher for unshorten-cli.
Maintains active streaming sessions, continuously revalidates tokens in the background,
and feeds fresh live streams to both the Localhost Web Player and PotPlayer.
"""

import time
import uuid
import threading
import asyncio
from typing import Dict, Any, Optional, List

# Global session registry: session_id -> session_data
_ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
_SESSIONS_LOCK = threading.Lock()
_WATCHER_THREAD: Optional[threading.Thread] = None

def register_playback_session(
    origin_url: str,
    title: str,
    initial_streams: List[Dict[str, Any]],
    referer: str = ""
) -> str:
    """Registers a new playback session and starts the background sentinel if needed."""
    session_id = uuid.uuid4().hex[:12]
    now = time.time()
    
    with _SESSIONS_LOCK:
        _ACTIVE_SESSIONS[session_id] = {
            "session_id": session_id,
            "origin_url": origin_url,
            "title": title,
            "referer": referer or origin_url,
            "streams": initial_streams,
            "active_stream_url": initial_streams[0]["url"] if initial_streams else "",
            "active_quality": initial_streams[0].get("quality", "Default") if initial_streams else "",
            "created_at": now,
            "last_updated": now,
            "refresh_count": 0,
            "status": "ready"
        }
        
    ensure_watcher_running()
    return session_id

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _SESSIONS_LOCK:
        sess = _ACTIVE_SESSIONS.get(session_id)
        return dict(sess) if sess else None

def update_session_stream(session_id: str, stream_url: str, quality: str = ""):
    with _SESSIONS_LOCK:
        if session_id in _ACTIVE_SESSIONS:
            _ACTIVE_SESSIONS[session_id]["active_stream_url"] = stream_url
            if quality:
                _ACTIVE_SESSIONS[session_id]["active_quality"] = quality
            _ACTIVE_SESSIONS[session_id]["last_updated"] = time.time()

def refresh_session_streams_sync(session_id: str) -> bool:
    """Re-scrapes origin URL to refresh security tokens and mirrors."""
    sess = get_session(session_id)
    if not sess:
        return False
        
    origin_url = sess.get("origin_url")
    if not origin_url:
        return False
        
    try:
        from .anystream import extract_any_streams
        loop = asyncio.new_event_loop()
        fresh_streams = loop.run_until_complete(extract_any_streams(origin_url))
        loop.close()
        
        if fresh_streams:
            with _SESSIONS_LOCK:
                if session_id in _ACTIVE_SESSIONS:
                    _ACTIVE_SESSIONS[session_id]["streams"] = fresh_streams
                    # Preserve quality if matching
                    curr_q = _ACTIVE_SESSIONS[session_id].get("active_quality", "")
                    matched = next((s for s in fresh_streams if s.get("quality") == curr_q), fresh_streams[0])
                    _ACTIVE_SESSIONS[session_id]["active_stream_url"] = matched["url"]
                    _ACTIVE_SESSIONS[session_id]["last_updated"] = time.time()
                    _ACTIVE_SESSIONS[session_id]["refresh_count"] += 1
            return True
    except Exception:
        pass
    return False

def _sentinel_loop():
    """Background thread that periodically checks and updates sessions."""
    while True:
        time.sleep(30)
        with _SESSIONS_LOCK:
            now = time.time()
            # Clean up sessions older than 3 hours
            dead_ids = [sid for sid, d in _ACTIVE_SESSIONS.items() if now - d.get("last_updated", 0) > 10800]
            for sid in dead_ids:
                del _ACTIVE_SESSIONS[sid]
                
            active_ids = list(_ACTIVE_SESSIONS.keys())
            
        for sid in active_ids:
            try:
                # Refresh tokens every 8 minutes
                sess = get_session(sid)
                if sess and (time.time() - sess.get("last_updated", 0) > 480):
                    refresh_session_streams_sync(sid)
            except Exception:
                pass

def ensure_watcher_running():
    global _WATCHER_THREAD
    if _WATCHER_THREAD is None or not _WATCHER_THREAD.is_alive():
        _WATCHER_THREAD = threading.Thread(target=_sentinel_loop, daemon=True)
        _WATCHER_THREAD.start()
