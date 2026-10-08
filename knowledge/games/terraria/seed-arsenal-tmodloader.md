---
kind: game
title: "Seed Arsenal: missiles, a tactical nuke, new enemies and a boss for Terraria"
game: "Terraria"
games_also: []
game_version: "Terraria 1.4.4.9 via tModLoader 2026.07 (GitHub build), Steam; vanilla 1.4.5.8 decompiled for reference"
platform: windows
engine: xna-fna
route: loader-api
tools: ["tModLoader", "ilspycmd", "FixedSeed (black-forest-labs/flux-1-dev)", "fsgc sprite", "ffmpeg gfxcapture", "ProcLoopback"]
anti_cheat: "none (single player)"
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: ["Fixed Seed"]
date: 2026-09-28
links: ["https://github.com/Fixed-Seed/game-changer/tree/main/examples/terraria-tmodloader"]
tags: [weapons, projectiles, boss, npc-ai, sprites, explosions, camera, showcase-video]
---

# Seed Arsenal: missiles, a tactical nuke, new enemies and a boss for Terraria

> Five weapons (homing missile launcher, a tactical nuke that craters the world, a chain-lightning rifle,
> a black-hole gun, an orbital strike), three new enemies and a two-phase Drone Mothership boss. All
> sprites were generated with FixedSeed. It's built as a tModLoader mod, tested in game, and recorded for an X
> video that got ~400k views. Code: `examples/terraria-tmodloader`.

## Setup
- **Loader:** tModLoader, the free Steam app **1281930**. It must be in the Steam library or it won't start.
  The GitHub build was used, with an isolated save folder.
- **Reference source:** `ilspycmd -p` on `Terraria.exe`, into a folder outside the repo.
- **Art:** FixedSeed `black-forest-labs/flux-1-dev` → `fsgc sprite` (cutout, fit, sheet).

## Route and why
**Loader API.** tModLoader exposes everything as C# subclasses:
- `ModItem`, `ModProjectile`, `ModNPC` for content;
- `ModSystem` for world hooks;
- `ModCommand` for test commands;
- MonoMod detours (`On_Main.DoUpdate += ...`) when you need vanilla internals.

No reason to go lower.

## How the game works (what we had to learn)
- **NPC sheets:** frame height = texture height / `Main.npcFrameCount[type]`, so any consistent frame
  size works. Vertical strips.
- **Orientation:** items are drawn pointing right. NPC sprites face left and the engine flips them.
  Projectile rotation 0 means pointing right, unless you draw it yourself in `PreDraw`.
- **Vanilla AI styles:** aiStyle 3, the "fighter", flees in daylight, so a daytime walker enemy needs custom
  `AI()`. Slimes can reuse aiStyle 1.
- **World edits:** destroying tiles is `WorldGen.KillTile`. For multiplayer, follow vanilla explosives' net
  messages.
- **Camera:** you can steer it through `ModSystem.ModifyScreenPosition`; screen shake via
  `PunchCameraModifier`.
- **Lab mode:**
  - `-tmlsavedirectory <dir>` isolates saves;
  - `-skipselect Player:World` loads straight into a world;
  - `Main.instance.InactiveSleepTime = TimeSpan.Zero` keeps full speed while unfocused.

## Build steps
1. Put `SeedArsenal/` in `Documents/My Games/Terraria/tModLoader/ModSources/`.
2. In game: Workshop > Develop Mods > Build + Reload. Or from the command line:
   `dotnet tModLoader.dll -build <ModSources>/SeedArsenal`.
3. Get the items with `/arsenal` (or the recipes), and summon the boss with `/mothership`.

## Verification
- **In game:** `client.log` shows the load, and screenshots of the window show sprite scale and orientation.
- **Scripted scene:** a showcase `ModSystem` spawns waves on a timeline and fires the weapons, so a take
  reproduces exactly.
- **Builds:** the example compiles to a `.tmod` with 0 warnings on three command-line routes (`dotnet build`,
  and `tModLoader.dll -build` on the SDK and on the bundled runtime). The in-game Build + Reload wasn't re-run
  for the ported example.
- **Not verified:** multiplayer.

## Gotchas
1. **Recording from inside the game leaked 17 GB of memory in one take.**
   - **Cause:** this FNA3D's D3D11 `ReadBackbuffer` allocates a full-size staging texture per call.
   - **Fix:** capture the window from outside with ffmpeg `gfxcapture=hwnd=...`.
2. **`SDL_AUDIODRIVER=disk` recorded nothing.**
   - **Cause:** FAudio on Windows talks to WASAPI directly.
   - **Fix:** use a process-loopback capture of the game's PID (`game_changer/ps1/ProcLoopback.ps1`).
3. **The recording's tail was lost.**
   - **Cause:** gfxcapture stalls on a frozen window, so ffmpeg never read the 'q'.
   - **Fix:** send 'q', then wait on a background thread. Never block the game's main thread. Write
     `.mkv`, which survives a kill.
4. **Takes stopped matching.**
   - **Cause:** explosions crater the showcase world.
   - **Fix:** restore a pristine copy of the world before every take (`fsgc backup`).
5. **tModLoader refuses to start.**
   - **Cause:** the free tModLoader app isn't in the Steam library.
   - **Fix:** add it. Never patch the check.
6. **The agent killed its own shell.**
   - **Cause:** `pkill -f <pattern>` matched the agent's own command line.
   - **Fix:** kill by exact PID only.
7. **Sprites came out with grey fringes or a floor shadow.**
   - **Cause:** the generated art had soft shadows under objects.
   - **Fix:** flood-fill cutout with a grey tolerance or keep-top (`fsgc sprite cutout --grey 150 --keep-top 0.8`),
     then one nearest-neighbour fit.

## Assets
- **Prompt style:** "16-bit pixel art game sprite in the style of Terraria, crisp dark outline, limited
  palette, centered, plain flat white background, no shadow, no text" plus the object and its orientation
  ("perfectly horizontal side view, muzzle pointing right").
- **Frame sizes:** launcher 64x26, missile 38x16, nuke 40x84, boss 240x150 x2 frames.

## Cost and time
Roughly a day for the weapons and showcase, and another half-day for the boss set (approximate), with one
agent and a human reviewing clips. Image generation cost a few dollars.

## Open questions
- Multiplayer sync for the nuke's world edits at scale.
- A proper boss arena and loot table beyond the showcase.
