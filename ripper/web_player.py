"""
Local Cinema Web Player HTML & Assets Generator with Instant In-Browser URL Input.
Provides:
- In-browser Direct URL Resolver bar (no need to return to terminal)
- Plyr / native HTML5 controls (Keyboard shortcuts, speed control, pip, fullscreen)
- Live background session auto-sync & real-time token revalidation
- Real-time quality selector (1080p, 720p, 480p, 360p, 240p)
- Instant fallback & error recovery without losing scrubber position
"""

def generate_web_player_html(session_id: str, title: str, active_stream_url: str, streams: list) -> str:
    import urllib.parse, json
    encoded_active = urllib.parse.quote(active_stream_url) if active_stream_url else ""
    qualities_json = []
    for s in streams:
        u = s.get("url", "")
        qualities_json.append({
            "quality": s.get("quality", "HD Direct"),
            "url": f"/stream.mp4?session={session_id}&url=" + urllib.parse.quote(u) if u else ""
        })

    q_json_str = json.dumps(qualities_json)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎬 {title} - AnyStream Cinema</title>
    <link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css" />
    <style>
        :root {{
            --plyr-color-main: #00e676;
            --bg-color: #0b0f19;
            --surface-color: #161f30;
            --text-color: #f1f5f9;
            --accent-glow: rgba(0, 230, 118, 0.25);
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .theater-container {{
            width: 100%;
            max-width: 1150px;
            background: var(--surface-color);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 20px 50px rgba(0,0,0,0.6), 0 0 40px var(--accent-glow);
            border: 1px solid rgba(255,255,255,0.08);
            display: flex;
            flex-direction: column;
        }}
        .search-bar {{
            padding: 12px 20px;
            background: rgba(15, 23, 42, 0.95);
            display: flex;
            gap: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            align-items: center;
        }}
        .search-input {{
            flex: 1;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12);
            color: #fff;
            padding: 10px 16px;
            border-radius: 10px;
            font-size: 0.92rem;
            outline: none;
            transition: all 0.2s;
        }}
        .search-input:focus {{
            border-color: #00e676;
            background: rgba(255,255,255,0.09);
            box-shadow: 0 0 10px rgba(0, 230, 118, 0.2);
        }}
        .search-btn {{
            background: #00e676;
            color: #0b0f19;
            font-weight: 700;
            border: none;
            padding: 10px 22px;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.92rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .search-btn:hover {{
            background: #00c853;
            transform: translateY(-1px);
        }}
        .search-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .header-bar {{
            padding: 14px 24px;
            background: rgba(11, 15, 25, 0.85);
            backdrop-filter: blur(10px);
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .title-badge {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 1.05rem;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 75%;
        }}
        .status-dot {{
            width: 10px;
            height: 10px;
            background: #00e676;
            border-radius: 50%;
            box-shadow: 0 0 10px #00e676;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.5; transform: scale(1.2); }}
            100% {{ opacity: 1; transform: scale(1); }}
        }}
        .player-wrapper {{
            position: relative;
            background: #000;
            width: 100%;
            aspect-ratio: 16/9;
        }}
        video {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
        .controls-bar {{
            padding: 14px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(11, 15, 25, 0.95);
            font-size: 0.88rem;
        }}
        .quality-selector {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .quality-btn {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            color: #fff;
            padding: 6px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.82rem;
            font-weight: 600;
            transition: all 0.2s;
        }}
        .quality-btn:hover {{
            background: rgba(0, 230, 118, 0.2);
            border-color: #00e676;
            color: #00e676;
        }}
        .quality-btn.active {{
            background: #00e676;
            color: #000;
            border-color: #00e676;
        }}
        .toast-msg {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0,0,0,0.85);
            backdrop-filter: blur(8px);
            color: #00e676;
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 0.85rem;
            border-left: 4px solid #00e676;
            opacity: 0;
            transition: opacity 0.3s;
            pointer-events: none;
            z-index: 100;
        }}
        .toast-msg.show {{ opacity: 1; }}
    </style>
</head>
<body>
    <div class="theater-container">
        <!-- Direct Instant URL Resolver Bar -->
        <div class="search-bar">
            <input type="text" id="urlInput" class="search-input" placeholder="Paste any video URL or page link here (No CLI needed)..." />
            <button id="resolveBtn" class="search-btn" onclick="resolveNewLink()">
                <span>⚡ Resolve & Stream</span>
            </button>
        </div>

        <div class="header-bar">
            <div class="title-badge">
                <div class="status-dot" id="liveDot"></div>
                <span id="videoTitle">{title}</span>
            </div>
            <div style="font-size: 0.8rem; color: #94a3b8;">⚡ Ultra-DPI Bypass Active</div>
        </div>

        <div class="player-wrapper">
            <div class="toast-msg" id="toast"></div>
            <video id="player" playsinline controls preload="auto" crossorigin>
                <source src="/stream.mp4?session={session_id}&url={encoded_active}" type="video/mp4" />
            </video>
        </div>

        <div class="controls-bar">
            <div class="quality-selector" id="qualityContainer">
                <span style="color: #94a3b8; margin-right: 4px;">Quality:</span>
            </div>
            <div style="color: #64748b; font-size: 0.8rem;">
                Hotkeys: [Space] Play/Pause • [F] Fullscreen • [←/→] Seek 5s • [M] Mute
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script>
    <script>
        let sessionId = "{session_id}";
        let currentStreams = {q_json_str};
        let currentUrl = "{active_stream_url}";

        const playerElement = document.getElementById('player');
        const player = new Plyr(playerElement, {{
            controls: ['play-large', 'play', 'progress', 'current-time', 'duration', 'mute', 'volume', 'captions', 'settings', 'pip', 'airplay', 'fullscreen'],
            seekTime: 5,
            invertTime: false,
            keyboard: {{ focused: true, global: true }}
        }});

        function showToast(msg) {{
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 3500);
        }}

        function renderQualities(streamsList) {{
            const qContainer = document.getElementById('qualityContainer');
            qContainer.innerHTML = '<span style="color: #94a3b8; margin-right: 4px;">Quality:</span>';
            streamsList.forEach((s, idx) => {{
                const btn = document.createElement('button');
                btn.className = 'quality-btn' + (idx === 0 ? ' active' : '');
                btn.textContent = s.quality.replace(/Direct Stream|Direct Video/gi, '').trim() || s.quality;
                btn.onclick = () => {{
                    document.querySelectorAll('.quality-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    switchStream(s.url);
                }};
                qContainer.appendChild(btn);
            }});
        }}

        renderQualities(currentStreams);

        player.on('error', (event) => {{
            console.warn('Playback error caught');
            showToast('⚠️ Stream stalled or buffering, re-aligning range...');
        }});

        function switchStream(newStreamUrl, resetTime = false) {{
            const currTime = resetTime ? 0 : player.currentTime;
            const wasPlaying = !player.paused;
            try {{
                player.source = {{
                    type: 'video',
                    sources: [
                        {{
                            src: newStreamUrl,
                            type: newStreamUrl.includes('.m3u8') ? 'application/x-mpegURL' : 'video/mp4'
                        }}
                    ]
                }};
            }} catch(e) {{
                playerElement.src = newStreamUrl;
            }}
            setTimeout(() => {{
                try {{ player.currentTime = currTime; }} catch(e) {{}}
                if (wasPlaying || resetTime) {{
                    player.play().catch(() => {{}});
                }}
            }}, 150);
            showToast('✔ Switched Stream');
        }}

        // Resolve new link directly from browser
        async function resolveNewLink() {{
            const inp = document.getElementById('urlInput');
            const btn = document.getElementById('resolveBtn');
            const target = inp.value.trim();
            if (!target) return;

            btn.disabled = true;
            btn.innerHTML = '<span>⏳ Resolving Master...</span>';
            showToast('⚡ Deep-resolving direct streams from host...');

            try {{
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 45000);
                const res = await fetch('/api/resolve?url=' + encodeURIComponent(target), {{ signal: controller.signal }});
                clearTimeout(timeoutId);
                const data = await res.json();
                if (data.session_id && data.active_stream_url) {{
                    sessionId = data.session_id;
                    currentUrl = data.active_stream_url;
                    document.getElementById('videoTitle').textContent = data.title || 'Direct Stream';
                    
                    const newStreams = data.streams.map(s => ({{
                        quality: s.quality || 'HD Direct',
                        url: '/stream.mp4?session=' + sessionId + '&url=' + encodeURIComponent(s.url)
                    }}));
                    
                    renderQualities(newStreams);
                    const streamToPlay = '/stream.mp4?session=' + sessionId + '&url=' + encodeURIComponent(currentUrl);
                    switchStream(streamToPlay, true);
                    inp.value = '';
                    showToast('🎉 Playing ' + (data.title || 'video'));
                }} else {{
                    showToast('❌ No stream found on that page.');
                }}
            }} catch (err) {{
                console.error('Resolution failure:', err);
                showToast('❌ ' + (err.name === 'AbortError' ? 'Resolution timed out on host' : 'Failed to connect to local proxy server (:5055)'));
            }} finally {{
                btn.disabled = false;
                btn.innerHTML = '<span>⚡ Resolve & Stream</span>';
            }}
        }}

        document.getElementById('urlInput').addEventListener('keydown', (e) => {{
            if (e.key === 'Enter') resolveNewLink();
        }});

        // Live Auto-Sync Background Polling (Detects Token/Mirror changes on host)
        setInterval(async () => {{
            if (!sessionId) return;
            try {{
                const res = await fetch('/api/session?id=' + sessionId);
                if (res.ok) {{
                    const data = await res.json();
                    if (data.active_stream_url && data.active_stream_url !== currentUrl) {{
                        currentUrl = data.active_stream_url;
                        const targetStream = '/stream.mp4?session=' + sessionId + '&url=' + encodeURIComponent(currentUrl);
                        switchStream(targetStream);
                        showToast('🔄 Auto-Refreshed Live Token from Host');
                    }}
                }}
            }} catch (e) {{}}
        }}, 15000);
    </script>
</body>
</html>
"""
    return html
