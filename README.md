# window.carteakey.dev

A live 24/7 window camera stream and automated timelapse generator running on a Raspberry Pi 4B with an OV5647 CSI camera module.

Served privately across LAN and Tailscale via Flask, piping hardware-encoded H264 into an HLS segmenter for playback in modern browsers.

## Access

* **Tailscale (Private):** `http://100.126.76.57:8765`
* **LAN:** `http://192.168.0.85:8765`

## Features

- **Hardware Accelerated H264 Streaming**: Camera VPU encodes 1080p @ 30fps H264 directly, ffmpeg copies stream without CPU re-encoding (~38% total CPU).
- **HLS Segmenter**: 2-second segments with rolling buffer for smooth playback and low latency (~6–8s).
- **Idle Stream Management**: Stream activates only when client heartbeats are received. Automatically pauses camera and ffmpeg after 120s with no active viewers.
- **Automated Snapshots & Timelapses**: Captures frames every 30s; nightly systemd timer compiles day's frames into a 24fps MP4 timelapse and clears raw JPEGs.
- **External USB Storage**: High-frequency snapshot writes offloaded to dedicated USB drive (`CASEY`).
- **Interactive Web Player**: Auto-fading HUD, live Toronto weather from Open-Meteo, ambient music player, and full-resolution snapshot viewer.

## Hardware & System Requirements

### 1. GPU Memory (`gpu_mem=128`)
On Raspberry Pi 4 running Debian 12 Bookworm (64-bit), the hardware camera pipeline (`libcamera` / `rpicam-apps` with `bcm2835-isp`) communicates with the VideoCore firmware via VCHI.
* **Mandatory Setting**: `/boot/firmware/config.txt` must have `gpu_mem=128`.
* **Warning**: Reducing `gpu_mem` to `16MB` (e.g. during headless server memory tuning) causes firmware to disable the VCHI MMAL/ISP camera interface (`status=-22`), breaking `bcm2835-isp` and causing `rpicam-vid` to fail with `ERROR: rpicam-apps currently only supports the Raspberry Pi platforms.`

### 2. External USB Storage (`/media/pi/CASEY`)
High-frequency write paths are symlinked to prevent SD/OS drive wear:
* `static/snapshots` -> `/media/pi/CASEY/snapshots`
* `static/timelapse` -> `/media/pi/CASEY/timelapse`

Configured in `/etc/fstab`:
```text
UUID=AE63-588B  /media/pi/CASEY  vfat  defaults,nofail,uid=1000,gid=1000  0  2
```

## Service Management

```bash
# Restart stream server
sudo systemctl restart window-cam.service

# View live stream logs
journalctl -u window-cam.service -f

# Manually trigger timelapse compilation
python3 make_timelapse.py

# Check timer status
systemctl status window-timelapse.timer
```

## Troubleshooting

- **Web player serving stale/repeating video:**
  If `rpicam-vid` was offline or halted while old `.ts` files lingered in `static/hls/`, clients may replay the cached segments. Flush the directory and restart:
  ```bash
  rm -rf static/hls/*
  sudo systemctl restart window-cam.service
  ```
- **Camera not detected:**
  Run `rpicam-hello --list-cameras`. If empty, verify `gpu_mem=128` in `/boot/firmware/config.txt` and check `dmesg | grep -i isp`.
