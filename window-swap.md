# Building My Own WindowSwap

I've been a fan of [WindowSwap](https://window-swap.com) for a while — the idea is simple and kind of beautiful. Someone points a camera out their window, streams it to the internet, and strangers get to borrow that view for a few minutes. A slice of someone else's world.

So I built my own.

## The Hardware

A **Raspberry Pi 4B** sitting on my desk with an **OV5647 camera module** (the original Pi cam, 5MP) pointed out the window. The view: a busy Toronto intersection, a parking lot, some trees, a radio tower in the distance. Rainy March day vibes.

Getting the camera working took about ten minutes. The lens ships slightly out of focus — you have to crack the glue seal and twist the lens ring by hand until the image snaps in. Worth it.

## Streaming

The Pi runs a Python/Flask server that pipes `rpicam-vid` output as an MJPEG stream. Each client gets the same pre-encoded frame via a shared `threading.Event` — so CPU usage is flat regardless of viewer count. The real bottleneck is upstream bandwidth, not the Pi.

MJPEG at 1080p is software-encoded on the Pi 4B (the VPU only hardware-accelerates H264). Running at 15fps keeps CPU around 35% and the stream latency at near-zero, which matters more than framerate for a window view.

## The Site

Full-viewport stream, auto-hiding UI. When you move your mouse it fades in:

- Current Toronto time and date
- Live weather from [open-meteo](https://open-meteo.com) (free, no API key)
- Viewer count
- A music player — shuffled playlist, SVG controls, volume slider
- Pulsing live dot

Everything rides on a Cloudflare tunnel. No port forwarding, no exposed IP, no headache.

## Snapshots and Timelapse

Every 30 seconds the server briefly pauses the stream, fires `rpicam-still` at full **2592×1944** resolution, then restarts. Clients auto-reconnect seamlessly. The snapshots accumulate in dated folders and get compiled into daily timelapse MP4s at midnight — so at the end of each day there's a compressed record of whatever happened outside the window.

## What's Next

Hardware H264 encoding via `h264_v4l2m2m` would drop CPU to ~3% and let the stream run at 30fps comfortably. The latency tradeoff (HLS adds ~8 seconds) is acceptable for a window view — nobody needs sub-second latency to watch pigeons.

The plan is to submit a clip to the actual WindowSwap community once the view is framed properly. In the meantime it lives at [window.carteakey.dev](https://window.carteakey.dev).

Code on GitHub soon.
