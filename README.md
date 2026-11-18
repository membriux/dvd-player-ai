# dvd-player-ai

A runbook for an AI agent asked to get kids' shows playing on a family's screens.
There are **two independent delivery targets**, and they need different file formats:

| Target | Where it plays | Format that works | Section |
|--------|----------------|-------------------|---------|
| **SD card** | Car DVD/Blu-ray head unit with an SD slot | depends on the unit — verify the manual | [§A](#a-sd-card-for-a-dvd-head-unit) |
| **Jellyfin** | LG webOS TV, phones, laptops | H.264 + AAC `.mp4` | [§B](#b-jellyfin-homelab) |

> Follow this as a procedure, not reference. The recurring failure mode in this project
> was **assuming a format or a spec instead of verifying it**. Every "golden rule" below
> is something that actually went wrong once.

---

## Live environment (as of 2026-11-18)

```
LAN 192.168.8.0/24, gateway GL.iNet .1, DNS not intercepted
Proxmox   pve @ 192.168.8.238:8006   (API token in Keychain: proxmox-homelab-token)
  LXC 100 pve-cloudflare-tunnel
  LXC 104 jellyfin @ 192.168.8.114   (SSH: root + ~/.ssh/id_ecdsa, Debian 13, amd64)
LG TV     OLED65C3AUA @ 192.168.8.184, webOS 26 (fw 43.21.96), Dev Mode OFF
```

**Jellyfin 12.4** on LXC 104:
- LAN `http://192.168.8.114:8096` · public `https://movies.membriux.com`
- Libraries: **Kid Shows** (`/srv/media/tv`, type `tvshows`) and **Kid Videos**
  (`/srv/kidtube/library`, type `homevideos`, currently empty)
- Users: `sancjgui` (admin) and `Santiago` (non-admin, scoped to the two kid libraries)
- Content: Bluey S1–3 (170), Clifford the Big Red Dog (65), Clifford's Puppy Days (39)

Companion project: `~/Desktop/kidtube/` (yt-dlp → Jellyfin, nightly systemd timer).

---

## A. SD card for a DVD head unit

### A1. Identify the device spec first

Find the owner's manual PDF and read its supported-media table. Capture: filesystem,
recognized **file extensions**, video codec, max resolution, max bitrate, audio codec.

Worked example — Toyota PZ462-00207 rear-seat system: `.avi .divx .mpg .mpeg .vob`
(**`.mp4` is not in the list**), DivX/MPEG-4 Part 2, ≤720×576, ≤3000 kbps, MP3 audio.

Three buckets you can land in:
- **Modern unit** — plays H.264/AAC `.mp4` directly (§A3a).
- **Older DivX unit** — MPEG-4 Part 2 in `.avi` + MP3 only (§A3b).
- **Blu-ray disc engine reading the SD slot as a disc** — wants an AVCHD `BDMV` tree,
  usually under `/PRIVATE/AVCHD/` (§A3c).

### A2. Format the card

**If the head unit offered to format the card, let it, and never reformat.** Read the
filesystem back and just copy files on:

```bash
diskutil info /Volumes/<CARD>        # "File System Personality"
```

If you must format, whole-disk + MBR is the most compatible:

```bash
diskutil eraseDisk MS-DOS <LABEL> MBRFormat /dev/diskN   # FAT32, ≤32 GB cards
diskutil eraseDisk ExFAT  <LABEL> MBRFormat /dev/diskN   # >32 GB, only if supported
```

Constraints that bit us:
- **macOS caps volume labels at 11 characters — on exFAT as well as FAT32.** `diskutil`
  rejects anything longer with `"<name> does not appear to be a valid volume name for its
  file system"`. 14, 13 and 12 chars were all refused; 11 was accepted. Plan the label.
- Many units are **FAT32-only with a hard 32 GB ceiling** and refuse 64 GB SDXC cards
  regardless of filesystem. A 2017 Sienna did, however, format a 64 GB card to exFAT
  itself — so trust the device over the forum.
- **FAT32 has a 4 GB per-file limit.** exFAT does not.
- A failed `diskutil eraseDisk` aborts cleanly and leaves the previous filesystem intact.

### A3. Transcode and organize

Zero-pad episode numbers so the unit's file browser sorts correctly:
`<CARD>/<Show>/Season_1/Episode_01.ext`

**a. Modern unit (H.264/AAC mp4)** — if the source is already H.264/AAC, just copy.
```bash
ffmpeg -i IN -c:v libx264 -profile:v high -level 4.0 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart OUT.mp4
```

**b. Older DivX unit** (`scripts/transcode_divx.py`)
```bash
ffmpeg -i IN \
  -c:v mpeg4 -vtag XVID -b:v 2000k -maxrate 2800k -bufsize 4000k \
  -vf "scale=720:480:flags=lanczos,setdar=16/9" -r 30000/1001 -g 300 \
  -c:a libmp3lame -b:a 192k -ar 48000 -ac 2 OUT.avi
```

**c. AVCHD BDMV** (`scripts/build_avchd.py`, needs `ffmpeg` + `tsMuxeR`) — re-encode to
AVCHD-legal H.264 **720×480** with **AC-3** audio (AVCHD forbids AAC), concatenate,
then mux with `--avchd --split-size=1900MB --custom-chapters=<marks>` and place the
result at `<CARD>/PRIVATE/AVCHD/BDMV`. Non-standard sizes like 852×480 are **not** legal
AVCHD — re-encode, never stream-copy.

### A4. Diagnosing "audio plays but no video"

Two possible causes, and we hit the second one:
1. **Unsupported video codec** — the file is H.264 but the manual lists only DivX /
   MPEG-4 Part 2. Transcode per §A3b.
2. **Failing player hardware.** If the spec says the codec *is* supported and it still
   fails, suspect the unit. In this project the Sienna's player was the fault; once it was
   repaired, plain H.264/AAC `.mp4` played fine and no transcode was ever needed.

### A5. Before handing the card back

```bash
export COPYFILE_DISABLE=1                                  # before any copy
find /Volumes/<CARD> -name '._*' -delete                   # AppleDouble stubs
rm -rf /Volumes/<CARD>/.Spotlight-V100 /Volumes/<CARD>/.fseventsd /Volumes/<CARD>/.Trashes
ffprobe -v error -show_entries stream=codec_type,codec_name,width,height \
  -of csv=p=0 "<one output file>"                          # matches §A1 spec?
diskutil eject /Volumes/<CARD>
```

`._Foo.mp4` sidecars double the apparent file count and some players list them as junk
entries.

---

## B. Jellyfin homelab

### B1. Naming is the whole game

Jellyfin's TV scanner needs this exact shape, or series/episodes won't be detected:

```
/srv/media/tv/<Show Name>/Season 01/<Show Name> - S01E01 - <Title>.mp4
```

`scripts/jf_install_show.py` downloads an archive.org item straight onto the Jellyfin
host in this layout. It is resumable and size-verified — re-run it to retry failures.

```bash
scp -i ~/.ssh/id_ecdsa scripts/jf_install_show.py root@192.168.8.114:/root/
ssh -i ~/.ssh/id_ecdsa root@192.168.8.114 \
  'setsid nohup python3 /root/jf_install_show.py bluey /srv/media/tv > /root/bluey.log 2>&1 &'
```

Download on the Jellyfin host, not through the Mac — one less hop and it survives a
laptop sleep. Use `setsid nohup ... &` so it outlives the SSH session; a plain
backgrounded SSH command reports "completed" when the *launcher* exits, which says
nothing about the transfer. Verify with `pgrep -cf jf_install_show.py`.

### B2. Jellyfin 12.4 API gotchas

- **Auth header:** `Authorization: MediaBrowser Token="<token>"`.
  `X-Emby-Token` returns **401** on 12.4.
- **Getting a token:** `POST /Users/AuthenticateByName` with
  `{"Username":..., "Pw":...}` and an `Authorization: MediaBrowser Client="...",
  Device="...", DeviceId="...", Version="..."` header.
- **Per-user remote access.** `Policy.EnableRemoteAccess` exists **per user** as well as
  server-wide. If the user's flag is `false`, remote logins fail with **403, not 401** —
  it looks exactly like a wrong password. Server-wide lives in
  `/etc/jellyfin/network.xml` (`<EnableRemoteAccess>`); a restart is required.
- **Policy updates must GET-then-merge.** `POST /Users/{id}/Policy` rejects a hand-built
  object (it needs `AuthenticationProviderId`, `PasswordResetProviderId`). Fetch the user,
  mutate its `Policy`, post the whole thing back.
- **Granting a new library to a scoped user:** append the library's `ItemId` (from
  `GET /Library/VirtualFolders`) to `Policy.EnabledFolders`, keeping
  `EnableAllFolders=false`.
- **Create a library:** `POST /Library/VirtualFolders?name=<n>&collectionType=tvshows&refreshLibrary=true`
  with `{"LibraryOptions":{"PathInfos":[{"Path":"/srv/media/tv"}]}}` → 204.
- **Rescan:** `POST /Library/Refresh` → 204. With realtime monitoring on, files that land
  later appear on their own.
- Verify access **as the restricted user**, not as admin: authenticate as them and call
  `GET /UserViews?userId=<id>`.

### B3. Public access via Cloudflare tunnel

`cloudflared` was already installed (Homebrew) and already logged in — check
`~/.cloudflared/cert.pem` and `cloudflared tunnel list` before installing anything.
`cf` on npm is **not** the Cloudflare CLI; `cloudflared` is not an npm package.

```bash
cloudflared tunnel create movies
cloudflared tunnel route dns movies movies.membriux.com
# then on the Jellyfin host:
#   /etc/cloudflared/config.yml  ->  ingress: hostname movies.membriux.com
#                                    service: http://localhost:8096
cloudflared service install && systemctl enable --now cloudflared
```

Then flip Jellyfin's server-wide `EnableRemoteAccess` to `true` and restart, or the
tunnel reaches a server that refuses remote requests.

**Cloudflare bot protection returns 403 to scripted clients.** A `curl`/`urllib` request
with a default user-agent gets **403** on `POST /Users/AuthenticateByName`, while the
identical request with a browser user-agent returns **200**. `GET` endpoints like
`/web/index.html` and `/System/Info/Public` are unaffected, which makes it look like a
login or config bug. Always retest with a realistic UA before debugging the origin.

### B4. Security posture

- A fresh Jellyfin is wide open until the setup wizard completes.
- `EnableUPnP=False`, no DLNA plugin (DLNA has no auth and bypasses user scoping).
- `Santiago` is non-admin, `EnableAllFolders=False`, no delete/download rights.
- **Current deliberate risk, chosen by the owner:** `movies.membriux.com` is public with
  no Cloudflare Access gate, protected only by Jellyfin's own login with a short password.
  Cloudflare Access is already configured on this zone
  (`~/.cloudflared/membriux.cloudflareaccess.com-org-token`) if it is ever wanted.
- Rotate the Proxmox token — it is `root@pam` full-privilege and was pasted in plaintext.

---

## C. Sourcing from archive.org

Use the metadata API; never scrape the HTML download page.

```python
import json, urllib.request
d = json.load(urllib.request.urlopen(f"https://archive.org/metadata/{IDENT}"))
# download URL = https://archive.org/download/{IDENT}/{urllib.parse.quote(name)}
```

- **Check `metadata.mediatype` first.** An item titled "Cars the movie 2006" was
  `mediatype: image` — 393 JPEGs in a photo collection, zero video files. The title lies;
  the mediatype does not.
- **A single-episode detail page can be a whole-series item.** A URL ending
  `...-s-02e-05-celebrating-spring-garden-delights` turned out to hold the complete
  39-episode series. Always list the item's files before planning.
- Skip derivative duplicates (`.ia.mp4`), full-disc concatenations when per-episode files
  exist, and stubs under ~2 MB (menus/intros).
- **Verify each file against its metadata byte size** and make the script resumable.
  Transient `HTTP 500`s and read timeouts are common — a second run finishes the
  stragglers. Expect roughly 3–7 failures per 170 files on the first pass.

---

## D. LG webOS TV — what is and is not possible remotely

Jellyfin has a webOS app (appId `1030579`) available for the C3.

**Installing it and reordering the home launcher are manual, remote-in-hand tasks.**
SSAP exposes neither app installation nor launcher ordering, and `bscpylgtv` has no
corresponding methods. On the TV: Content Store → Jellyfin → Install, point it at
`http://192.168.8.114:8096` (use the LAN IP, not the tunnel), then Home → hover the app
row → drag Jellyfin to the front.

To check whether a TV client ever signed in, query `GET /Devices` on Jellyfin — a
signed-in TV app registers there. Only Mac clients appeared, which is how we knew the app
was never installed.

`bscpylgtv` notes for webOS 26:
- Pairing needs the **unsigned** `manifest-comp.json` (`-m`); the default signed manifest
  is rejected with `403 blacklisted certificate` since fw 43.00.92, surfacing as
  `PyLGTVCmdError: Unable to pair`.
- `states=["apps"]` crashes with `KeyError('change')` — the subscription payload changed.
  Pass `states=[]`.
- A stored client key can go stale: `401 insufficient permissions (not registered)`.
  Re-pairing requires pressing accept on the TV.
- Raw `ssap://...` URIs 404; use the wrapper methods.
- Confirmed working ad settings (verified by read-back): `general.homePromotion=off`,
  `option.livePlus=off`. Many other ad keys accept writes and silently validate nothing —
  Luna returns `{'returnValue': True}` for nonsense keys — so do not claim they work.

---

## E. Host-side gotchas

- **npm `E401` on every install:** `~/.npmrc` points the *default* registry at Amazon
  CodeArtifact with an expired `_authToken`, so even public packages 401. Either pass
  `--registry=https://registry.npmjs.org` or refresh the token. Better: scope CodeArtifact
  to `@amzn:registry=...` and leave the default as npmjs.
- `timeout` does not exist on macOS (it is `gtimeout` from coreutils). Use an in-script
  deadline such as `asyncio.wait_for`.
- Inline `python3 -c` with an f-string containing escaped quotes fails with
  `SyntaxError: f-string expression part cannot include a backslash`. Use a heredoc.
- `bc` is not installed on the Debian 13 LXC; do arithmetic in the shell or Python.

---

## Repository layout

```
README.md                      this runbook
scripts/download_archive.py    generic archive.org downloader (keeps original names)
scripts/install_show.py        archive.org -> SD card, Show/Season_X/Episode_NN.ext
scripts/jf_install_show.py     archive.org -> Jellyfin host, Jellyfin TV naming
scripts/transcode_divx.py      H.264 -> DivX/Xvid AVI + MP3 for older DVD units
scripts/build_avchd.py         AVCHD BDMV authoring via tsMuxeR
```
