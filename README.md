# dvd-player-ai

Put kids' shows on an SD card so a cheap DVD player can play them.

## The one thing that matters

**Cheap DVD players cannot play H.264.** That is the format almost every video uses
today. Feed it to this kind of player and it shows an error, goes black, and restarts.

Convert the videos to **Xvid + MP3 in an `.avi` file** instead. That works.

## Quick start

```bash
# 1. format the card (ERASES IT - check the disk number first!)
diskutil list
diskutil eraseDisk MS-DOS MYCARD MBRFormat /dev/disk4

# 2. convert videos onto it
python3 scripts/to_sunpin_avi.py /Volumes/MYCARD --show all

# 3. clean up Mac junk files and eject
find /Volumes/MYCARD -name '._*' -delete
diskutil eject /Volumes/MYCARD
```

## The settings that work

| Setting | Use this | Not this |
|---|---|---|
| Video | Xvid (MPEG-4 Part 2) | H.264 |
| Audio | MP3 | AAC |
| File type | `.avi` | `.mp4` |
| Size | 720x480 | anything bigger than 720x576 |
| Card | 32GB FAT32 | exFAT, GPT |

The ffmpeg command:

```bash
ffmpeg -i input.mp4 \
  -c:v mpeg4 -vtag XVID -b:v 700k \
  -vf "scale=720:480,setdar=16/9" \
  -c:a libmp3lame -b:a 96k -ar 48000 -ac 2 \
  output.avi
```

About 43MB per 7-minute episode, or 160MB per 26-minute episode.

## If it still doesn't work

Try these in order. Stop when it works.

1. **Does an empty card work?** Format it, put nothing on it, insert it.
   - Player is fine -> the problem is your video files. Go to step 2.
   - Player still dies -> the problem is the card or the slot. Go to step 4.
2. **Put ONE video on the card.** Easier to test than 200.
3. **Already using Xvid `.avi` and still failing?** Try MPEG-2 instead. It is what real
   DVDs use, so every player can read it:
   `ffmpeg -i input.mp4 -target ntsc-dvd output.mpg`
4. **Try a different card**, ideally a smaller one. Some players only handle 8GB or less
   even when the box says more.
5. **Insert the card while the player is OFF**, then turn it on. Some players brown out
   and reset when a card is plugged in live.
6. **Still dead with every card?** The slot is probably broken. Use the warranty.

## Gotchas that cost us hours

- **"MP4" on a box usually means Xvid**, not H.264. Box specs lie by being vague.
- **The player auto-plays** when you insert the card. Press **STOP** to get the file list,
  then arrows and OK to pick something. There is also a **DVD/USB/CARD** button to switch
  what it reads from.
- **Macs leave junk files** (`._filename`) next to every file you copy. Some players list
  them as broken videos. Delete them before ejecting: `find /Volumes/CARD -name '._*' -delete`.
- **Keep the card plugged in** while converting. If it unmounts the job dies.
- **Zero-pad names** (`S01E01`, not `S1E1`) or the player sorts episode 10 before episode 2.
- **A one-episode page can hide a whole series.** Check what an archive.org item actually
  contains before planning around its title.
- **Check `mediatype` on archive.org.** One item titled "Cars the movie" was 393 photos
  and no video at all.

## Our setup

Videos live on a Jellyfin server (`192.168.8.114:8096`), and the scripts pull from there
to build cards. 274 episodes: Bluey (170), Clifford the Big Red Dog (65), Clifford's
Puppy Days (39). Roughly 24GB as Xvid, which fits a 32GB card.

Player tested: **SUNPIN PD969 / PD901** portable DVD player. Its maker's FAQ lists
`VOB, AVI, MPEG 1, MPEG 2, MPEG 4, XVID` video and `MP3, WMA` audio, max 720x576.
H.264 and AAC are not on that list. The error it throws on an H.264 file is `814E`,
which is documented nowhere we could find.

## Scripts

| Script | What it does |
|---|---|
| `to_sunpin_avi.py` | Jellyfin -> Xvid AVI on the card. **Use this one.** |
| `shrink_to_sd.py` | Jellyfin -> smaller H.264 mp4. For players that DO support H.264. |
| `jf_install_show.py` | archive.org -> Jellyfin, named so Jellyfin detects episodes |
| `install_show.py` | archive.org -> SD card as mp4 |
| `download_archive.py` | archive.org -> plain download, original filenames |
| `transcode_divx.py` | Batch H.264 -> Xvid AVI, local files |
| `build_avchd.py` | Makes an AVCHD disc structure. Only for Blu-ray-style players. |

All of them skip files that are already done, so you can re-run after a failure.
