#!/usr/bin/env python3
"""Install a show/movie from an archive.org item onto an SD card, organized and
renamed for a DVD-player file browser. Resumable + size-verified.

Usage:
    python3 install_show.py <identifier> <card_path> <ShowName> [options]

    --season-regex RE   capture season+episode from the source filename, e.g.
                        'Season (\\d) - (?:First|Second) Half(\\d+)' -> Season_S/Episode_NN
    --flat              number files sequentially in sort order (default)
    --ext mp4,avi       extensions to fetch (default mp4)
    --min-size BYTES    skip stubs/menus (default 2000000)
    --dry-run           print the plan without downloading

Output layout (player-browser friendly, zero-padded so it sorts correctly):
    <card>/<ShowName>/Episode_01.mp4            (flat)
    <card>/<ShowName>/Season_1/Episode_01.mp4   (with --season-regex)
"""
import argparse, json, os, re, shutil, urllib.parse, urllib.request


def meta(identifier):
    return json.load(urllib.request.urlopen(
        f"https://archive.org/metadata/{identifier}", timeout=60))


def build_plan(args):
    d = meta(args.identifier)
    exts = tuple("." + e.strip().lower().lstrip(".") for e in args.ext.split(","))
    files = [f for f in d.get("files", [])
             if f.get("name", "").lower().endswith(exts)
             and not f["name"].lower().endswith(".ia" + exts[0])   # skip derivatives
             and int(f.get("size", 0)) >= args.min_size]
    files.sort(key=lambda f: natkey(f["name"]))

    plan = []  # (src_name, size, relative_out_path)
    if args.season_regex:
        rx = re.compile(args.season_regex)
        counters = {}
        for f in files:
            m = rx.search(f["name"])
            if not m:
                continue
            season = int(m.group(1))
            counters[season] = counters.get(season, 0) + 1
            plan.append((f["name"], int(f["size"]),
                         os.path.join(f"Season_{season}",
                                      f"Episode_{counters[season]:02d}{ext_of(f['name'])}")))
    else:
        for i, f in enumerate(files, 1):
            plan.append((f["name"], int(f["size"]),
                         f"Episode_{i:02d}{ext_of(f['name'])}"))
    return plan


def ext_of(name):
    return "." + name.rsplit(".", 1)[-1].lower()


def natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("identifier")
    ap.add_argument("card")
    ap.add_argument("show")
    ap.add_argument("--season-regex", default=None)
    ap.add_argument("--flat", action="store_true")
    ap.add_argument("--ext", default="mp4")
    ap.add_argument("--min-size", type=int, default=2_000_000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = f"https://archive.org/download/{args.identifier}"
    root = os.path.join(args.card, args.show)
    plan = build_plan(args)
    total = sum(p[1] for p in plan)
    print(f"{len(plan)} files, {total/1e9:.2f} GB -> {root}", flush=True)
    if args.dry_run:
        for src, size, rel in plan:
            print(f"  {size/1e6:8.1f}MB  {rel:<34} <- {src}")
        return

    os.environ["COPYFILE_DISABLE"] = "1"
    ok = 0
    for i, (src, size, rel) in enumerate(plan, 1):
        out = os.path.join(root, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if os.path.exists(out) and os.path.getsize(out) == size:
            ok += 1
            continue
        url = f"{base}/{urllib.parse.quote(src)}"
        tmp = out + ".part"
        try:
            with urllib.request.urlopen(url, timeout=180) as r, open(tmp, "wb") as w:
                shutil.copyfileobj(r, w, 1 << 20)
            if os.path.getsize(tmp) == size:
                os.replace(tmp, out)
                ok += 1
                print(f"[{i}/{len(plan)}] OK {rel}", flush=True)
            else:
                print(f"[{i}/{len(plan)}] SIZE-MISMATCH {rel}", flush=True)
                os.remove(tmp)
        except Exception as e:
            print(f"[{i}/{len(plan)}] FAIL {rel}: {e}", flush=True)
            if os.path.exists(tmp):
                os.remove(tmp)
    print(f"DONE {ok}/{len(plan)} (re-run to retry failures)", flush=True)


if __name__ == "__main__":
    main()
