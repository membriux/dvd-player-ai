# dvd-player-ai

A runbook for an AI agent tasked with loading video onto an SD card that plays in a
**DVD / Blu-ray head unit with an SD-card slot** (car rear-seat systems, standalone
players, etc.). It covers the full pipeline: **find & download → format the card →
transcode & organize → verify**.

> Written for: an AI agent doing this end to end for a non-expert user. Follow it as a
> procedure. Do not assume a format works — **verify the target device's spec first**,
> because these players vary wildly (some play H.264 MP4, many older ones only play
> DivX/MPEG-4 Part 2 AVI).

---

## 0. Golden rules (learned the hard way)

1. **The device spec is the source of truth, not a web summary.** Find the unit's owner's
   manual and read its "supported media / file formats" table. AI-generated spec blurbs
   were wrong in practice; the official PDF was right.
2. **"Audio plays but no video" = the video codec is unsupported** (OR the player hardware
   is failing). If the file is H.264 and the manual lists only DivX/MPEG-4 Part 2,
   transcode the video. If the spec says the codec *is* supported and it still fails,
   suspect the player itself.
3. **Let the head unit format the card when it offers to.** Whatever filesystem it writes
   is exactly what it wants — read it back on a computer to learn the target FS, then just
   copy files onto it. **Never reformat a card the user says the device formatted.**
4. **Card size matters.** Many of these units are FAT32-only with a hard **32 GB ceiling**
   and reject 64 GB SDXC cards regardless of format. If the unit won't read a 64 GB card,
   try a ≤32 GB SDHC card before blaming the files. (Some newer units format 64 GB to
   exFAT themselves — if so, that's fine.)
5. **FAT32 has a 4 GB per-file limit;** exFAT does not. Split or keep files under 4 GB on
   FAT32.
6. **Strip macOS metadata** (`._*`, `.Spotlight-V100`, `.fseventsd`, `.Trashes`) before
   handing the card back — some players list the `._Foo.mp4` AppleDouble stubs as junk
   entries. Set `export COPYFILE_DISABLE=1` before copying.
7. **Verify, don't assume.** `ffprobe` every output; confirm codec/container/resolution
   match the spec before declaring done.

---

## 1. Identify the target device spec (do this first)

Get: make/model + "rear seat entertainment" / "SD card" / owner's manual. Pull the manual
PDF and extract the media-format table. Capture these fields:

| Field | Why it matters | Example (Toyota PZ462-00207 RSE) |
|-------|----------------|-----------------------------------|
| Filesystem | How to format the card | FAT32 (≤32 GB) or exFAT |
| Recognized extensions | Container to mux into | `.avi .divx .mpg .mpeg .vob` (**no `.mp4`!**) |
| Video codec(s) | What to transcode to | DivX / MPEG-4 Part 2 (DivX 5, no GMC/Qpel) |
| Max resolution | Downscale target | ≤ 720×576 |
| Max bitrate | Encoder cap | ≤ 3000 kbps (SD/USB) |
| Audio codec(s) | Audio transcode target | MP3 (AAC sometimes OK) |
| Folder/menu model | How to organize | Built-in file browser; max 200 folders |

Common buckets you'll land in:
- **Modern unit:** plays **H.264/AAC `.mp4`** directly → easiest (§4a).
- **Older DivX unit:** only **MPEG-4 Part 2 in `.avi`** + MP3 → transcode (§4b).
- **Blu-ray disc engine reading SD as a disc:** wants **AVCHD** `BDMV` tree, often under
  `/PRIVATE/AVCHD/` → author with tsMuxeR (§4c). A "please format this card" prompt on an
  AVCHD/loose-file card usually means the SD path is *not* the AVCHD engine — it's a file
  browser; fall back to §4a/§4b.

---

## 2. Find & download the videos

Source is either a URL the user provides or an [archive.org](https://archive.org) item.

**archive.org via the metadata API** (no HTML scraping, gives exact filenames + sizes):

```python
import urllib.request, urllib.parse, json
IDENT = "bluey-iso-archive"              # the item id from /details/<id> or /download/<id>
d = json.load(urllib.request.urlopen(f"https://archive.org/metadata/{IDENT}"))
for f in d["files"]:
    n = f["name"]
    if n.lower().endswith((".mp4",".mkv",".avi")):
        print(f.get("size"), n)
# download URL = https://archive.org/download/{IDENT}/{urllib.parse.quote(name)}
```

Download notes:
- Pick one copy per episode; skip derivative dupes (`.ia.mp4`) and giant full-disc
  concatenations if per-episode files exist. Skip menu/intro stubs (tiny <2 MB files).
- Verify each file's byte size against the metadata; **retry transient `HTTP 500` /
  timeouts** (archive.org flakes — a second pass usually completes the stragglers).
- Make it resumable: skip files already present at the expected size.

`scripts/download_archive.py` in this repo is a ready-to-run, resumable implementation.

---

## 3. Format the SD card

1. **If the device already formatted it, STOP — don't reformat.** Read the FS back:
   ```bash
   diskutil info /Volumes/<CARD>   # macOS: look at "File System Personality"
   ```
   Copy files onto it as-is.
2. **If you must format**, match the spec:
   - FAT32 (≤32 GB cards, most compatible):
     `diskutil eraseVolume MS-DOS <NAME> /dev/diskN`  (or `mkfs.vfat -F32` on Linux)
   - exFAT (>32 GB, only if the unit supports it):
     `diskutil eraseVolume ExFAT <NAME> /dev/diskN`
   - Windows hides FAT32 for >32 GB — use a third-party tool (Rufus / guiformat) there.
3. **Confirm the physical card class** is accepted (SDHC ≤32 GB is safest for older units).

---

## 4. Transcode & organize

Install `ffmpeg` (and `tsMuxeR` only for the AVCHD case). Pick the branch from §1.
Organize output as a simple, zero-padded, browsable tree:

```
<CARD>/<Show>/Season_1/Episode_01.ext
```

Zero-pad episode numbers (`Episode_01`, not `Episode_1`) so the player's file browser
sorts correctly.

### 4a. Modern unit — H.264/AAC MP4 (no transcode if source already is)
If the source is already H.264/AAC `.mp4`, just copy with the right names. If not:
```bash
ffmpeg -i IN -c:v libx264 -profile:v high -level 4.0 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart OUT.mp4
```

### 4b. Older DivX unit — MPEG-4 Part 2 in AVI + MP3 (the common car-unit case)
≤720×480, ≤3 Mbps, no GMC/Qpel (ffmpeg's `mpeg4` encoder defaults satisfy this):
```bash
ffmpeg -i IN \
  -c:v mpeg4 -vtag XVID -b:v 2000k -maxrate 2800k -bufsize 4000k \
  -vf "scale=720:480:flags=lanczos,setdar=16/9" -r 30000/1001 -g 300 \
  -c:a libmp3lame -b:a 192k -ar 48000 -ac 2 \
  OUT.avi
```

### 4c. Blu-ray disc engine — AVCHD BDMV (only if the SD slot is the disc engine)
1. Normalize each clip to AVCHD-legal streams: H.264 **720×480** (or 1280×720 / 1080),
   **AC-3** audio (AVCHD does **not** allow AAC), into an intermediate `.mp4`.
2. Concatenate per title (ffmpeg concat demuxer), compute per-episode chapter offsets.
3. Author with tsMuxeR: `MUXOPT ... --avchd --split-size=1900MB --custom-chapters=<marks>`
   → writes a `BDMV/` + `CERTIFICATE/` tree.
4. Place it at **`<CARD>/PRIVATE/AVCHD/BDMV`** (camera-style path many units require), not
   just root `BDMV`. On FAT32, `--split-size` keeps each `.m2ts` under 4 GB.

`scripts/transcode_divx.py` (4b) and `scripts/build_avchd.py` (4c) in this repo are
ready-to-run implementations.

---

## 5. Verify & finish

```bash
ffprobe -v error -show_entries stream=codec_type,codec_name,width,height \
  -of default=noprint_wrappers=1 "<one output file>"      # matches §1 spec?
export COPYFILE_DISABLE=1                                   # before any copy to the card
find /Volumes/<CARD> -name '._*' -delete                   # strip AppleDouble stubs
rm -rf /Volumes/<CARD>/.Spotlight-V100 /Volumes/<CARD>/.fseventsd /Volumes/<CARD>/.Trashes
diskutil eject /Volumes/<CARD>                             # safe-eject before pulling
```

Checklist before handing back:
- [ ] Codec/container/resolution/bitrate match the device spec (§1), confirmed by `ffprobe`.
- [ ] Files organized `Show/Season_X/Episode_NN.ext`, zero-padded.
- [ ] No `._*` / macOS system files on the card.
- [ ] Card not reformatted if the device formatted it.
- [ ] If the unit still shows nothing: re-check card size (≤32 GB SDHC) and the §1 spec
      before touching the files again.

---

## Worked example (what this repo was built from)

Goal: Bluey S1–S3 on an SD card for a 2017 Toyota Sienna Limited rear-seat system.
- Pulled 170 episodes from the `bluey-iso-archive` item (metadata API, resumable).
- The unit formatted the 64 GB card to **exFAT** itself → left it, copied files in.
- Final working format: **H.264/AAC `.mp4`**, organized `Bluey/Season_S_Episode_N.mp4`.
- Earlier "audio but no video" turned out to be a **failing player**, not the files —
  once the hardware was fixed, plain MP4 played. (Had it truly been a DivX-only unit, §4b
  would have been the fix — that path is kept here because it's the common case.)
