import shutil
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
    jpegs = sorted(p for p in day_dir.glob("*.jpg") if p.stat().st_size > 0)
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

    log_file = day_dir / "_ffmpeg.log"
    with open(log_file, "w") as log:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin",
                "-r", str(FPS),
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-vf", "format=yuv420p",
                "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast",
                str(out),
            ],
            stdout=log,
            stderr=log,
            timeout=1800,
        )
    list_file.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  ERROR: ffmpeg failed for {day_dir.name}")
        if log_file.exists():
            print(log_file.read_text()[-500:])
        return False
    log_file.unlink(missing_ok=True)

    size_mb = out.stat().st_size / 1e6
    print(f"  done → {out.name} ({size_mb:.1f} MB)")

    # Archival to Glowdesk NAS if mounted
    nas_archive = Path("/mnt/storage/archive/window-cam/timelapse")
    if nas_archive.is_dir():
        try:
            shutil.copy2(out, nas_archive / out.name)
            print(f"  archived to NAS → {nas_archive / out.name}")
        except Exception as e:
            print(f"  NAS archive warning: {e}")

    return True


def cleanup(day_dir: Path):
    shutil.rmtree(day_dir)
    print(f"  cleaned up snapshots from {day_dir.name}")


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
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    for d in sorted(SNAPSHOT_DIR.iterdir()):
        if d.is_dir() and d.name < cutoff and d.name != today:
            print(f"\n[{d.name}] Safety cleanup (>30 days old)")
            cleanup(d)

    print("\nDone.")


if __name__ == "__main__":
    main()
