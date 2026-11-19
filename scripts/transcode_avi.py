#!/usr/bin/env python3
"""Transcode all Bluey mp4s on the card to DivX-compatible AVI per the Toyota
PZ462-00207 RSE manual: MPEG-4 Part 2 (Xvid), <=720x480, MP3 audio, <=3Mbps,
no GMC/Qpel. Output into season subfolders with zero-padded names so the unit's
file browser shows a clean, correctly-sorted menu:
    Bluey/Season_1/Episode_01.avi ...
Removes the unplayable .mp4 sources. Resumable."""
import os, re, subprocess, glob

BASE = "/Volumes/SanEsc/Bluey"

def transcode(src, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 1_000_000:
        return "skip"
    tmp = dst + ".part.avi"
    cmd = ["ffmpeg","-y","-hide_banner","-loglevel","error","-i", src,
        "-c:v","mpeg4","-vtag","XVID","-b:v","2000k","-maxrate","2800k","-bufsize","4000k",
        "-vf","scale=720:480:flags=lanczos,setdar=16/9","-r","30000/1001","-g","300",
        "-c:a","libmp3lame","-b:a","192k","-ar","48000","-ac","2",
        tmp]
    subprocess.check_call(cmd)
    os.replace(tmp, dst)
    return "ok"

def main():
    srcs = glob.glob(f"{BASE}/Season_*_Episode_*.mp4")
    def key(p):
        s, e = re.findall(r"Season_(\d+)_Episode_(\d+)", os.path.basename(p))[0]
        return (int(s), int(e))
    srcs.sort(key=key)
    print(f"to transcode: {len(srcs)}", flush=True)
    ok = 0
    for i, src in enumerate(srcs, 1):
        s, e = key(src)
        folder = f"{BASE}/Season_{s}"
        os.makedirs(folder, exist_ok=True)
        dst = f"{folder}/Episode_{e:02d}.avi"
        try:
            st = transcode(src, dst)
            ok += 1
            if st == "ok":
                os.remove(src)
                print(f"[{i}/{len(srcs)}] ok Season_{s}/Episode_{e:02d}.avi", flush=True)
        except subprocess.CalledProcessError as ex:
            print(f"[{i}/{len(srcs)}] FAIL {os.path.basename(src)}: {ex}", flush=True)
    for s in (1, 2, 3):
        n = len(glob.glob(f"{BASE}/Season_{s}/*.avi"))
        print(f"Season_{s}: {n} avi", flush=True)
    print(f"DONE ok={ok} mp4_left={len(glob.glob(f'{BASE}/*.mp4'))}", flush=True)

if __name__ == "__main__":
    main()
