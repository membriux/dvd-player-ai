#!/usr/bin/env python3
"""Convert episodes from the Jellyfin host into Xvid AVI for a SUNPIN PD969.

That player has no H.264 decoder. Feeding it H.264/AAC in MP4 makes the firmware
fault with error 814E and reboot, even with a single file on the card. Sunpin's
own FAQ lists the supported set as VOB/AVI/MPEG-1/MPEG-2/MPEG-4/XVID video with
MP3 or WMA audio, and caps resolution at 720x576. So: MPEG-4 Part 2 (Xvid) video
+ MP3 audio in an AVI container, at 720x480.

Bitrate calibrated on a 26-minute episode: 700k video + 96k audio -> ~161 MB,
which puts all 274 episodes near 24 GB and inside a 32 GB card.

Usage:
    python3 to_sunpin_avi.py <card_path> [--show bluey|clifford|puppydays|all]
                             [--limit N] [--season S]

Resumable: an episode already present on the card at a plausible size is skipped.
"""
import argparse
import os
import re
import subprocess

HOST = "root@192.168.8.114"
KEY = os.path.expanduser("~/.ssh/id_ecdsa")
SRC_ROOT = "/srv/media/tv"
TMP = "/tmp/sunpin_work"

VIDEO_KBPS = "700k"
MAXRATE = "1000k"
AUDIO_KBPS = "96k"
WIDTH, HEIGHT = 720, 480        # within the player's 720x576 ceiling

SHOWS = {
    "bluey":     ("Bluey",                    "Bluey"),
    "clifford":  ("Clifford the Big Red Dog", "Clifford"),
    "puppydays": ("Clifford's Puppy Days",    "PuppyDays"),
}


def ssh(cmd):
    return subprocess.check_output(
        ["ssh", "-i", KEY, "-o", "ConnectTimeout=10", HOST, cmd]).decode()


def sources(show_dir):
    out = ssh(f'find "{SRC_ROOT}/{show_dir}" -name "*.mp4" | sort')
    items = []
    for path in out.splitlines():
        m = re.search(r"S(\d+)E(\d+)", os.path.basename(path))
        if m:
            items.append((path, int(m.group(1)), int(m.group(2))))
    items.sort(key=lambda t: (t[1], t[2]))
    return items


def convert(src, dst):
    tmp_out = dst + ".part.avi"
    subprocess.check_call([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
        "-c:v", "mpeg4", "-vtag", "XVID",
        "-b:v", VIDEO_KBPS, "-maxrate", MAXRATE, "-bufsize", "2000k",
        "-vf", f"scale={WIDTH}:{HEIGHT},setdar=16/9", "-g", "250",
        "-c:a", "libmp3lame", "-b:a", AUDIO_KBPS, "-ar", "48000", "-ac", "2",
        tmp_out,
    ])
    os.replace(tmp_out, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("card")
    ap.add_argument("--show", default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--season", type=int, default=0)
    args = ap.parse_args()

    os.environ["COPYFILE_DISABLE"] = "1"      # keep ._ sidecars off the card
    os.makedirs(TMP, exist_ok=True)
    picked = SHOWS if args.show == "all" else {args.show: SHOWS[args.show]}

    for key, (show_dir, card_dir) in picked.items():
        items = sources(show_dir)
        if args.season:
            items = [i for i in items if i[1] == args.season]
        if args.limit:
            items = items[:args.limit]
        dest = os.path.join(args.card, card_dir)
        os.makedirs(dest, exist_ok=True)
        print(f"\n=== {show_dir}: {len(items)} episodes -> {card_dir}/", flush=True)

        for n, (remote, season, ep) in enumerate(items, 1):
            name = f"S{season:02d}E{ep:02d}.AVI"
            dst = os.path.join(dest, name)
            if os.path.exists(dst) and os.path.getsize(dst) > 1_000_000:
                continue
            local = os.path.join(TMP, "src.mp4")
            try:
                subprocess.check_call(["scp", "-i", KEY, "-q",
                                       f"{HOST}:{remote}", local])
                convert(local, dst)
                print(f"[{n}/{len(items)}] {card_dir}/{name}  "
                      f"{os.path.getsize(dst)/1e6:.0f}MB", flush=True)
            except subprocess.CalledProcessError as e:
                print(f"[{n}/{len(items)}] FAIL {name}: {e}", flush=True)
            finally:
                if os.path.exists(local):
                    os.remove(local)

    subprocess.call(["find", args.card, "-name", "._*", "-delete"])
    print("\nDONE", flush=True)


if __name__ == "__main__":
    main()
