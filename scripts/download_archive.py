#!/usr/bin/env python3
"""Download media files from an archive.org item, resumable + size-verified.

Usage:
    python3 download_archive.py <archive_identifier> <dest_dir> [--ext mp4,mkv,avi]

Example:
    python3 download_archive.py bluey-iso-archive /Volumes/CARD/Bluey --ext mp4

Picks files by extension, verifies each against the metadata byte size, skips
files already complete, and retries are handled by just re-running (transient
archive.org HTTP 500 / timeouts are common — a second pass finishes stragglers).
Rename/organize into Season_X/Episode_NN is left to the caller or a wrapper.
"""
import argparse, json, os, shutil, urllib.parse, urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("identifier")
    ap.add_argument("dest")
    ap.add_argument("--ext", default="mp4,mkv,avi",
                    help="comma-separated extensions to fetch")
    ap.add_argument("--min-size", type=int, default=2_000_000,
                    help="skip files smaller than this (drops menu/intro stubs)")
    args = ap.parse_args()

    exts = tuple("." + e.strip().lower().lstrip(".") for e in args.ext.split(","))
    base = f"https://archive.org/download/{args.identifier}"
    meta = json.load(urllib.request.urlopen(
        f"https://archive.org/metadata/{args.identifier}", timeout=60))
    files = [f for f in meta["files"]
             if f.get("name", "").lower().endswith(exts)
             and int(f.get("size", 0)) >= args.min_size]
    os.makedirs(args.dest, exist_ok=True)
    print(f"{len(files)} files to fetch -> {args.dest}", flush=True)

    ok = 0
    for i, f in enumerate(files, 1):
        name, size = f["name"], int(f["size"])
        out = os.path.join(args.dest, os.path.basename(name))
        if os.path.exists(out) and os.path.getsize(out) == size:
            ok += 1
            continue
        url = f"{base}/{urllib.parse.quote(name)}"
        tmp = out + ".part"
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as w:
                shutil.copyfileobj(r, w, 1 << 20)
            if os.path.getsize(tmp) == size:
                os.replace(tmp, out)
                ok += 1
                print(f"[{i}/{len(files)}] OK {os.path.basename(out)}", flush=True)
            else:
                print(f"[{i}/{len(files)}] SIZE-MISMATCH {name}", flush=True)
                os.remove(tmp)
        except Exception as e:
            print(f"[{i}/{len(files)}] FAIL {name}: {e}", flush=True)
            if os.path.exists(tmp):
                os.remove(tmp)
    print(f"DONE {ok}/{len(files)} (re-run to retry any FAIL)", flush=True)


if __name__ == "__main__":
    main()
