---
kind: technique
title: "Recording real game footage with only the game's audio"
tags: [recording, gfxcapture, wasapi, process-loopback, nvenc, audio-sync, showcase]
date: 2026-09-30
agents: ["Claude Code (Opus 5.5)"]
humans: ["Fixed Seed"]
links: []
---

# Recording real game footage with only the game's audio

> Capture one game window (GPU frames, not the desktop) and one process's sound (no Discord pings, no
> Spotify), synced, then cut. `fsgc win record` + `fsgc video mux` do this on Windows, including from WSL.

## When to use it
Showcase videos, bug evidence, and oracles that need to see motion.

## How
- **Video:** ffmpeg's `gfxcapture` source (Windows.Graphics.Capture) on the game's window
  (`window_exe=` or `hwnd=`). It gets the real frames even when the window is covered. Encode with
  NVENC/AMF/QSV and write **.mkv**.
- **Audio:** WASAPI **process loopback** of the game's PID (`game_changer/ps1/ProcLoopback.ps1`). Write raw f32 stereo
  48 kHz, placed by QPC timestamps with gaps filled with silence, so file position = wall time.
- **Sync:** record both start times, then mux with the offset. Fine-tune with a visual/audio event (a flash
  vs its boom).
- **Pacing:** script the take (mod-side timeline or director), so a reshoot is one command.

## Gotchas
1. **Black frames.** GDI/`gdigrab` can't see GPU-rendered games. Use gfxcapture (or `ddagrab` for the whole
   monitor).
2. **Empty .mkv, and ffmpeg ignores 'q'.**
   - **Cause:** gfxcapture only delivers a frame when the window redraws. A paused game, static menu or
     minimized window produces nothing, and ffmpeg is stuck waiting.
   - **Fix:** record while the game is rendering. Stop from a background thread, with a kill after a
     timeout.
3. **Never stop ffmpeg from the game's main thread.** If the game blocks, gfxcapture stalls and the 'q' is
   never read. The tail of the take is lost.
4. **NVENC H.264 is limited to 4096 px wide.** Crop 32:9 screens to the centre 16:9, scale down, or use
   HEVC.
5. **Reading the back buffer from inside the game can leak.** FNA3D's D3D11 `ReadBackbuffer` allocated a
   staging texture per call (17 GB in one take). Capture from outside.
6. **The game's audio can't be redirected.** Many engines (FAudio, Unity, Unreal) talk to WASAPI directly,
   so SDL/driver tricks do nothing. Use process loopback.
7. **Audio a few hundred ms early.** ffmpeg + capture + encoder startup takes about 0.25-0.3 s before the
   first frame. Account for it in the mux, and measure once per machine.

## Seen in
- [Seed Arsenal (Terraria)](../games/terraria/seed-arsenal-tmodloader.md)
- [San Franciscans (AoE2)](../games/age-of-empires-ii-de/san-franciscans-civ.md)
- [Minecraft inside GTA V](../games/gta-v/minecraft-passthrough.md)
