# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A window-swap.com-style live camera site running on a Raspberry Pi 4B with an OV5647 CSI camera module. Publicly served at `window.carteakey.dev` via Cloudflare Tunnel → localhost:8765.

## Running and reloading

```bash
# Apply code changes
sudo systemctl restart window-cam

# View live logs
journalctl -u window-cam -f

# Run timelapse manually (normally fires at 00:05 via systemd timer)
python3 make_timelapse.py

# Run development server directly (kills the service first)
sudo systemctl stop window-cam && python3 app.py
```

## Architecture

### Stream pipeline
`rpicam-vid` (hardware H264 VPU, 1080p@30fps) → stdout pipe → `ffmpeg` (HLS segmenter) → `static/hls/` → hls.js in browser.

- **No re-encoding**: ffmpeg uses `-c:v copy`, zero CPU for encoding
- **Segments**: 2s each, rolling 5-segment window, `delete_segments+append_list`
- **Latency**: ~6-8s (HLS buffer)
- Cloudflare Tunnel serves static `.ts` files — compliant with ToS (no raw streaming)

### Idle management
The stream only runs when viewers are present:
- Frontend sends `POST /api/heartbeat` with a session ID every 30s
- `watchdog_thread` prunes stale sessions and kills `rpicam-vid`+`ffmpeg` after `IDLE_TIMEOUT` (120s) with no active viewers
- `capture_thread` blocks on `stream_active` Event, wakes on first heartbeat
- `snapshot_thread` skips extraction when `stream_active` is not set

### Snapshot pipeline
`snapshot_thread` extracts frames from `ts_files[-2]` (second-to-last .ts segment — always fully written) via `ffmpeg -vframes 1`. Saves to `static/snapshots/YYYY-MM-DD/HHMMSS.jpg` every 30s. No stream pause needed.

### Key threads
| Thread | Purpose |
|---|---|
| `capture_thread` | Manages rpicam-vid + ffmpeg processes |
| `watchdog_thread` | Kills stream after idle, prunes viewer sessions |
| `snapshot_thread` | Extracts JPEGs from HLS segments |

### Config constants (top of `app.py`)
```python
WIDTH, HEIGHT = 1920, 1080
FPS = 30
BITRATE = "4000000"   # 4 Mbps
INTRA = 60            # keyframe every 2s at 30fps
PORT = 8765
IDLE_TIMEOUT = 120    # seconds
VIEWER_TTL = 60       # heartbeat expiry
RECORD_DURATION = 600 # 10-min WindowSwap clip
```

## Key files

| File | Role |
|---|---|
| `app.py` | Flask app — all routes, threads, stream management |
| `templates/index.html` | Full UI (single file — CSS + HTML + JS) |
| `templates/timelapse.html` | Timelapse viewer page |
| `make_timelapse.py` | Daily timelapse generator + 30-day snapshot cleanup |
| `window-cam.service` | Systemd service (always-restart) |
| `window-timelapse.timer` | Fires `make_timelapse.py` at 00:05 daily |

## API routes

| Route | Purpose |
|---|---|
| `GET /hls/<file>` | Serve HLS segments (no-cache headers) |
| `POST /api/heartbeat` | Register viewer session, wake stream |
| `GET /api/viewers` | `{count, gen, streaming}` |
| `GET /api/weather` | open-meteo.com, 15-min cache |
| `GET /api/snapshots` | List days with picture-of-day (noon-closest) |
| `GET /api/snapshots/<date>` | All JPEGs for a date |
| `GET /api/timelapse` | List MP4s with `{date, file, size_mb}` |
| `GET /api/disk` | `{snapshots_mb, timelapse_mb, music_mb, free_gb, total_gb}` |
| `POST /api/record` | Start 10-min WindowSwap clip recording |
| `GET /api/record/status` | `{status, progress, file, error}` |
| `GET /api/record/download/<file>` | Download recorded clip |

## Static directories (gitignored)

```
static/hls/          # Live HLS segments (transient)
static/snapshots/    # YYYY-MM-DD/HHMMSS.jpg
static/timelapse/    # YYYY-MM-DD.mp4
static/music/        # MP3s served to frontend player
static/recordings/   # WindowSwap submission clips
```

## Timelapse generation

`make_timelapse.py` runs at 00:05 daily:
1. For each past day's snapshot dir: writes `_list.txt` concat file → `ffmpeg libx264 -crf 23` → `static/timelapse/YYYY-MM-DD.mp4`
2. On success: deletes all JPEGs and removes the day directory
3. Safety cleanup: deletes snapshot dirs older than 30 days regardless

## Hardware notes

- Camera: OV5647 (Pi Camera Module v1), accessed via `rpicam-vid` (libcamera stack, NOT legacy v4l2)
- Hardware encoder: Pi 4B VPU via rpicam-vid's internal H264 encoder
- Do NOT revert to MJPEG — software encoding was 89% CPU at 1080p30
- CPU at idle (stream paused): ~0%. CPU while streaming: ~38% total
