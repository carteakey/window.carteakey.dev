#!/usr/bin/env python3
"""window.carteakey.dev — live camera stream server."""

import json
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template

# ── Config ────────────────────────────────────────────────────────────────────
# 1080p@15fps: MJPEG is software-encoded on Pi 4B (~35% CPU). Hardware MJPEG
# is possible via /dev/video11 (mjpeg_v4l2m2m) but needs a 2-process pipeline.
# Hardware H264→HLS (~3% CPU) is the cleanest path but adds 5-10s latency.
# With fan installed temps drop to ~45°C — this config is stable as-is.
WIDTH = 1920
HEIGHT = 1080
FPS = 15
PORT = 8765
LOCATION = "Toronto, Canada"
LAT, LON = 43.70, -79.42
SNAPSHOT_INTERVAL = 30  # seconds
SNAPSHOT_DIR = Path("static/snapshots")
TIMELAPSE_DIR = Path("static/timelapse")
MUSIC_DIR = Path("static/music")
WEATHER_TTL = 900  # 15 min cache

# ── Shared state ──────────────────────────────────────────────────────────────
current_frame: bytes | None = None
frame_lock = threading.Lock()
frame_event = threading.Event()

camera_proc: subprocess.Popen | None = None
snapshot_in_progress = threading.Event()  # set while rpicam-still is running

viewer_count = 0
viewer_lock = threading.Lock()

stream_generation = 0  # increments each time rpicam-vid restarts

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
    daily = d["daily"]
    return {
        "temp": round(c["temperature_2m"]),
        "desc": WMO_DESC.get(c["weather_code"], ""),
        "sunrise": daily["sunrise"][0],
        "sunset":  daily["sunset"][0],
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


# ── Camera capture thread ─────────────────────────────────────────────────────
def capture_thread():
    global current_frame, camera_proc
    cmd = [
        "rpicam-vid",
        "-t", "0",
        "--codec", "mjpeg",
        "--width", str(WIDTH),
        "--height", str(HEIGHT),
        "--framerate", str(FPS),
        "--nopreview",
        "-o", "-",
    ]
    while True:
        # Wait if a snapshot is being taken
        while snapshot_in_progress.is_set():
            time.sleep(0.2)

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        camera_proc = proc
        global stream_generation
        stream_generation += 1
        buf = b""
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    start = buf.find(b"\xff\xd8")
                    end = buf.find(b"\xff\xd9", start + 2)
                    if start == -1 or end == -1:
                        break
                    frame = buf[start: end + 2]
                    buf = buf[end + 2:]
                    with frame_lock:
                        current_frame = frame
                    frame_event.set()
                    frame_event.clear()
        except Exception:
            pass
        finally:
            proc.kill()
            camera_proc = None
        time.sleep(2)


# ── Snapshot thread (full-res via rpicam-still) ───────────────────────────────
def snapshot_thread():
    while True:
        time.sleep(SNAPSHOT_INTERVAL)

        # Signal capture_thread to not restart while we use the camera
        snapshot_in_progress.set()

        # Terminate the running stream
        proc = camera_proc
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

        try:
            today = datetime.now().strftime("%Y-%m-%d")
            ts = datetime.now().strftime("%H%M%S")
            day_dir = SNAPSHOT_DIR / today
            day_dir.mkdir(parents=True, exist_ok=True)
            out = day_dir / f"{ts}.jpg"

            subprocess.run(
                [
                    "rpicam-still",
                    "-o", str(out),
                    "--width", "2592",
                    "--height", "1944",
                    "--timeout", "1500",
                    "--nopreview",
                ],
                timeout=8,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
        finally:
            # Release camera — capture_thread will restart the stream
            snapshot_in_progress.clear()


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", location=LOCATION)


def generate_stream():
    global viewer_count
    with viewer_lock:
        viewer_count += 1
    try:
        while True:
            frame_event.wait(timeout=2)
            with frame_lock:
                frame = current_frame
            if frame is None:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame
                + b"\r\n"
            )
    finally:
        with viewer_lock:
            viewer_count -= 1


@app.route("/stream")
def stream():
    return Response(
        generate_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "Connection": "close"},
    )


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
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    TIMELAPSE_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    threading.Thread(target=capture_thread, daemon=True).start()
    threading.Thread(target=snapshot_thread, daemon=True).start()

    print(f"window.carteakey.dev running on http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
