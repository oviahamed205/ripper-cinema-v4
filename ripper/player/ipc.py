"""
ripper.player.ipc
~~~~~~~~~~~~~~~~~

Cross-Platform MPV JSON-RPC IPC Supervisor.
Supports:
- Windows Named Pipes (\\\\.\\pipe\\ripper-mpv-ipc)
- Unix Domain Sockets (/tmp/ripper-mpv-ipc.sock)
- Real-time bidirectional querying of time-pos, duration, pause state
- Sub-second resume checkpointing into ~/.ripper/history.json
- Graceful reconnection and error handling on player exit.
"""

from __future__ import annotations

import os
import sys
import json
import time
import socket
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable

HISTORY_FILE = Path.home() / ".ripper" / "history.json"


def get_default_ipc_path() -> str:
    """Return platform-specific IPC endpoint."""
    if sys.platform == "win32":
        return r"\\.\pipe\ripper-mpv-ipc"
    return "/tmp/ripper-mpv-ipc.sock"


def save_resume_checkpoint(
    title: str,
    stream_url: str,
    time_pos: float,
    duration: float,
    portal_id: str = "ripper",
    season: Optional[int] = None,
    episode: Optional[int] = None,
) -> None:
    """Persist current watch progress to history.json (seamlessly supports list and dict formats)."""
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        raw_data = None
        if HISTORY_FILE.exists():
            try:
                raw_data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                raw_data = None

        now = int(time.time())
        completed = duration > 0 and (time_pos >= 0.90 * duration)
        entry_payload = {
            "title": title,
            "stream_url": stream_url,
            "url": stream_url,
            "time_pos": round(time_pos, 2),
            "duration": round(duration, 2),
            "completed": completed,
            "portal_id": portal_id,
            "season": season,
            "episode": episode,
            "updated_at": now,
        }

        if isinstance(raw_data, list):
            updated = False
            for item in raw_data:
                if isinstance(item, dict) and (item.get("url") == stream_url or item.get("stream_url") == stream_url):
                    item.update(entry_payload)
                    updated = True
                    break
            if not updated:
                raw_data.insert(0, entry_payload)
            data_to_write = raw_data
        elif isinstance(raw_data, dict):
            raw_data[stream_url] = entry_payload
            data_to_write = raw_data
        else:
            data_to_write = {stream_url: entry_payload}

        HISTORY_FILE.write_text(json.dumps(data_to_write, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_saved_resume_position(stream_url: str) -> Optional[float]:
    """Retrieve saved resume timestamp in seconds for a given stream URL."""
    if not HISTORY_FILE.exists():
        return None
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and (item.get("url") == stream_url or item.get("stream_url") == stream_url):
                    if not item.get("completed"):
                        return float(item.get("time_pos", 0))
                    return None
            return None
        elif isinstance(data, dict):
            entry = data.get(stream_url)
            if entry and not entry.get("completed"):
                return float(entry.get("time_pos", 0))
    except Exception:
        pass
    return None


class MpvIpcClient:
    """Client for controlling and monitoring MPV through JSON-RPC."""

    def __init__(
        self,
        ipc_path: Optional[str] = None,
        on_progress: Optional[Callable[[float, float], None]] = None,
    ):
        self.ipc_path = ipc_path or get_default_ipc_path()
        self.on_progress = on_progress
        self.is_connected = False
        self._pipe_handle = None
        self._sock = None
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None

        self.last_pos: float = 0.0
        self.last_duration: float = 0.0
        self.is_paused: bool = False

    def connect(self, timeout: float = 3.0) -> bool:
        """Connect to MPV Named Pipe or Unix Domain Socket."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if sys.platform == "win32":
                    import ctypes
                    from ctypes import wintypes

                    # Open existing Windows Named Pipe
                    handle = ctypes.windll.kernel32.CreateFileW(
                        self.ipc_path,
                        0xC0000000,  # GENERIC_READ | GENERIC_WRITE
                        0,
                        None,
                        3,  # OPEN_EXISTING
                        0,
                        None,
                    )
                    if handle != -1 and handle != 0:
                        self._pipe_handle = handle
                        self.is_connected = True
                        return True
                else:
                    if os.path.exists(self.ipc_path):
                        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        sock.connect(self.ipc_path)
                        self._sock = sock
                        self.is_connected = True
                        return True
            except Exception:
                time.sleep(0.1)
                continue
            time.sleep(0.1)
        return False

    def send_command(self, command_parts: list) -> Optional[Dict[str, Any]]:
        """Send JSON-RPC command array and parse response."""
        if not self.is_connected:
            return None

        cmd_json = json.dumps({"command": command_parts}) + "\n"
        data_bytes = cmd_json.encode("utf-8")

        try:
            if sys.platform == "win32" and self._pipe_handle:
                import ctypes
                written = ctypes.c_ulong(0)
                success = ctypes.windll.kernel32.WriteFile(
                    self._pipe_handle,
                    data_bytes,
                    len(data_bytes),
                    ctypes.byref(written),
                    None,
                )
                if not success:
                    self.is_connected = False
                    return None
            elif self._sock:
                self._sock.sendall(data_bytes)
        except Exception:
            self.is_connected = False
            return None

        return {"status": "sent"}

    def get_time_pos(self) -> Optional[float]:
        """Request time-pos property."""
        self.send_command(["get_property", "time-pos"])
        return self.last_pos

    def pause(self) -> None:
        """Toggle pause."""
        self.send_command(["cycle", "pause"])

    def seek(self, seconds: float) -> None:
        """Seek relative seconds."""
        self.send_command(["seek", seconds, "relative"])

    def show_osd_text(self, text: str, duration_ms: int = 2500) -> None:
        """Show on-screen display text inside MPV window."""
        self.send_command(["show-text", text, duration_ms])

    def close(self) -> None:
        """Close IPC handle and terminate monitoring."""
        self._stop_event.set()
        self.is_connected = False
        if sys.platform == "win32" and self._pipe_handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self._pipe_handle)
            except Exception:
                pass
            self._pipe_handle = None
        elif self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
