# game-changer

A game-modding toolkit and a shared knowledge base for AI coding agents: Claude Code, Codex, Cursor, Gemini
CLI, GitHub Copilot, OpenCode and anything else that reads `AGENTS.md`. When someone opens an agent in this
repo, they almost always want to **mod a game**, or to learn how a game was modded.

## Start here
1. **Read `skills/mod-any-game/SKILL.md` and follow its loop:** intake → recon → route → lab (backups) →
   source of truth → vertical slice → assets → verify in the real game → showcase → publish.
2. **Search the knowledge base first:** `bin/fsgc kb search "<game or engine>"`. Other agents may already have
   written down the exact versions, routes and gotchas (`knowledge/INDEX.md`).
3. **At the end, share what you learned:** write a field note (`bin/fsgc kb new ...`) and, once your human
   agrees, open a PR (`bin/fsgc kb pr <note> --yes`). See `knowledge/README.md` and `CONTRIBUTING.md`.

## Tools
- **`bin/fsgc`** is the Python CLI, and it sets itself up with `uv`.
  - Put it on PATH: `export PATH="$PWD/bin:$PATH"`, or install it anywhere with
    `uv tool install git+https://github.com/Fixed-Seed/game-changer`.
  - Every group has `--help`:
    - `scan`: installed games, engine, anti-cheat, loaders, saves, routes
    - `passthrough`: two games at once. `plan` picks the host, each engine's hooks, the link and milestones;
      `peer` stands in for either side of the link
    - `fixedseed` (alias `fs`): sprites, textures, PBR, 3D, remeshes, rigs, motion, SVG, SFX, music, voice, video via the
      FixedSeed API (`https://run.fixedseed.com`, key in `FIXEDSEED_KEY`)
    - `sprite` / `render3d`: art → engine-ready frames
    - `win`: launch, screenshot, input, record on Windows (also from WSL)
    - `video`: contact sheets and EDL showcase edits
    - `backup`: snapshot and restore saves
    - `publish`: pre-release lint
    - `kb`: the knowledge base
- **FixedSeed MCP server:** ships in this repo as `bin/fsgc fixedseed mcp` (stdio, stdlib only; code in
  `game_changer/fixedseed_mcp.py`). It reads `FIXEDSEED_KEY` from the environment. It also has a `passthrough`
  tool and prompt (the same plan as `fsgc passthrough plan`), which need no key.
  - It's pre-configured per agent: `.mcp.json` (Claude Code), `.codex/config.toml` (Codex),
    `.cursor/mcp.json` (Cursor), `.vscode/mcp.json` (VS Code / Copilot), `gemini-extension.json`
    (Gemini CLI).
  - No MCP? `fsgc fixedseed` does the same from the shell.
- **Skills** (`skills/*/SKILL.md`, Agent Skills format) are also linked where each agent looks for them:
  `.agents/skills` (Codex and others), `.claude/skills`, `.gemini/skills`, `.github/skills`.
- **Engine playbooks:** `skills/mod-any-game/references/engines/`.
- **Worked examples:** `examples/terraria-tmodloader`, `examples/aoe2-de-civ`,
  `examples/minecraft-gta5-passthrough`.

## Rules (full reasoning in `skills/mod-any-game/references/safety.md`)
- **What you can mod:** any game the user owns: single-player, multiplayer, or servers the user hosts.
  - Never touch online clients protected by anti-cheat.
  - Never write cheats against other players (aimbots, ESP, speed hacks).
  - Never bypass anti-cheat, DRM or ownership checks.
- **Saves:** `fsgc backup` saves before modded launches.
- **What you ship:** never commit or publish game files, extracted assets or decompiled code. Keep
  decompiles outside the repo.
- **Processes:** kill by exact PID (`fsgc win kill`), never by name pattern.
- **Ask first** before:
  - driving the user's mouse and keyboard, and never focus a game with an online mode while they're typing;
  - installing loaders into game folders or changing the registry;
  - publishing anything, PRs included.
- **Keep a journal:** a `MODLOG.md` in the mod's working folder. It becomes your field note at the end.

## Working on the toolkit itself
- **Python:** 3.10+, deps Pillow, numpy and PyYAML (`uv` handles them via `bin/fsgc`). Code lives in `game_changer/`,
  one module per CLI group, each with `register(sub)` and a docstring that doubles as `--help`.
- **Windows tools:** `game_changer/ps1/*.ps1` embed C# 5 (Windows PowerShell 5.1's compiler): no string
  interpolation, no `out var`, no expression-bodied members.
- **Tests:** `uv run --with pytest pytest -q tests`. CI also runs `fsgc kb check --index` and
  `fsgc publish check .`.
- **Wording:** keep skills and docs agent-neutral ("the agent", not a product name) except in sections
  about one specific agent.
