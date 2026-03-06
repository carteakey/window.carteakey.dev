#!/usr/bin/env python3
"""
Generate daily timelapse MP4s from snapshots, then delete the raw JPEGs.

Run at midnight via systemd timer (window-timelapse.timer).
Skips today's folder — only processes completed past days.
"""

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

SNAPSHOT_DIR = Path("/home/pi/services/window.carteakey.dev/static/snapshots")
TIMELAPSE_DIR = Path("/home/pi/services/window.carteakey.dev/static/timelapse")
FPS = 24  # output timelapse framerate


def make_timelapse(day_dir: Path) -> bool:
    jpegs = sorted(day_dir.glob("*.jpg"))
    if len(jpegs) < 2:
        print(f"  skipping {day_dir.name}: only {len(jpegs)} frames")
        return False

    TIMELAPSE_DIR.mkdir(parents=True, exist_ok=True)
    out = TIMELAPSE_DIR / f"{day_dir.name}.mp4"

    if out.exists():
        print(f"  {out.name} already exists, skipping")
        return True

    print(f"  generating {out.name} from {len(jpegs)} frames …")

    # Write a concat list so ffmpeg gets frames in order without glob issues
    list_file = day_dir / "_list.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in jpegs)
    )

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            str(out),
        ],
        capture_output=True,
        timeout=600,
    )
    list_file.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  ERROR: ffmpeg failed for {day_dir.name}")
        print(result.stderr.decode()[-500:])
        return False

    size_mb = out.stat().st_size / 1e6
    print(f"  done → {out.name} ({size_mb:.1f} MB)")
    return True


def cleanup(day_dir: Path):
    removed = 0
    for jpg in day_dir.glob("*.jpg"):
        jpg.unlink()
        removed += 1
    day_dir.rmdir()
    print(f"  cleaned up {removed} snapshots from {day_dir.name}")


def main():
    today = date.today().isoformat()
    if not SNAPSHOT_DIR.exists():
        print("No snapshot directory found.")
        sys.exit(0)

    day_dirs = sorted(
        d for d in SNAPSHOT_DIR.iterdir()
        if d.is_dir() and d.name != today
    )

    if not day_dirs:
        print("Nothing to process.")
    else:
        print(f"Processing {len(day_dirs)} day(s) …")
        for d in day_dirs:
            print(f"\n[{d.name}]")
            success = make_timelapse(d)
            if success:
                cleanup(d)

    # Safety: delete snapshot dirs older than 30 days regardless
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    for d in sorted(SNAPSHOT_DIR.iterdir()):
        if d.is_dir() and d.name < cutoff and d.name != today:
            print(f"\n[{d.name}] Safety cleanup (>30 days old)")
            cleanup(d)

    print("\nDone.")


if __name__ == "__main__":
    main()
