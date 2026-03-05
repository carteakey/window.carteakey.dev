#!/usr/bin/env python3
"""window.carteakey.dev — live camera stream server."""

import json
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, send_from_directory

# ── Config ────────────────────────────────────────────────────────────────────
# Hardware H264 via rpicam-vid → ffmpeg HLS segmenter.
# h264_v4l2m2m is available but rpicam-vid already uses the Pi VPU internally.
# -c:v copy in ffmpeg passes the stream through without re-encoding.
# CPU: ~5-8% vs ~35% for software MJPEG.  Latency: ~6-8s (HLS buffer).
WIDTH    = 1920
HEIGHT   = 1080
FPS      = 30
BITRATE  = "4000000"   # 4 Mbps — excellent quality for 1080p
INTRA    = 60          # keyframe every 2s at 30fps (required for HLS cuts)
PORT     = 8765
LOCATION = "Toronto, Canada"
LAT, LON = 43.70, -79.42
SNAPSHOT_INTERVAL = 30   # seconds
HLS_DIR      = Path("static/hls")
SNAPSHOT_DIR = Path("static/snapshots")
TIMELAPSE_DIR = Path("static/timelapse")
MUSIC_DIR    = Path("static/music")
WEATHER_TTL  = 900  # 15 min cache

# ── Shared state ──────────────────────────────────────────────────────────────
viewer_count    = 0
viewer_lock     = threading.Lock()
stream_generation = 0
weather_cache: dict = {"data": None, "ts": 0.0}

app = Flask(__name__)


# ── Weather ───────────────────────────────────────────────────────────────────
WMO_DESC = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}

def fetch_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,weather_code"
        f"&daily=sunrise,sunset"
        f"&timezone=America%2FToronto&forecast_days=1"
    )
    with urllib.request.urlopen(url, timeout=5) as r:
        d = json.loads(r.read())
    c = d["current"]
    return {
        "temp": round(c["temperature_2m"]),
        "desc": WMO_DESC.get(c["weather_code"], ""),
        "sunrise": d["daily"]["sunrise"][0],
        "sunset":  d["daily"]["sunset"][0],
    }

def get_weather():
    now = time.time()
    if weather_cache["data"] and now - weather_cache["ts"] < WEATHER_TTL:
        return weather_cache["data"]
    try:
        data = fetch_weather()
        weather_cache["data"] = data
        weather_cache["ts"] = now
        return data
    except Exception:
        return weather_cache["data"] or {"temp": "--", "desc": "", "sunrise": None, "sunset": None}


# ── Capture thread: rpicam-vid → ffmpeg → HLS ─────────────────────────────────
def capture_thread():
    global stream_generation
    HLS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        cam = subprocess.Popen(
            [
                "rpicam-vid", "-t", "0",
                "--codec", "h264",
                "--width", str(WIDTH), "--height", str(HEIGHT),
                "--framerate", str(FPS),
                "--bitrate", BITRATE,
                "--intra", str(INTRA),
                "--nopreview",
                "-o", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        ffmpeg = subprocess.Popen(
            [
                "ffmpeg", "-y",
                "-i", "pipe:0",
                "-c:v", "copy",
                "-f", "hls",
                "-hls_time", "2",
                "-hls_list_size", "5",
                "-hls_flags", "delete_segments+append_list",
                "-hls_segment_filename", str(HLS_DIR / "seg%d.ts"),
                str(HLS_DIR / "stream.m3u8"),
            ],
            stdin=cam.stdout,
            stderr=subprocess.DEVNULL,
        )
        cam.stdout.close()  # let ffmpeg own the pipe
        stream_generation += 1

        ffmpeg.wait()
        cam.kill()
        time.sleep(2)


# ── Snapshot thread: extract frame from latest complete .ts segment ───────────
def snapshot_thread():
    # Wait for HLS to produce some segments before starting
    time.sleep(10)
    while True:
        time.sleep(SNAPSHOT_INTERVAL)
        ts_files = sorted(HLS_DIR.glob("seg*.ts"))
        if len(ts_files) < 2:
            continue
        src = ts_files[-2]  # second-to-last is always fully written

        today = datetime.now().strftime("%Y-%m-%d")
        ts    = datetime.now().strftime("%H%M%S")
        day_dir = SNAPSHOT_DIR / today
        day_dir.mkdir(parents=True, exist_ok=True)
        out = day_dir / f"{ts}.jpg"

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(src),
                "-vframes", "1",
                "-q:v", "2",
                str(out),
            ],
            timeout=10,
            stderr=subprocess.DEVNULL,
        )


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", location=LOCATION)


@app.route("/hls/<path:filename>")
def hls(filename):
    mime = "application/vnd.apple.mpegurl" if filename.endswith(".m3u8") else "video/mp2t"
    resp = send_from_directory(HLS_DIR, filename, mimetype=mime)
    resp.headers["Cache-Control"] = "no-cache, no-store"
    return resp


@app.route("/api/music")
def music_list():
    if not MUSIC_DIR.exists():
        return jsonify([])
    tracks = sorted(
        f.name for f in MUSIC_DIR.iterdir()
        if f.suffix.lower() in {".mp3", ".ogg", ".flac", ".wav", ".m4a"}
    )
    return jsonify(tracks)


@app.route("/api/weather")
def weather():
    return jsonify(get_weather())


@app.route("/api/viewers")
def viewers():
    with viewer_lock:
        return jsonify({"count": viewer_count, "gen": stream_generation})


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "window.carteakey.dev",
        "short_name": "window",
        "display": "fullscreen",
        "orientation": "landscape",
        "background_color": "#000000",
        "theme_color": "#000000",
        "start_url": "/",
    })


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    HLS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    TIMELAPSE_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    threading.Thread(target=capture_thread, daemon=True).start()
    threading.Thread(target=snapshot_thread, daemon=True).start()

    print(f"window.carteakey.dev running on http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
