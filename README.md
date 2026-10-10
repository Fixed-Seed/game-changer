<p align="center">
  <img src="docs/media/banner.png" alt="game-changer: a blocky miner on a skateboard fires a rifle at a zombie horde on a sunset city street" width="100%">
</p>

<p align="center">
  <b>Mod almost any PC game you own with an AI agent.</b><br>
  game-changer teaches Claude Code, Codex, Cursor, Gemini CLI and GitHub Copilot to mod a game from start to
  finish: work out how the game can be modded, read its code, build the mod and prove it works in the running
  game. With a <a href="https://fixedseed.com">FixedSeed</a> key it can also make the art, 3D models and sound.
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#what-it-can-do">What it can do</a> ·
  <a href="#ask-for-a-mod">Ask for a mod</a> ·
  <a href="#two-games-at-once">Two games at once</a> ·
  <a href="#field-notes">Field notes</a> ·
  <a href="#examples">Examples</a> ·
  <a href="#art-3d-and-sound-with-fixedseed">Art, 3D and sound</a>
</p>

## Install

You need an AI coding agent, Python 3.10 or newer ([uv](https://docs.astral.sh/uv/) recommended) and ffmpeg. No
account is needed.

In Claude Code, run these two commands, then restart it:

```text
/plugin marketplace add Fixed-Seed/game-changer
/plugin install game-changer@game-changer
```

<details>
<summary>Codex, Gemini CLI, Cursor, VS Code / Copilot, or any other agent</summary>
<br>

| Agent | Install |
|---|---|
| Codex | `codex plugin marketplace add Fixed-Seed/game-changer`, then `codex plugin add game-changer` (or pick it in `/plugins`) |
| Gemini CLI | `gemini extensions install https://github.com/Fixed-Seed/game-changer` |
| Cursor | Paste `https://github.com/Fixed-Seed/game-changer` under Cursor Settings → Plugins, or clone it and open the folder |
| VS Code / Copilot | Turn on `chat.plugins.enabled`, run Chat: Install Plugin From Source and paste the repo URL |
| Skills only (any agent) | `npx skills add https://github.com/Fixed-Seed/game-changer` |
| Anything else | `git clone https://github.com/Fixed-Seed/game-changer` and start your agent inside the folder |

Each one brings the same skills and the `fsgc` command line (skills only: just the skills).
</details>

## What it can do

All of this works without an account:

- Find your installed games and work out how each one can be modded: engine and version, anti-cheat, mod loaders
  already there, save folders and the community's route (`fsgc scan`).
- Read the game's real code, with decompilers for .NET, IL2CPP, Java and native games, and reverse-engineer file
  formats, proved with a round trip.
- Build the mod on the game's own loader, with playbooks for 12 engine families, from Unity and Unreal to
  Bethesda, Minecraft and retro decomps.
- Back up your saves before anything touches them, and restore them (`fsgc backup`).
- Launch, screenshot, drive and record a Windows game, so the agent can test its own mod (`fsgc win`).
- Turn your own art into what the engine loads: cutouts, frame fitting, pixel art, palettes and sprite sheets,
  and 3D models rendered into sprite frames with Blender (`fsgc sprite`, `fsgc render3d`).
- Plan two games running at once (`fsgc passthrough`).
- Cut a showcase video (`fsgc video`), and check a mod for game files and leaked keys before you share it
  (`fsgc publish check`).
- Search and add to the field notes on how other games were modded (`fsgc kb`).

Every command is listed in [docs/reference.md](docs/reference.md), and each one has `--help`.

## Ask for a mod

Start your agent and say what you want:

> Give Terraria the Needler from Halo: pink crystal shots that home in on enemies and burst after a few hits.

The agent loads the mod-any-game skill and works through the same steps for every mod. For the Needler, it:

1. Checks the field notes for Terraria, to see what other agents learned modding it.
2. Finds the game and picks a route: the install, the engine, tModLoader, anti-cheat and save folders, written
   down in `MODDING_PLAN.md`. It stops at online-only games with anti-cheat.
3. Sets up a safe lab. It backs up your saves and asks before installing a mod loader.
4. Reads the code it needs to hook, decompiled outside the repo and never shipped.
5. Builds one working piece first: a Needler that fires, before the homing and the bursts.
6. Makes the sprite, from art you give it or with FixedSeed if you've added a key, and tells you the cost first.
7. Tests it in the game. It launches Terraria, takes screenshots and fires the gun, and asks before it uses your
   mouse and keyboard.
8. Records a clip, and can cut it into a short showcase video.
9. Packages the mod, checked for game files and leaked keys.
10. Writes a field note on what it learned, and opens a pull request with it only if you say so.

More to try:

> Mod Terraria: add a homing missile launcher and a tactical nuke that craters the world.

> Make a new civilization for Age of Empires II.

> Put real Minecraft inside GTA V story mode. Minecraft's camera should follow GTA's, and its TNT should blow
> up GTA cars.

> What engine is `C:\Games\Foo`, and has anyone modded it before?

## Two games at once

A passthrough runs two games side by side with a mod in each. One is the game you play in; the other's picture,
objects, collision and events cross a local link into it. The worked example is real Minecraft inside GTA V. Ask
your agent for one, or plan it yourself:

```bash
# which game hosts, each engine's hooks, the link and the milestones
fsgc passthrough plan minecraft "gta v"

# the same, and it starts PLAN.md and MODLOG.md in a working folder
fsgc passthrough plan skyrim minecraft --out ~/mods/mc-skyrim
```

It stops at online-only games, flags anti-cheat, and falls back to a content port or an embedded library (Mario 64
via libsm64) when a live link isn't possible. The plan is also a `passthrough` tool and prompt on the MCP server.

## Field notes

[`knowledge/`](knowledge/) holds notes on how specific games were actually modded: the exact versions that worked,
the route and why, how it was verified, and every gotcha (symptom → cause → fix). Agents read them before they
start and write one when they finish, so the next agent starts where yours stopped. Browse
[`knowledge/INDEX.md`](knowledge/INDEX.md), or search from anywhere:

```bash
fsgc kb search "grand theft auto"
```

Every game is welcome. The rules for adding a note, for humans and AIs, are in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Examples

- [Seed Arsenal](examples/terraria-tmodloader) for Terraria (tModLoader): a homing missile launcher, a tactical
  nuke with a crater and a mushroom cloud, a chain-lightning rifle, a black-hole gun, an orbital strike, three new
  enemies and a two-phase Drone Mothership boss.
- [San Franciscans](examples/aoe2-de-civ) for Age of Empires II DE: a new civilization with a Robotaxi unique unit
  and Delivery Drones rendered from 3D models at the game's camera angle, a Transamerica Pyramid wonder, and a
  reverse-engineered `.sld` sprite writer.
- [Minecraft inside GTA V](examples/minecraft-gta5-passthrough): a Fabric mod and a ScriptHookV + ReShade add-on
  share the camera, ground and events. Minecraft's frame is depth-composited into GTA's, its TNT, arrows and
  fireworks become GTA explosions and bullets, and its mobs fight the police.

Each has a field note with every non-obvious lesson.

## Rules it follows

- It works on games you own: single-player, multiplayer, or servers you host. It won't touch online games with
  anti-cheat, write cheats against other players, or get around anti-cheat, DRM or ownership checks.
- It never ships game files or decompiled code. Mods ship as code, your own assets, patches or converters.
- It backs up your saves before touching them, and stops programs by process ID only.
- It asks before using your mouse and keyboard, installing loaders into game folders, or publishing anything,
  pull requests included.

Full reasoning: [`skills/mod-any-game/references/safety.md`](skills/mod-any-game/references/safety.md).

## Art, 3D and sound with FixedSeed

With a FixedSeed key, the agent can also make what the mod needs: sprites with real transparency, pixel-art items,
Minecraft block textures, seamless and PBR textures, 3D models from a picture or a sentence, rigs and animation,
SVG icons, sound effects, music, voice lines and video. The FixedSeed MCP server already comes with the install,
and it starts working once the key is set. Every file lands in `assets/gen/` with a line in
`fixedseed_manifest.jsonl` (model, inputs, request id), so any asset can be traced and made again.

<p align="center">
  <img src="docs/media/quickstart.gif" alt="Getting started in five steps: go to fixedseed.com, sign in with Google, create an API key, add API credits, and give the key to your agent" width="100%">
</p>

To set it up:

1. Go to [fixedseed.com](https://fixedseed.com) and choose Get an API key.
2. Sign in with Google.
3. Create a key and copy it. It's shown only once. You can give the key a spending limit, and the API stops it
   there whatever the agent does.
4. Add credits under API billing, from $10 to $1,000. Credits can be spent for a year, and failed requests aren't
   charged.
5. Set the key in the terminal you start your agent from, then restart the agent:

   ```bash
   export FIXEDSEED_KEY=sk_live_...
   ```

   In PowerShell it's `$env:FIXEDSEED_KEY = "sk_live_..."`. To keep the key for new terminals, add the `export`
   line to `~/.zshrc` or `~/.bashrc`, or run `setx FIXEDSEED_KEY "sk_live_..."` once on Windows. In Claude Code,
   `/mcp` then lists fixedseed as connected.

How spending works:

- The agent prices a plan before it spends anything, and asks you before going over about $5.
- Many assets go out as one batch under a cap. Asking again for the same thing within an hour collects the
  earlier result instead of paying twice.
- A request the API turns away costs nothing, whether it hit the key's spending limit, an empty wallet or too many
  requests at once, and the agent is told which limit it was.

Things to ask for:

> Make five new Terraria weapons as pixel-art sprites, and keep the art under a dollar.

> Retexture Minecraft's cobblestone, stone bricks and oak logs as mossy ruins, as a resource pack.

> Give my Age of Empires II civilization a unique unit, rendered from a 3D model.

The same commands work in your own terminal:

```bash
# a pixel-art item, ready for Terraria
fsgc fixedseed item "a copper shortsword with a leather grip"

# 16 px block textures, with the Minecraft model files
fsgc fixedseed block "mossy cobblestone" --namespace mymod

# what a plan costs, before anything is spent
fsgc fixedseed estimate fixedseed/item-sprite:10 tencent/hunyuan3d-3.1:2

# many requests at once, under a cap
fsgc fixedseed batch plan.json --max-cents 300
```
