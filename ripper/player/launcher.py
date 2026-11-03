"""
Media Player integration for unshorten-cli (Enterprise & Pro Edition).
Supports launching direct video streams (Cloudflare R2, S3, CDN) directly in:
- PotPlayer (PotPlayerMini64.exe / PotPlayerMini.exe / PotPlayer64.exe)
- VLC Media Player
- MPV Player
- Windows Default Media Player
"""

import os
import sys
import shutil
import subprocess
try:
    import winreg
except ImportError:
    winreg = None
from typing import Optional, Tuple, List

if not hasattr(os, "startfile"):
    def _posix_startfile(filepath: str) -> None:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.startfile = _posix_startfile  # type: ignore[attr-defined]

# Common installation paths for PotPlayer & VLC on Windows
POTPLAYER_COMMON_PATHS = [
    r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe",
    r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini.exe",
    r"C:\Program Files (x86)\DAUM\PotPlayer\PotPlayerMini.exe",
    r"C:\Program Files (x86)\DAUM\PotPlayer\PotPlayerMini64.exe",
    r"C:\Program Files\DAUM\PotPlayer\PotPlayer64.exe",
    r"C:\Program Files (x86)\DAUM\PotPlayer\PotPlayer.exe",
    r"C:\Program Files\PotPlayer\PotPlayerMini64.exe",
    r"C:\Program Files\PotPlayer\PotPlayer64.exe",
    r"C:\Program Files (x86)\PotPlayer\PotPlayerMini.exe",
    os.path.expanduser(r"~\AppData\Local\DAUM\PotPlayer\PotPlayerMini64.exe"),
    os.path.expanduser(r"~\AppData\Local\Programs\PotPlayer\PotPlayerMini64.exe"),
    os.path.expanduser(r"~\AppData\Roaming\DAUM\PotPlayer\PotPlayerMini64.exe"),
    r"D:\PotPlayer\PotPlayerMini64.exe",
    r"E:\PotPlayer\PotPlayerMini64.exe",
    r"D:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe",
    r"E:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe",
]

VLC_COMMON_PATHS = [
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    r"D:\Program Files\VideoLAN\VLC\vlc.exe",
    r"E:\Program Files\VideoLAN\VLC\vlc.exe",
]

MPV_COMMON_PATHS = [
    r"C:\Program Files\mpv\mpv.exe",
    r"C:\mpv\mpv.exe",
    r"D:\mpv\mpv.exe",
]


def find_potplayer_in_registry() -> Optional[str]:
    """Search Windows registry for PotPlayer executable path."""
    if sys.platform != "win32" or winreg is None:
        return None

    keys_to_check = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\DAUM\PotPlayer", "ProgramPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\DAUM\PotPlayer", "ProgramPath"),
        (winreg.HKEY_CURRENT_USER, r"Software\DAUM\PotPlayer", "ProgramPath"),
        (winreg.HKEY_CLASSES_ROOT, r"Applications\PotPlayerMini64.exe\shell\open\command", ""),
        (winreg.HKEY_CLASSES_ROOT, r"Applications\PotPlayer64.exe\shell\open\command", ""),
        (winreg.HKEY_CLASSES_ROOT, r"Applications\PotPlayer.exe\shell\open\command", ""),
        (winreg.HKEY_CLASSES_ROOT, r"PotPlayer.File\shell\open\command", ""),
        (winreg.HKEY_CLASSES_ROOT, r"PotPlayer64.File\shell\open\command", ""),
    ]

    for root, subkey, val_name in keys_to_check:
        try:
            with winreg.OpenKey(root, subkey) as key:
                val, _ = winreg.QueryValueEx(key, val_name)
                if val:
                    clean_path = val.split('"')[1] if '"' in val else val.split()[0]
                    if os.path.exists(clean_path):
                        return clean_path
        except Exception:
            pass
    return None


def detect_available_players() -> List[Tuple[str, str]]:
    """Detect all installed video players available on system, prioritizing PotPlayer."""
    players: List[Tuple[str, str]] = []

    # 1. Check PotPlayer direct paths first (highest priority)
    for p in POTPLAYER_COMMON_PATHS:
        if os.path.exists(p):
            players.append(("PotPlayer", p))
            break

    if not players:
        pot_reg = find_potplayer_in_registry()
        if pot_reg and os.path.exists(pot_reg):
            players.append(("PotPlayer", pot_reg))

    if not players:
        for bin_name in ("PotPlayerMini64.exe", "PotPlayer64.exe", "PotPlayer.exe", "potplayer"):
            w = shutil.which(bin_name)
            if w:
                players.append(("PotPlayer", w))
                break

    # 2. VLC
    for v in VLC_COMMON_PATHS:
        if os.path.exists(v):
            players.append(("VLC Media Player", v))
            break
    if not any("VLC" in name for name, _ in players):
        w = shutil.which("vlc")
        if w:
            players.append(("VLC Media Player", w))

    # 3. MPV
    for m in MPV_COMMON_PATHS:
        if os.path.exists(m):
            players.append(("MPV Player", m))
            break
    if not any("MPV" in name for name, _ in players):
        w = shutil.which("mpv")
        if w:
            players.append(("MPV Player", w))

    # 4. Headless / Cross-platform Cinema Web & VLC Bridge Fallback
    if not players:
        players.append(("VLC / Cinema Web Player", "http://127.0.0.1:5055/player"))

    return players


def launch_video_stream_in_player(
    stream_url: str,
    custom_player_path: Optional[str] = None,
    subtitle_path: Optional[str] = None,
    audio_language: Optional[str] = None,
    title: Optional[str] = None,
    filename: Optional[str] = None,
    **kwargs,
) -> Tuple[bool, str]:
    """
    Launch direct video stream in PotPlayer (default), VLC, MPV, or system player with optional subtitles and audio language.
    Returns (success: bool, status_message: str).
    """
    clean_url = stream_url.strip()
    session_title = title or filename or "Media Stream"

    # Normalize audio language tag
    lang_tag = (audio_language or "").strip().lower()

    # If custom player provided and valid
    if custom_player_path and os.path.exists(custom_player_path):
        try:
            cmd = [custom_player_path, clean_url]
            if subtitle_path and os.path.exists(subtitle_path):
                if "potplayer" in custom_player_path.lower():
                    cmd.append(f'/sub="{subtitle_path}"')
                elif "vlc" in custom_player_path.lower():
                    cmd.append(f"--sub-file={subtitle_path}")
                elif "mpv" in custom_player_path.lower():
                    cmd.append(f"--sub-file={subtitle_path}")
            if lang_tag:
                if "potplayer" in custom_player_path.lower():
                    cmd.append(f'/audio="{lang_tag}"')
                elif "vlc" in custom_player_path.lower():
                    cmd.append(f"--audio-language={lang_tag}")
                elif "mpv" in custom_player_path.lower():
                    cmd.append(f"--alang={lang_tag}")
            subprocess.Popen(cmd)
            return True, f"Launched in Custom Player ({os.path.basename(custom_player_path)})"
        except Exception as e:
            return False, f"Failed to launch custom player: {e}"

    # Auto-detect player with PotPlayer as #1 priority
    players = detect_available_players()

    if players:
        player_name, player_bin = players[0]
        try:
            cmd = [player_bin, clean_url]
            if subtitle_path and os.path.exists(subtitle_path):
                if "PotPlayer" in player_name:
                    cmd.append(f'/sub="{subtitle_path}"')
                elif "VLC" in player_name:
                    cmd.append(f"--sub-file={subtitle_path}")
                elif "MPV" in player_name:
                    cmd.append(f"--sub-file={subtitle_path}")

            if lang_tag:
                if "PotPlayer" in player_name:
                    cmd.append(f'/audio="{lang_tag}"')
                elif "VLC" in player_name:
                    cmd.append(f"--audio-language={lang_tag}")
                elif "MPV" in player_name:
                    cmd.append(f"--alang={lang_tag}")

            save_playback_resume_state(clean_url, title=session_title, subtitle_path=subtitle_path)
            subprocess.Popen(cmd)
            sub_msg = f" (Sub: {os.path.basename(subtitle_path)})" if subtitle_path else ""
            audio_msg = f" [Audio: {lang_tag.upper()}]" if lang_tag else ""
            return True, f"🚀 Streaming live in {player_name} ({os.path.basename(player_bin)}){sub_msg}{audio_msg}!"
        except Exception as e:
            return False, f"Failed to launch {player_name}: {e}"

    # Fallback to system default association
    if sys.platform == "win32":
        try:
            save_playback_resume_state(clean_url, title=session_title, subtitle_path=subtitle_path)
            os.startfile(clean_url)
            return True, "🚀 Opened in Default System Media Player!"
        except Exception as e:
            return False, f"Failed to open default player: {e}"

    return False, "No compatible media player found."


def save_playback_resume_state(stream_url: str, title: str = "", subtitle_path: Optional[str] = None):
    """Save last played stream and timestamp for 1-click resume."""
    try:
        from pathlib import Path
        import json, time
        cfg_dir = Path.home() / ".ripper"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        state_file = cfg_dir / "resume_state.json"
        state = {
            "stream_url": stream_url,
            "title": title or "Media Stream",
            "subtitle_path": subtitle_path,
            "timestamp": time.time(),
        }
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_playback_resume_state() -> Optional[dict]:
    """Retrieve last played stream for resume playback."""
    try:
        from pathlib import Path
        import json
        state_file = Path.home() / ".ripper" / "resume_state.json"
        if state_file.exists():
            return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


