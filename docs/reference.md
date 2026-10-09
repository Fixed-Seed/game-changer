# game-changer reference

Everything the [README](../README.md) walkthrough leaves out: every skill, every `fsgc` command, the MCP tools,
and where each agent finds them in a clone. Every `fsgc` command also has `--help` with examples.

## Skills

Agent Skills format, in [`skills/`](../skills/).

| Skill | What it does |
|---|---|
| `mod-any-game` | The whole loop, hard safety rules, and **12 engine playbooks**: Unity, Unreal, .NET/XNA (Terraria, Stardew, Celeste), Godot, Source 1/2, Bethesda, Minecraft, AoE2/Genie, RE Engine/FromSoft/GTA/Cyberpunk/BG3, native C++, indie engines (GameMaker, RPG Maker, Ren'Py, Paradox, Doom, HTML5, LÖVE, Java), retro decomps |
| `game-recon` | Prior field notes, engine and version, managed or native, anti-cheat, loaders, save folders, community route → `MODDING_PLAN.md` |
| `reverse-engineering` | ILSpy / Cpp2IL / Vineflower / Ghidra and IDA over MCP / Cheat Engine / Frida / RenderDoc; reverse-engineer a file format and prove it with a round trip |
| `fixedseed-assets` | Sprites with real transparency, consistent variants, pixel-art items, Minecraft block textures, seamless textures, PBR materials, image- and text-to-3D, remeshing, auto-rigging, text-to-motion, SVG icons, SFX, music, voice lines (stock or cloned), cutscene video, video background removal |
| `asset-pipeline` | Art → engine-exact frames: cutout, nearest-neighbour fit, palettes, sheets, team-colour masks, 3D → 8/16-heading sprites |
| `game-automation` | Launch, screenshot (GPU-safe), click/type safely, windowed mode, crash-reporter cleanup, in-game agent bridges |
| `showcase-video` | Record the window with only the game's audio, pick moments, cut a styled video from an EDL |
| `mashup-mods` | Game inside a game: passthrough mods planned with `fsgc passthrough` (worked example: Minecraft × GTA V), content ports, decomps as libraries, reimplementations |
| `publish-mod` | Lint, package per platform, credits, the post |
| `share-field-notes` | Search the knowledge base, write your own note, open the PR |

## The `fsgc` CLI

| | |
|---|---|
| `fsgc scan` | Find Steam/Epic/Xbox installs; fingerprint engine and version, .NET vs native, anti-cheat, installed loaders, save folders, ranked routes |
| `fsgc passthrough` | Two games at once. `plan` picks the host, lists each engine's hooks, the link contract, milestones with proofs and prior notes (`--out` starts PLAN.md and MODLOG.md); `peer` stands in for either side of the link and checks every message the other side sends |
| `fsgc fixedseed` (`fsgc fs`) | `item` (true pixel-art items), `block` (Minecraft block textures + model files), `sprite`, `image`, `edit`, `rmbg`, `upscale`, `texture`, `pbr`, `maps`, `model3d`, `remesh`, `retexture`, `rig`, `motion`, `vector`, `sfx`, `music`, `voice`, `video`, `video-rmbg`, `run`, `search`, `schema`, `price`, `estimate`, `batch`, `balance`, `result`, `upload`, `mcp`. Plain REST against the FixedSeed API, with a manifest of every generation |
| `fsgc sprite` | `cutout`, `fit`, `pixelate`, `palette`, `sheet`, `slice`, `frames`, `team-mask`, `seamless`, `preview` |
| `fsgc render3d` | GLB → sprite frames from the game's camera (`aoe2`, `iso8`, `trueiso`, `topdown`, `side`, `turntable`) with Blender |
| `fsgc win` | `shot`, `record` (gfxcapture + process-loopback audio), `drive` (input that only reaches the game), `ps`, `kill`, `launch`, `reg` |
| `fsgc video` | `contact` sheets, `compile` (EDL → titled, beat-cut video with music), `mux`, `beats`, `first-frame` |
| `fsgc backup` | Snapshot, diff and restore save folders |
| `fsgc publish check` | Blocks shipping game files, decompiled code and leaked keys |
| `fsgc kb` | The knowledge base: `search`, `show`, `new`, `check`, `index`, `sync`, `pr` |

Two no-build Windows tools ship inside the package (`game_changer/ps1/`): WinDrive input and ProcLoopback
game-only audio, both PowerShell with embedded C#.

Plugin installs and clones put `fsgc` on PATH. Anywhere else:

```bash
uv tool install git+https://github.com/Fixed-Seed/game-changer     # or: pipx install git+...
```

## The FixedSeed MCP server

`fsgc fixedseed mcp` is a stdio MCP server (stdlib only) that reads `FIXEDSEED_KEY`, and optionally
`FIXEDSEED_API` (default `https://run.fixedseed.com`), from the environment.

| Tool | What it does |
|---|---|
| `search_models` | Search the live catalog (no key needed) |
| `get_model` | A model's input schema, example input and price |
| `upload_file` | Upload a local file for model inputs (`generate` does this by itself for local paths) |
| `estimate` | What a plan costs before anything is spent, and the wallet balance |
| `generate` | Queue, wait, download into `out_dir`, a manifest line, previews the agent can see |
| `generate_batch` | Many requests at once under a `max_cents` cap; re-running collects, never pays twice |
| `get_request` | Status of a request; downloads its outputs when it's done |
| `get_balance` | The API wallet |
| `passthrough` | Plan two games running at once (no key needed); also a `passthrough` prompt |

A request the API turns away (the plan's limit of simultaneous requests, the key's spending limit, the wallet)
is never charged, and the error names the limit with its numbers.

## In a clone

- **Instructions:** `AGENTS.md`, which `CLAUDE.md` and `GEMINI.md` point to.
- **Skills:** `.agents/skills` (Codex and others), `.claude/skills`, `.gemini/skills` and `.github/skills` all link
  to `skills/`.
- **MCP config:** `.mcp.json` (Claude Code), `.codex/config.toml` (Codex), `.cursor/mcp.json` (Cursor),
  `.vscode/mcp.json` (VS Code / Copilot), `gemini-extension.json` (Gemini CLI).
- **Tests:** `uv run --with pytest pytest -q tests`. CI also runs `fsgc kb check --index` and
  `fsgc publish check .`.

## Requirements

- Python 3.10+. `bin/fsgc` uses [uv](https://docs.astral.sh/uv/) when it's installed, which sets up its
  dependencies on first run; otherwise it runs the system `python3`, which then needs
  `pip install pillow numpy pyyaml`.
- ffmpeg, for recording and video.
- Blender, only for rendering 3D models into sprites (`fsgc render3d`).
- Windows games are driven natively or from WSL.
