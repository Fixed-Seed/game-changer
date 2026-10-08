---
kind: game
title: "San Franciscans: a new civilization for Age of Empires II DE with units rendered from 3D"
game: "Age of Empires II: Definitive Edition"
games_also: []
game_version: "AoE2 DE (Steam), September 2026 build"
platform: windows
engine: genie
route: data
tools: ["genieutils-py", "AoE2ScenarioParser", "FixedSeed (flux-1-dev, hunyuan3d-3.1)", "Blender", "fsgc render3d", "sld.py (custom)", "WinDrive", "ffmpeg gfxcapture"]
anti_cheat: "none for single player / lobbies (ranked uses unmodded data)"
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: ["Fixed Seed"]
date: 2026-09-29
links: ["https://github.com/Fixed-Seed/game-changer/tree/main/examples/aoe2-de-civ"]
tags: [civilization, data-mod, sld, sprite-format, reverse-engineering, 3d-to-sprite, player-colour, scenario]
---

# San Franciscans: a new civilization for Age of Empires II DE with units rendered from 3D

> A playable civilization with its own bonuses, unique techs, a Transamerica Pyramid wonder, and a Robotaxi
> unique unit plus Delivery Drones. The units are FixedSeed image → FixedSeed 3D → Blender renders from AoE2's camera,
> written into the game's `.sld` sprite format, which we reverse-engineered. It's tested in game and
> recorded. Code: `examples/aoe2-de-civ`.

## Setup
- **Game:** AoE2 DE from Steam.
- **Local mods:** `%USERPROFILE%\Games\Age of Empires 2 DE\<steamid>\mods\local\<Mod>`.
- **Tools:** Python 3.11+ with `genieutils-py` for the `.dat` and `AoE2ScenarioParser` for the demo map;
  Blender 5 for the renders.

## Route and why
A **data mod** (the `.dat`, JSON, strings) plus graphics. The Genie engine keeps units, techs and civs in
one binary `.dat` that genieutils reads and writes, so no code injection is needed.

## How the game works (what we had to learn)
- **Loading:** a mod with a `.dat` is a **data mod**. It only applies when picked in the skirmish lobby's
  "Data Mod" dropdown; the Mod Manager shows a gear icon, not a checkbox.
- **The civ picker is limited by the exe:** it only lists civs in the executable's hard-coded civ-id table
  (index-based UI tables). A new civ must **replace a slot** (we used the Burgundians, 36). Extra civs
  load and play but never appear.
- **Strings:** DE's key-value tables keep DLL help strings at `id − 79000`, e.g. Knight help 105068 → key
  26068.
- **Icons:** in-game command-panel icons come from the base game's prebuilt `widgetui` atlas, which a local
  mod can't extend. Menus, the civ picker and the tech tree read `wpfg/resources/` art, which a mod can
  override.
- **Castle units:** unique units need `creatable_type` 2. Tech 266 ("Castle built") never fires for
  scenario-placed castles.
- **SLD sprites:** a header, then frames. Each frame has a canvas, a hotspot and a layer mask:
  - main layer: BC1 (DXT1);
  - shadow and player colour: BC4;
  - damage mask: BC1;
  - every layer is 4x4 blocks with skip/draw command runs;
  - a "copy from previous frame" flag.

  Units: 16 headings clockwise from east, the hotspot at the ground point, and an extra trailing frame.
- **The camera:** orthographic, 30° elevation (2:1 tiles).

## Build steps
1. **Sprites:**
   1. `fsgc fixedseed run black-forest-labs/flux-1-dev` (or `fsgc fixedseed image`) for the concept (white background, **saturated blue trim** where player colour
      goes).
   2. `fsgc fixedseed model3d` for the GLB.
   3. `fsgc render3d --preset aoe2 --shadows` for the frames.
   4. `make_sprites.py pack`: blue → player mask, burnt death frames, then `.sld`.
2. **Data:** `build_mod.py`:
   1. copy the Britons' tech tree into the replaced slot;
   2. deep-copy template units, then adjust stats, graphics and train location;
   3. add unique techs and bonus effects;
   4. append strings, icons, `civilizations.json`, `unitlines.json` and `futuravailableunits.json`.
3. **Install** into `mods/local/`, then pick the Data Mod in a skirmish lobby.

## Verification
- **SLD writer:** round-trip the stock knight (decode → encode → decode) to 0.91/255 mean error before
  writing a single new file.
- **One unit first:** it went into a test scenario and we screenshotted it next to stock units for scale,
  facing and player colour.
- **Crash bisection:** a scenario-row trial script that reports whether the game survives.

## Gotchas
1. **The new civ never showed in the picker.**
   - **Cause:** the exe's hard-coded civ table.
   - **Fix:** replace a slot.
2. **The mod seemed to do nothing.**
   - **Cause:** data mods need picking in the lobby's Data Mod dropdown.
3. **Unique unit help text was blank.**
   - **Cause:** help strings live at `id − 79000` in DE.
4. **In-game icons stayed stock.**
   - **Cause:** the widgetui atlas can't be extended by local mods.
   - **Fix:** use stock icons in game and custom art in the menus.
5. **The Robotaxi was never trainable in the scenario.**
   - **Cause:** tech 266 doesn't fire for placed castles.
   - **Fix:** gate on Castle Age.
6. **A Britons tech's tech-tree entry pointed at the wrong unit.**
   - **Cause:** a text replace of `"ID": 8,` in `futuravailableunits.json` also hit the Town Watch tech
     (ID 8).
   - **Fix:** edit only the `Units` lists, structurally.
7. **The ultrawide capture wouldn't encode.**
   - **Cause:** NVENC H.264 max width is 4096.
   - **Fix:** capture the centre 16:9 of the 5120x1440 screen.
8. **Steam said "already running" after a crash.**
   - **Cause:** BugSplat's `BsSndRpt64.exe` lingered.
   - **Fix:** kill it by PID.
9. **Clicks landed on the wrong buttons.**
   - **Cause:** the windowed game drops the foreground on clicks.
   - **Fix:** treat "nothing in the foreground and the cursor over the game" as safe (WinDrive does).
     Set any window size via registry `Windowed Width/Height` (1936x1119 → a 1920x1080 client).

## Assets
- FLUX.1 [dev] concepts (`black-forest-labs/flux-1-dev`) in a "clean studio product render, three-quarter view, white background" style,
  with blue accents for player colour.
- Image-to-3D for the GLBs: TRELLIS made the shipped meshes; `fsgc fixedseed model3d` regenerates them with
  Hunyuan3D 3.1 (`tencent/hunyuan3d-3.1`).
- The wonder was painted directly in AoE2's projection and fitted to the 5x5 footprint. It's a single frame,
  so no 3D was needed.

## Cost and time
About a day, most of it on reverse-engineering the SLD format and on the civ-picker limit. Generation spend was
a few dollars.

## Open questions
- Truly adding a 64th civ would mean patching the exe's civ tables. That's out of scope for a data mod.
