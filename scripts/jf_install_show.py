#!/usr/bin/env python3
"""Download a show from an archive.org item into a Jellyfin-conventional TV tree.

Runs ON the Jellyfin host. Resumable and size-verified: re-run to retry failures.

Layout produced (what Jellyfin's TV scanner expects):
    <root>/<Show Name>/Season 01/<Show Name> - S01E01 - <Title>.mp4

Usage:
    python3 jf_install_show.py bluey    /srv/media/tv
    python3 jf_install_show.py clifford /srv/media/tv
"""
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request

SHOWS = {
    # Bluey: source names are "Bluey - Season <s> - First/Second Half<n>.mp4".
    # Halves are ordered First then Second, numbered sequentially within a season.
    "bluey": {
        "identifier": "bluey-iso-archive",
        "name": "Bluey",
        "match": re.compile(r"Season (\d) - (First|Second) Half(\d+)\.mp4$"),
        "mode": "season_half",
    },
    # Clifford: source names are "<nn> <Story A>_<Story B>.mp4" -- one file holds
    # two stories, so the pair becomes the episode title.
    "clifford": {
        "identifier": "dsclifford",
        "name": "Clifford the Big Red Dog",
        "match": re.compile(r"^(\d+)\s+(.*)\.mp4$"),
        "mode": "flat_titled",
    },
    # Puppy Days: source names already carry "S01e01 <Title A> - <Title B>".
    # The item is the complete series despite the single-episode detail page.
    "puppydays": {
        "identifier": "cliffords-puppy-days-s-02e-05-celebrating-spring-garden-delights",
        "name": "Clifford's Puppy Days",
        "match": re.compile(r"-\s*S(\d+)e(\d+)\s+(.*)\.mp4$", re.I),
        "mode": "season_ep",
    },
}

MIN_SIZE = 2_000_000  # drop menu/intro stubs


def clean_title(raw):
    """Source joins two story titles with '_'; make it display-safe."""
    t = raw.replace("_", " & ")
    t = re.sub(r"[/:]", "-", t)          # path- and scanner-hostile chars
    return re.sub(r"\s+", " ", t).strip()


def natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def build_plan(cfg):
    meta = json.load(urllib.request.urlopen(
        f"https://archive.org/metadata/{cfg['identifier']}", timeout=60))
    files = [f for f in meta.get("files", [])
             if f.get("name", "").lower().endswith(".mp4")
             and not f["name"].lower().endswith(".ia.mp4")
             and int(f.get("size", 0)) >= MIN_SIZE]
    files.sort(key=lambda f: natkey(f["name"]))

    show = cfg["name"]
    plan = []  # (src_name, size, relative_output_path)

    if cfg["mode"] == "season_half":
        # order within a season: First Half before Second Half, then by number
        keyed = []
        for f in files:
            m = cfg["match"].search(f["name"])
            if m:
                keyed.append((int(m.group(1)), 0 if m.group(2) == "First" else 1,
                              int(m.group(3)), f))
        keyed.sort(key=lambda t: t[:3])
        counters = {}
        for season, _half, _num, f in keyed:
            counters[season] = counters.get(season, 0) + 1
            ep = counters[season]
            plan.append((f["name"], int(f["size"]), os.path.join(
                show, f"Season {season:02d}",
                f"{show} - S{season:02d}E{ep:02d}.mp4")))
    elif cfg["mode"] == "season_ep":
        # season and episode numbers come from the source name itself
        for f in files:
            m = cfg["match"].search(os.path.basename(f["name"]))
            if not m:
                continue
            season, ep = int(m.group(1)), int(m.group(2))
            title = clean_title(m.group(3))
            plan.append((f["name"], int(f["size"]), os.path.join(
                show, f"Season {season:02d}",
                f"{show} - S{season:02d}E{ep:02d} - {title}.mp4")))

    else:  # flat_titled -> all Season 01
        ep = 0
        for f in files:
            m = cfg["match"].match(os.path.basename(f["name"]))
            if not m:
                continue
            ep += 1
            title = clean_title(m.group(2))
            plan.append((f["name"], int(f["size"]), os.path.join(
                show, "Season 01",
                f"{show} - S01E{ep:02d} - {title}.mp4")))
    return plan


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in SHOWS:
        sys.exit(f"usage: {sys.argv[0]} {{{'|'.join(SHOWS)}}} <root_dir>")
    cfg, root = SHOWS[sys.argv[1]], sys.argv[2]
    base = f"https://archive.org/download/{cfg['identifier']}"

    plan = build_plan(cfg)
    total = sum(p[1] for p in plan)
    print(f"{len(plan)} episodes, {total / 1e9:.2f} GB -> {root}", flush=True)

    ok = 0
    for i, (src, size, rel) in enumerate(plan, 1):
        out = os.path.join(root, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if os.path.exists(out) and os.path.getsize(out) == size:
            ok += 1
            continue
        tmp = out + ".part"
        try:
            url = f"{base}/{urllib.parse.quote(src)}"
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
    print(f"DONE {ok}/{len(plan)}", flush=True)


if __name__ == "__main__":
    main()
