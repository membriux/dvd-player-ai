#!/usr/bin/env python3
"""Download all Bluey S1-3 episodes from bluey-iso-archive, organized as
<CARD>/Bluey/Season_<s>_Episode_<n>.mp4 (plain mp4, exFAT). Resumable."""
import urllib.request, urllib.parse, json, re, os, shutil, sys

CARD = sys.argv[1] if len(sys.argv) > 1 else "/Volumes/BLUEY"
DEST = f"{CARD}/Bluey"
ITEM = "bluey-iso-archive"
BASE = f"https://archive.org/download/{ITEM}"

def meta():
    return json.load(urllib.request.urlopen(f"https://archive.org/metadata/{ITEM}", timeout=60))

def relevant(f):
    n = f.get("name", "")
    if not n.lower().endswith(".mp4"):
        return None
    m = re.search(r"Season (\d) - (First|Second) Half(\d+)\.mp4$", n)
    if not m or int(f.get("size", 0)) < 2_000_000:
        return None
    return (int(m.group(1)), 0 if m.group(2) == "First" else 1, int(m.group(3)), n, int(f["size"]))

def main():
    d = meta()
    items = sorted(x for x in (relevant(f) for f in d["files"]) if x)
    # assign sequential episode numbers per season
    plan = []            # (season, epnum, srcname, size)
    counters = {}
    for s, half, num, n, sz in items:
        counters[s] = counters.get(s, 0) + 1
        plan.append((s, counters[s], n, sz))
    os.makedirs(DEST, exist_ok=True)
    print(f"episodes to fetch: {len(plan)}", flush=True)
    ok = 0
    for i, (s, ep, src, size) in enumerate(plan, 1):
        out = f"{DEST}/Season_{s}_Episode_{ep}.mp4"
        if os.path.exists(out) and os.path.getsize(out) == size:
            ok += 1
            continue
        url = f"{BASE}/{urllib.parse.quote(src)}"
        tmp = out + ".part"
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as w:
                shutil.copyfileobj(r, w, 1 << 20)
            if os.path.getsize(tmp) == size:
                os.replace(tmp, out)
                ok += 1
                print(f"[{i}/{len(plan)}] OK Season_{s}_Episode_{ep}.mp4", flush=True)
            else:
                print(f"[{i}/{len(plan)}] SIZE-MISMATCH S{s}E{ep} ({os.path.getsize(tmp)}/{size})", flush=True)
                os.remove(tmp)
        except Exception as e:
            print(f"[{i}/{len(plan)}] FAIL S{s}E{ep}: {e}", flush=True)
            if os.path.exists(tmp):
                os.remove(tmp)
    # per-season tallies
    have = {}
    for f in os.listdir(DEST):
        m = re.match(r"Season_(\d)_Episode_\d+\.mp4$", f)
        if m:
            have[int(m.group(1))] = have.get(int(m.group(1)), 0) + 1
    print(f"DONE {ok}/{len(plan)}  per-season: " +
          " ".join(f"S{s}={have.get(s,0)}" for s in sorted(have)), flush=True)

if __name__ == "__main__":
    main()
