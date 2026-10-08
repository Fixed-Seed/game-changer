---
kind: game
title: "An RL agent that beats the Eye of Cthulhu: decompiled boss AI to a simulator, then back into the real game"
game: "Terraria"
games_also: []
game_version: "Terraria 1.4.5.8 (decompiled), tModLoader 1.4.4.9 base for the in-game agent"
platform: windows
engine: xna-fna
route: loader-api
tools: ["ilspycmd", "numpy", "numba", "PufferLib 3", "PyTorch", "cloud H100s (training)", "tModLoader"]
anti_cheat: "none (single player)"
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: ["Fixed Seed"]
date: 2026-09-28
links: []
tags: [reinforcement-learning, simulator, sim-to-real, decompile, trace-replay, float32, boss-ai]
---

# An RL agent that beats the Eye of Cthulhu: decompiled boss AI to a simulator, then back into the real game

> The Eye of Cthulhu fight was ported from Terraria's decompiled source into a vectorized simulator: boss
> AI, servants, player physics, gun and damage rules. A PufferLib PPO agent trained in it (99.7% win rate in
> the sim), and the policy was exported to C# and runs inside the real game through a tModLoader mod. Real
> traces were replayed against the sim until they matched.

## Setup
- **Decompiles:** Terraria 1.4.5.8 with `ilspycmd` into a folder outside the repo. tModLoader's 1.4.4.9
  base decompiled too. The two were diffed: the Eye's AI is identical, apart from refactors like
  `ClearTarget()` vs `target = 255`.
- **Training:** Python 3.12 with PufferLib 3.0.0, locally on an RTX 4090 and on rented cloud H100s.
- **In game:** a tModLoader mod builds an arena identical to the sim, runs fights back to back, and logs
  results plus per-frame traces.

## Route and why
The loader API for the in-game half. The interesting part is **reimplementation-as-simulator**: the real
game runs at 60 fps with rendering, far too slow for RL. A faithful port of just the fight runs about 170k
steps/s.

## How the game works (what we had to learn)
- **The Eye:** NPC aiStyle 4, two phases, dashes and hovers. Its servants use aiStyle 5.
- **Player movement:** acceleration, max speed, jump height/time and gravity all come straight from the
  player update code.
- **Damage:** variance, defense and crits, hurt immunity frames, knockback.
- **Gun:** Minishark + musket balls, fire rate, projectile speed.
- **Time:** the fight's state machine is driven by `ai[]` counters that tick per frame.
- **Obs/action space:** 52 floats. MultiDiscrete [move 3, jump 2, fire 2, aim 32].

## Build steps
1. Decompile, then read `NPC.AI` for aiStyle 4/5 and the player update. Write a vectorized numpy port;
   later a numba one, float32-exact with the numpy version.
2. Wrap it as a PufferLib env and train PPO (30M local steps → 35% wins; 150M → 99.7%).
3. Export the policy MLP to plain C# weights. The mod reads the same observation every 3 frames and drives
   the player's controls.
4. Record real fights and compare them to the sim with trace replay.

## Verification
- **Trace replay:** feed the real game's state at frame t and its action into the sim, then compare the
  sim's t+1 to the real t+1, per variable.
- **Sim-to-real:** win rate over many fights in the real game.

## Gotchas
1. **Trace replay disagreed on every dash.**
   - **Cause:** the action applied on frame t takes effect on t+1; the sim was applying it one frame early.
   - **Fix:** apply frame t+1's action. The Eye's velocity then matched 99.9%.
2. **The numba sim slowly diverged from the numpy one.**
   - **Cause:** `0.2` (float64) is not `0.2f`.
   - **Fix:** use float32 constants and literals everywhere, like the C# does.
3. **The player moved faster in the real game than in the sim.**
   - **Cause:** a hidden buff. Standing near sunflowers gives *Happy!*, which is x1.21 move speed.
   - **Fix:** block the buff in the arena. Replays find what reading the code misses.
4. **PufferLib 3.0.0's sdist wouldn't build.**
   - **Cause:** its bundled demo C environments fail to compile.
   - **Fix:** build a wheel with `NO_OCEAN=1` and a one-line `setup.py` fix. It pins numpy<2 and its torch
     ABI.
5. **Cloud training failed to start.**
   - **Cause:** the key in use was an inference-API key without compute permissions.
   - **Fix:** log in with the provider's CLI (device flow, approved by the human).
6. **Recording from inside the mod leaked memory.** See the Seed Arsenal note: capture the window from
   outside instead.

## Assets
A FixedSeed-generated reskin of the Eye and servants (`black-forest-labs/flux-1-dev` → `fsgc sprite`) for the video.

## Cost and time
Roughly two days of sessions (approximate), plus cloud GPU time for the large runs.

## Open questions
- Expert mode, and other bosses (the port pattern generalizes).
- An LLM "coach" that writes tactics for the policy. A scaffold exists; it isn't evaluated.
