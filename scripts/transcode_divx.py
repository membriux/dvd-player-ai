#!/usr/bin/env python3
"""Transcode videos to DivX/MPEG-4 Part 2 AVI + MP3 for older DVD/SD players.

Target spec (typical older car/standalone DivX unit): MPEG-4 Part 2 (Xvid),
<=720x480, <=~2.8 Mbps, no GMC/Qpel (ffmpeg's mpeg4 encoder defaults satisfy
this), MP3 audio. Output into zero-padded season folders so the unit's file
browser sorts correctly. Resumable.

Usage:
    python3 transcode_divx.py <src_dir> <dest_dir>
      src files named like "... Season <s> ... <episode-num>.mp4" OR already
      "Season_<s>_Episode_<n>.mp4"; adjust the parser below for your source.
"""
import argparse, glob, os, re, subprocess


def transcode(src, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 1_000_000:
        return "skip"
    tmp = dst + ".part.avi"
    subprocess.check_call([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
        "-c:v", "mpeg4", "-vtag", "XVID", "-b:v", "2000k",
        "-maxrate", "2800k", "-bufsize", "4000k",
        "-vf", "scale=720:480:flags=lanczos,setdar=16/9", "-r", "30000/1001", "-g", "300",
        "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        tmp,
    ])
    os.replace(tmp, dst)
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dest")
    args = ap.parse_args()

    srcs = glob.glob(os.path.join(args.src, "Season_*_Episode_*.mp4"))

    def key(p):
        s, e = re.findall(r"Season_(\d+)_Episode_(\d+)", os.path.basename(p))[0]
        return (int(s), int(e))

    srcs.sort(key=key)
    print(f"to transcode: {len(srcs)}", flush=True)
    ok = 0
    for i, src in enumerate(srcs, 1):
        s, e = key(src)
        folder = os.path.join(args.dest, f"Season_{s}")
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, f"Episode_{e:02d}.avi")
        try:
            transcode(src, dst)
            ok += 1
            print(f"[{i}/{len(srcs)}] ok Season_{s}/Episode_{e:02d}.avi", flush=True)
        except subprocess.CalledProcessError as ex:
            print(f"[{i}/{len(srcs)}] FAIL {os.path.basename(src)}: {ex}", flush=True)
    print(f"DONE ok={ok}", flush=True)


if __name__ == "__main__":
    main()
