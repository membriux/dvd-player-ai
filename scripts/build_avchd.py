#!/usr/bin/env python3
"""Author an AVCHD BDMV from a set of clips, for a Blu-ray engine that reads SD
as a disc. Normalizes each clip to AVCHD-legal streams (H.264 + AC-3 -- AVCHD
does NOT allow AAC), concatenates per title with a chapter mark per clip, and
muxes a BDMV tree with tsMuxeR. Place the result at <CARD>/PRIVATE/AVCHD/.

Requires: ffmpeg, tsMuxeR (https://github.com/justdan96/tsMuxer/releases).

Usage:
    python3 build_avchd.py <src_glob> <out_dir> --tsmuxer /path/to/tsMuxeR
      e.g. build_avchd.py "/src/*.mp4" ./out --tsmuxer ./bin/tsMuxeR

Notes:
- Target 720x480 (NTSC-SD) by default; AVCHD also allows 1280x720 / 1080 at
  specific frame rates. 852x480 and other non-standard sizes are NOT legal AVCHD
  -- re-encode, do not stream-copy.
- --split-size=1900MB keeps each .m2ts under FAT32's 4 GB limit.
- Final card layout the unit usually wants: <CARD>/PRIVATE/AVCHD/BDMV + CERTIFICATE.
"""
import argparse, glob, os, shutil, subprocess, tempfile


def norm(src, dst):
    """Re-encode to AVCHD-legal H.264 720x480 + AC-3 in an mp4 tsMuxeR can read."""
    if os.path.exists(dst) and os.path.getsize(dst) > 1_000_000:
        return
    subprocess.check_call([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
        "-map", "0:v:0", "-c:v", "libx264", "-preset", "faster",
        "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
        "-vf", "scale=720:480:flags=lanczos,setsar=40/33", "-r", "30000/1001",
        "-x264-params", "keyint=30:min-keyint=15:bframes=3:ref=4:nal-hrd=vbr",
        "-b:v", "1800k", "-maxrate", "3000k", "-bufsize", "4000k",
        "-map", "0:a:0", "-c:a", "ac3", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", dst,
    ])


def dur(path):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", path]).strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_glob")
    ap.add_argument("out")
    ap.add_argument("--tsmuxer", required=True)
    args = ap.parse_args()

    srcs = sorted(glob.glob(args.src_glob))
    if not srcs:
        raise SystemExit("no source clips matched")
    work = tempfile.mkdtemp(prefix="avchd_")
    normed = []
    for i, s in enumerate(srcs, 1):
        d = os.path.join(work, f"n{i:04d}.mp4")
        norm(s, d)
        normed.append(d)
        print(f"[{i}/{len(srcs)}] normalized {os.path.basename(s)}", flush=True)

    # concat
    cat = os.path.join(work, "concat.txt")
    with open(cat, "w") as f:
        for p in normed:
            f.write(f"file '{p}'\n")
    joined = os.path.join(work, "all.mp4")
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                           "-f", "concat", "-safe", "0", "-i", cat, "-c", "copy", joined])

    # cumulative chapter marks (start of each clip)
    marks, t = [], 0.0
    for p in normed:
        h, m, s = int(t // 3600), int((t % 3600) // 60), t % 60
        marks.append(f"{h:02d}:{m:02d}:{s:06.3f}")
        t += dur(p)
    chapters = ";".join(marks)

    meta = os.path.join(work, "avchd.meta")
    with open(meta, "w") as f:
        f.write("MUXOPT --no-pcr-on-video-pid --new-audio-pes --avchd --vbr "
                f"--vbv-len=500 --split-size=1900MB --custom-chapters={chapters}\n")
        f.write(f'V_MPEG4/ISO/AVC, "{joined}", insertSEI, contSPS, track=1, lang=eng\n')
        f.write(f'A_AC3, "{joined}", track=2, lang=eng\n')

    if os.path.exists(args.out):
        shutil.rmtree(args.out)
    subprocess.check_call([args.tsmuxer, meta, args.out])
    print(f"AVCHD authored at {args.out} (copy BDMV+CERTIFICATE to <CARD>/PRIVATE/AVCHD/)",
          flush=True)


if __name__ == "__main__":
    main()
