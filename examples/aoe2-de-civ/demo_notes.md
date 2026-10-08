# How the demo was recorded

The demo (a quick look at the civ picker, then a scripted battle on the `sf_demo` scenario) was
recorded from the real game, driven from WSL. The original scripts hardcoded click positions for one
5120x1440 full-screen setup, so they are not copied here. This is the same process with the repo's
tools. Everything below needs Windows (native or WSL) and the game.

Before driving the game, back up the profile (`fsgc backup create "<profile folder>" --name aoe2-profile`),
and ask the person at the PC before taking over their mouse and keyboard.

## 1. Build and install

```bash
python build_mod.py --install          # data mod -> <profile>/mods/local/SanFranciscans
python make_scenario.py demo --install # sf_demo -> <profile>/resources/_common/scenario
fsgc win setup                           # PowerShell tools + an ffmpeg with gfxcapture, picks the video encoder
```

## 2. Window mode and size (registry)

The in-game list of windowed sizes stops at 1366x768. The registry takes any size. Change it while
the game is closed. All values are `REG_DWORD`, under
`HKCU\Software\Microsoft\Microsoft Games\Age of Empires II DE`:

| value | meaning |
|---|---|
| `Mode Display` | 1 = full screen, 0 = windowed |
| `Windowed Width`, `Windowed Height` | any size. 1936 x 1119 gives a 1920x1080 client area (the rest is the frame) |
| `Windowed X Pos`, `Windowed Y Pos` | window position |
| `ResolutionX`, `ResolutionY` | full-screen resolution, 0 = native |

```bash
KEY='HKCU\Software\Microsoft\Microsoft Games\Age of Empires II DE'
fsgc win reg get "$KEY"                          # current values
fsgc win reg set "$KEY" "Mode Display" 0         # set backs the key up first (%LOCALAPPDATA%\game-changer\reg-backups)
fsgc win reg set "$KEY" "Windowed Width" 1936
fsgc win reg set "$KEY" "Windowed Height" 1119
```

With the game already windowed, WinDrive can also resize it: `fsgc win drive --proc AoE2DE_s "size 1920 1080"`.
The shipped demo was recorded full screen at 5120x1440 (`Mode Display` 1, native resolution).

## 3. Launch, and clean up after a crash

```bash
fsgc win launch --steam 813780     # AoE2 DE's Steam app id
fsgc win ps AoE2DE                 # pid, process name, window title
```

A crash leaves BugSplat's crash reporter (`BsSndRpt64.exe`) running, and Steam then refuses to start
the game ("already running"). Find it and kill it by its exact PID before relaunching:

```bash
fsgc win ps BsSndRpt64             # or: powershell.exe -Command "(Get-Process BsSndRpt64).Id"
fsgc win kill <pid>
```

## 4. Find click positions

```bash
fsgc win shot --exe AoE2DE_s.exe shot.png --scale 0.33
```

This captures the game window (Windows.Graphics.Capture, so GPU frames are not black), plus
`shot_small.png` at 1/3 scale, which is cheap to look at. Read a button's position in the small
image and multiply by 3 to get client coordinates for WinDrive. Crop the full-size shot to read small
text.

## 5. Drive the lobby

```bash
fsgc win drive --proc AoE2DE_s "focus" "key 0x1B" "click 1770 450"
```

From Python, for a longer script:

```python
from game_changer.win import Drive
d = Drive("AoE2DE_s"); d.focus(); d.click(1770, 450); d.type("San"); d.wheel(120)
```

Input only goes through while the game is the foreground window, or while nothing is and the cursor
is over the game (the windowed game can drop the foreground on clicks). `Drive.cmd` takes the
foreground back once and retries when it drifted.

The click path, with the positions used on the 5120x1440 full-screen window (they only hold for that
size and UI scale; find your own with step 4). Wait 1.5-4 s after each click for the menu to settle.

| step | client position (5120x1440) |
|---|---|
| Esc three times: skip the intro videos | `key 0x1B` |
| Single Player | 1770, 450 |
| "I've done this before" (only if the first-time prompt shows) | 2742, 816 |
| Skirmish | 2250, 700 |
| **Data Mod** dropdown, then our mod (the first entry) | 3291, 357 then 3291, 426 |
| Player 1's civ: open the picker | 2508, 519 |
| picker search box, type `San` | 1530, 198 |
| San Franciscans (opens the description panel) | 2118, 339 |
| Confirm | 2155, 1344 |
| Game Mode dropdown, then Custom Scenario | 3291, 468 then 3240, 789 |
| scenario list search box, type `sf_demo` | 1965, 324 |
| first row, then Load | 1734, 492 then 2547, 1233 |
| Game Speed, then Normal | 3291, 723 then 3190, 824 |
| Reveal Map, then All Visible | 3290, 768 then 3205, 867 |
| Start Game | 2598, 1233 |
| once the map shows: zoom in two notches | `wheel 120` twice |

The data mod has to be picked in the lobby: a mod with a `.dat` only applies when chosen in the
skirmish lobby's Data Mod dropdown. The Mod Manager lists local mods with a gear icon, not a checkbox.

## 6. Record

Two takes per run: A, the civ picker (from opening it to the description panel), and B, the battle
(started just before clicking Start Game; the loading screen is trimmed afterwards).

```bash
mkdir -p /mnt/c/caps             # the Windows ffmpeg writes there; it doesn't create folders
fsgc win record --exe AoE2DE_s.exe --out 'C:\caps\take3_a' --crop 1280:0:1280:0 --seconds 8
```

- Video: gfxcapture of the game window only, into an `.mkv` so a crash doesn't lose the take. Audio:
  a WASAPI process-loopback capture of just the game. A `.json` records the timing that syncs them.
- NVENC H.264 is limited to 4096 px wide, so a 5120x1440 screen can't be encoded whole.
  `--crop 1280:0:1280:0` (left:top:right:bottom) keeps the centre 2560x1440, which is 16:9 with the
  HUD at the far edges. Without a crop, `fsgc win record` scales down to 4096 wide under NVENC.

`fsgc win record` blocks while it records, so for take A drive the picker from a second shell. Take B
has to start recording and then click Start, which is easier from Python:

```python
import time
from game_changer.win import Drive, Recorder
d = Drive("AoE2DE_s"); d.focus(); d.cmd("move 2560 720")
rec = Recorder(exe="AoE2DE_s.exe", out=r"C:\caps\take3_b", crop=(1280, 0, 1280, 0)).start()
d.click(2598, 1233)                      # Start Game
time.sleep(2.6); d.wheel(120); d.wheel(120)
time.sleep(60)
rec.stop()
```

Then make each take an mp4 and find the moments:

```bash
fsgc video mux /mnt/c/caps/take3_b.mkv /mnt/c/caps/take3_b.audio.raw /mnt/c/caps/take3_b.json take3_b.mp4
fsgc video contact take3_b.mp4 sheet_b.png --every 2    # a timestamped grid of frames: pick the in/out points
```

`fsgc video first-frame take.mkv` finds the first bright, busy frame, which skips a loading screen when
a take starts on one. Take B starts in the lobby, which already counts as busy, so its in-point (5.0 s)
came from the contact sheet.

## 7. Cut

The shipped cut is 51.6 s: 2.6 s of the civ picker (from 1.15 s into take A), a 0.5 s crossfade into
the battle (from 5.0 s into take B, 49.5 s of it), one-line titles and a 0.8 s fade-out. Style: short
one-line titles naming what is on screen, no smaller explanatory lines, about 2-3 s of menus before
gameplay, the game's own audio.

The same edit as an EDL for `fsgc video compile edl.json sf_civ_demo.mp4`. The battle is split into
segments joined by cuts, so that each title gets its own segment. The theme copies the original
dark-and-gold captions. Compiled from the original takes, it reproduces the shipped cut shot for shot
(51.6 s).

```json
{"size": [1920, 1080], "fps": 30, "clip_volume": 1.0, "fade_out": 0.8,
 "theme": {"accent": "#D6AA5A", "text": "#F5E1AA", "chip": "#140E08B9"},
 "transition": {"type": "cut"},
 "segments": [
  {"clip": "take3_a.mp4", "in": 1.15, "dur": 2.6, "title": "A new civilization for Age of Empires II", "title_delay": 0.15},
  {"clip": "take3_b.mp4", "in": 5.0, "dur": 3.4, "title": "Wonder: the Transamerica Pyramid", "title_delay": 0, "title_hold": 2.5,
   "transition": {"type": "fade", "duration": 0.5}},
  {"clip": "take3_b.mp4", "in": 8.4, "dur": 8.1, "title": "Robotaxis and Delivery Drones", "title_delay": 0, "title_hold": 6.2},
  {"clip": "take3_b.mp4", "in": 16.5, "dur": 16.0, "title": "San Franciscans vs. the Franks", "title_delay": 0, "title_hold": 4.0},
  {"clip": "take3_b.mp4", "in": 32.5, "dur": 18.5, "title": "Move Fast and Break Things", "title_delay": 0, "title_hold": 5.0},
  {"clip": "take3_b.mp4", "in": 51.0, "dur": 3.5, "title": "San Franciscans", "title_delay": 0}
 ]}
```

The scenario's triggers set the camera path and the fight: the camera starts on the city, moves to
the army at 6 s, the attack-move starts at 9-10 s, Move Fast and Break Things is researched at 30 s,
the raid on the Franks' village starts at 34 s, and the camera returns home at 74 s (game seconds at
Normal speed, `make_scenario.py demo`).
