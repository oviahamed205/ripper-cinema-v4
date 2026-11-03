# 🎮 POTPLAYER, VLC & LOCAL CAST INTEGRATION
### Native Media Player Launchers, Process Management & Zero-Touch Playback

---

## 1. Native Desktop Player Detection (`unshorten/player.py`)

The player launcher scans standard Windows installation directories for high-performance players:

```python
PLAYER_REGISTRY = [
    {
        "name": "PotPlayer",
        "paths": [
            r"C:\Program Files\DAUM\PotPlayer\PotPlayer64.exe",
            r"C:\Program Files (x86)\DAUM\PotPlayer\PotPlayer.exe",
            r"C:\Program Files\PotPlayer\PotPlayer64.exe",
        ],
        "args": ["{url}", "/sub={sub_path}", "/title={title}"]
    },
    {
        "name": "VLC",
        "paths": [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ],
        "args": ["{url}", "--sub-file={sub_path}", "--meta-title={title}"]
    },
    {
        "name": "MPV",
        "paths": [
            r"C:\Program Files\mpv\mpv.exe",
            r"C:\mpv\mpv.exe",
        ],
        "args": ["{url}", "--sub-file={sub_path}", "--title={title}"]
    }
]
```

---

## 2. Launch Execution Strategy
* **Non-Blocking Background Spawn**: Uses `subprocess.Popen` with `creationflags=subprocess.DETACHED_PROCESS` on Windows so the CLI terminal remains interactive and responsive while the movie plays.
* **Auto-Subtitle Injection**: When a `.srt` subtitle is fetched by `subtitles.py`, the path is automatically passed to the player via `/sub=` or `--sub-file=`, so subtitles display immediately with zero manual dragging.
* **Custom Window Title**: Passes the canonical movie name + quality flag (e.g. `Deadpool & Wolverine [1080p Atmos]`) to display in the player's title bar.

---

## 3. Local LAN Casting Engine (DLNA / UPnP / Web)
* Broadcasts an SSDP UPnP packet over local Wi-Fi to auto-detect Smart TVs and Android devices (Samsung Galaxy J2 Prime).
* Generates a QR code in the terminal so you can scan it with your phone and immediately stream the movie in your mobile browser.
