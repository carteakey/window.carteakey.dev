# window.carteakey.dev — Phase 2 TODO

## Timelapse
- [ ] Daily timelapse generation: ffmpeg glob of `static/snapshots/YYYY-MM-DD/*.jpg` → `static/timelapse/YYYY-MM-DD.mp4`
      (ref: /home/pi/repos/rpi-usb-webcam/make-timelapse.sh for ffmpeg pattern)
- [ ] Systemd timer (or cron) to run generation at midnight each day
- [ ] After timelapse is confirmed good, delete raw snapshots for that day to save disk
- [ ] Timelapse viewer page at `/timelapse` — list + playable MP4s

## Snapshot quality upgrade
- [ ] Option to capture full-res 2592x1944 snapshots via `rpicam-still` on a separate interval
        (requires pausing stream briefly — evaluate if acceptable)

## WindowSwap submission helper
- [ ] One-click "record 10-min clip" button that captures the submission video WindowSwap requires
- [ ] Progress indicator + download link when done

## Hardware encoding (when fan is installed)
- [ ] Hardware H264 → HLS: `rpicam-vid --codec h264` → ffmpeg HLS segments → hls.js frontend
      (~3% CPU, 5-10s latency, fully hardware accelerated via h264_v4l2m2m)
- [ ] OR: hardware MJPEG via /dev/video11 (mjpeg_v4l2m2m) — zero latency, ~5% CPU
      pipeline: `rpicam-vid --codec yuv420 | ffmpeg -c:v mjpeg_v4l2m2m -f mpjpeg`

## Misc
- [ ] Show snapshot count / last snapshot time in UI (small indicator)
- [ ] Disk usage monitor — alert when snapshots folder exceeds threshold
- [ ] Config file (YAML/TOML) instead of hardcoded values in app.py
