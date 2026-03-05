# Building My Own WindowSwap

I've been a fan of [WindowSwap](https://window-swap.com) for a while — the idea is simple and kind of beautiful. Someone points a camera out their window, streams it to the internet, and strangers get to borrow that view for a few minutes. A slice of someone else's world.

So I built my own.

## The Hardware

A **Raspberry Pi 4B** sitting on my desk with an **OV5647 camera module** (the original Pi cam, 5MP) pointed out the window. The view: a busy Toronto intersection, a parking lot, some trees, a radio tower in the distance. Rainy March day vibes.

Getting the camera working took about ten minutes. The lens ships slightly out of focus — you have to crack the glue seal and twist the lens ring by hand until the image snaps in. Worth it.

## Streaming

The Pi runs a Python/Flask server that pipes `rpicam-vid` output through `ffmpeg` into an HLS stream. The camera's VPU hardware-encodes H264 directly — the CPU just shuttles bytes into segment files. Total CPU across both processes: ~38%. Temperature with no fan: ~78°C. Fine. With a fan: ~45°C.

The HLS segments (`static/hls/seg*.ts`) are 2 seconds each, rolling window of 5. `ffmpeg` deletes old ones automatically. The frontend uses `hls.js` for playback with built-in error recovery — if the stream hiccups, it resumes seamlessly from the buffer. Latency is ~6-8 seconds, which is irrelevant for a window view.

This approach also happens to be Cloudflare Tunnel ToS compliant. Raw video streaming over tunnels is not — but serving 2MB static files every 2 seconds is just normal web traffic.

## The Site

Full-viewport stream, auto-hiding UI. When you move your mouse it fades in:

- Current Toronto time and date
- Live weather from [open-meteo](https://open-meteo.com) (free, no API key)
- Viewer count
- A music player — shuffled playlist, SVG controls, volume slider
- Pulsing live dot

Everything rides on a Cloudflare tunnel. No port forwarding, no exposed IP, no headache.

## Snapshots and Timelapse

Every 30 seconds a background thread pulls the second-to-last `.ts` segment (which is always fully written) and extracts one frame with `ffmpeg`. No stream interruption. The snapshots go into `static/snapshots/YYYY-MM-DD/HHMMSS.jpg`.

At midnight a systemd timer runs `make_timelapse.py`, which walks every completed day's folder, feeds the JPEGs to `ffmpeg` as a concat list, and outputs a `libx264` MP4 at 24fps. After confirming the file is good, it deletes the raw JPEGs. The timelapse for a full day of 30-second snapshots — 2880 frames — compresses down to a few hundred MB.

## What's Next

Submitting a clip to the actual WindowSwap community. Their submission format requires a 10-minute window video, which is straightforward to generate from the HLS stream. After that, mostly just leaving it running and seeing what the timelapses look like across seasons.

It lives at [window.carteakey.dev](https://window.carteakey.dev).

Code on GitHub soon.
