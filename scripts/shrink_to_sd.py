#!/usr/bin/env python3
"""Pull episodes from the Jellyfin host, re-encode them small, write to the SD card.

The card is a 32 GB FAT32 SDHC for a car DVD head unit, which plays H.264 + AAC
mp4. Sources total ~32 GB at full quality, so everything is re-encoded with CRF
to fit with room to spare. Animation at 480p/CRF 25 holds up fine on a car screen.

Card layout (kept identical to what already works on that player):
    Bluey/Season_<s>_Episode_<n>.mp4
    Clifford/Episode_<nn>.mp4
    PuppyDays/Episode_<nn>.mp4

Resumable: an episode is skipped once its output exists and is non-trivial.
Each source is copied to a temp file, encoded, then the temp is removed, so peak
local disk use stays at one episode.
"""
import os
import re
import shutil
import subprocess
import sys

HOST = "root@192.168.8.114"
KEY = os.path.expanduser("~/.ssh/id_ecdsa")
SRC_ROOT = "/srv/media/tv"
CARD = sys.argv[1] if len(sys.argv) > 1 else "/Volumes/SANTIAGO_SH"
TMP = "/tmp/shrink_work"

CRF = "25"          # animation at 480p: visually fine, big size win
AUDIO_KBPS = "96k"
MAX_WIDTH = 720     # never upscale; leaves native 720x480 untouched

SHOWS = [
    # (jellyfin dir,                    card dir,     naming)
    ("Bluey",                     "Bluey",      "bluey"),
    ("Clifford the Big Red Dog",  "Clifford",   "flat"),
    ("Clifford's Puppy Days",     "PuppyDays",  "flat"),
]


def ssh(cmd):
    return subprocess.check_output(
        ["ssh", "-i", KEY, "-o", "ConnectTimeout=10", HOST, cmd]
    ).decode()


def list_sources(show_dir):
    """Return [(remote_path, season, episode)] sorted by season then episode."""
    out = ssh(f'find "{SRC_ROOT}/{show_dir}" -name "*.mp4" -print0 | tr "\\0" "\\n"')
    items = []
    for path in out.splitlines():
        if not path.strip():
            continue
        m = re.search(r"S(\d+)E(\d+)", os.path.basename(path))
        if not m:
            continue
        items.append((path, int(m.group(1)), int(m.group(2))))
    items.sort(key=lambda t: (t[1], t[2]))
    return items


def card_name(naming, season, episode, seq):
    if naming == "bluey":
        return f"Season_{season}_Episode_{episode}.mp4"
    return f"Episode_{seq:02d}.mp4"


def encode(src, dst):
    """Re-encode to H.264 + AAC, capped at MAX_WIDTH, preserving aspect."""
    tmp_out = dst + ".part.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
        "-map", "0:v:0", "-c:v", "libx264", "-preset", "veryfast",
        "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
        "-crf", CRF, "-maxrate", "1200k", "-bufsize", "2400k",
        # scale down to MAX_WIDTH only if wider; -2 keeps height even
        "-vf", f"scale='min({MAX_WIDTH},iw)':-2",
        "-map", "0:a:0", "-c:a", "aac", "-b:a", AUDIO_KBPS, "-ac", "2",
        "-movflags", "+faststart", tmp_out,
    ]
    subprocess.check_call(cmd)
    os.replace(tmp_out, dst)


def main():
    os.environ["COPYFILE_DISABLE"] = "1"   # no ._ sidecars on the card
    os.makedirs(TMP, exist_ok=True)
    total_ok = 0
    total_fail = 0

    manifest = os.path.join(CARD, ".shrunk_manifest.txt")
    done = set()
    if os.path.exists(manifest):
        with open(manifest) as fh:
            done = {line.strip() for line in fh if line.strip()}
    print(f"already shrunk: {len(done)}", flush=True)

    for show_dir, card_dir, naming in SHOWS:
        dest_dir = os.path.join(CARD, card_dir)
        os.makedirs(dest_dir, exist_ok=True)
        sources = list_sources(show_dir)
        print(f"\n=== {show_dir}: {len(sources)} episodes -> {card_dir}/", flush=True)

        for seq, (remote, season, episode) in enumerate(sources, 1):
            name = card_name(naming, season, episode, seq)
            dst = os.path.join(dest_dir, name)
            # Only a manifest entry proves WE encoded it. Pre-existing files are
            # full-size originals and must be re-encoded (overwritten in place),
            # and their size alone cannot distinguish them from a CRF output.
            key = f"{card_dir}/{name}"
            if key in done and os.path.exists(dst):
                continue

            local = os.path.join(TMP, "src.mp4")
            try:
                subprocess.check_call(
                    ["scp", "-i", KEY, "-q", f"{HOST}:{remote}", local])
                before = os.path.getsize(local)
                encode(local, dst)
                after = os.path.getsize(dst)
                total_ok += 1
                done.add(key)
                with open(manifest, "a") as fh:      # append as we go, so a
                    fh.write(key + "\n")             # kill mid-run loses nothing
                print(f"[{seq}/{len(sources)}] {name}  "
                      f"{before/1e6:.0f}MB -> {after/1e6:.0f}MB", flush=True)
            except subprocess.CalledProcessError as e:
                total_fail += 1
                print(f"[{seq}/{len(sources)}] FAIL {name}: {e}", flush=True)
            finally:
                if os.path.exists(local):
                    os.remove(local)

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\nDONE ok={total_ok} fail={total_fail}", flush=True)


if __name__ == "__main__":
    main()
