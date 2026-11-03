# 📥 DOWNLOAD MANAGER & RESUMABLE 8-THREAD CHUNKS
### Multi-Part Parallel Chunk Downloader, State Persistence & Integrity Verification

---

## 1. High-Speed Chunk Downloading Architecture (`unshorten/downloader.py`)

To maximize download speeds across high-speed connections and prevent aborted downloads from restarting at 0%:

```
[ Total File: 4.0 GB ]
├─ Chunk 0: Bytes 0         ── 524,288,000      [ Worker 1 ] ──► part_0.tmp
├─ Chunk 1: Bytes 524,288,001 ── 1,048,576,000   [ Worker 2 ] ──► part_1.tmp
├─ Chunk 2: Bytes 1,048,576,001 ── 1,572,864,000 [ Worker 3 ] ──► part_2.tmp
├─ Chunk 3: Bytes 1,572,864,001 ── 2,097,152,000 [ Worker 4 ] ──► part_3.tmp
├─ Chunk 4: Bytes 2,097,152,001 ── 2,621,440,000 [ Worker 5 ] ──► part_4.tmp
├─ Chunk 5: Bytes 2,621,440,001 ── 3,145,728,000 [ Worker 6 ] ──► part_5.tmp
├─ Chunk 6: Bytes 3,145,728,001 ── 3,670,016,000 [ Worker 7 ] ──► part_6.tmp
└─ Chunk 7: Bytes 3,670,016,001 ── 4,294,967,296 [ Worker 8 ] ──► part_7.tmp
```

---

## 2. Pause & Resume State Persistence

Each active download creates a metadata state file: `movie_filename.mp4.state.json`:
```json
{
  "url": "https://cdn.hubcloud.club/file/abc1234.mp4",
  "total_bytes": 4294967296,
  "chunks": [
    {"index": 0, "start": 0, "end": 524288000, "downloaded": 524288000, "done": true},
    {"index": 1, "start": 524288001, "end": 1048576000, "downloaded": 312000000, "done": false},
    {"index": 2, "start": 1048576001, "end": 1572864000, "downloaded": 0, "done": false}
  ],
  "headers": {
    "Referer": "https://hubcloud.club/",
    "User-Agent": "Mozilla/5.0..."
  }
}
```

* **Instant Pause/Resume**: When the user pauses or restarts the computer, the downloader reads `state.json`, queries the server for the missing byte offsets, and resumes instantly without redownloading a single byte.
* **Disk Assembly**: Once all 8 temporary chunk files finish, the engine concatenates them in binary stream mode and deletes temporary `.tmp` files.
