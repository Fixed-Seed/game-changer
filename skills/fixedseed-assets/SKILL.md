---
name: fixedseed-assets
description: Generate game assets with FixedSeed (fixedseed.com) through the bundled FixedSeed MCP server or the `fsgc fixedseed` CLI. Covers sprites and icons with transparent backgrounds, consistent variants and animation frames, pixel art, seamless textures, PBR material maps, depth/normal/albedo maps, image-to-3D and text-to-3D models, upscaling, sound effects, music, voice lines with cloning, and trailer or cutscene video. Use whenever a mod needs new art, audio or 3D models, or the user mentions FixedSeed, generating sprites, textures, models, SFX or music for a game.
---

# Game assets with FixedSeed

FixedSeed runs image, video, 3D, audio and language models behind one API key and one prepaid wallet. Use it
whenever the mod needs something that doesn't exist yet: a weapon sprite, a boss, a unit rendered from 16
angles, a tileable floor, a laser sound, boss music, a voiced line.

## Setup (check once per session)
- **Key.** `FIXEDSEED_KEY` must be set (create one at https://fixedseed.com/developers/keys and top up the API
  wallet at https://fixedseed.com/developers/billing). `fsgc fixedseed` also reads it from a `.env` file
  (`FIXEDSEED_KEY=...`) in the working folder. Never write the key into mod files; `fsgc publish check` flags
  leaked keys. `fsgc fixedseed balance` shows the wallet.
- **A key for the agent.** Suggest the user gives the agent its own key with a spend limit (monthly or
  lifetime, set when creating the key at https://fixedseed.com/developers/keys). The API stops that key at
  its limit whatever the agent does, so a runaway loop can't drain the wallet.
- **MCP.** The FixedSeed MCP server ships with this repo: `fsgc fixedseed mcp` (stdio, stdlib only). It reads
  `FIXEDSEED_KEY` (and optionally `FIXEDSEED_API`, default `https://run.fixedseed.com`) from the environment.
  It's pre-configured for each agent:
  - Claude Code: `.mcp.json`
  - Codex: `.codex/config.toml`
  - Cursor: `.cursor/mcp.json`
  - VS Code/Copilot: `.vscode/mcp.json`
  - Gemini CLI: `gemini-extension.json`

  To add it by hand:
  - Claude Code: `claude mcp add fixedseed -e FIXEDSEED_KEY=$FIXEDSEED_KEY -- /path/to/repo/bin/fsgc fixedseed mcp`
  - Codex (`~/.codex/config.toml`): `[mcp_servers.fixedseed]` with `command = "/path/to/repo/bin/fsgc"`,
    `args = ["fixedseed", "mcp"]` and `env_vars = ["FIXEDSEED_KEY"]`
  - anything else: a stdio server whose command is `bin/fsgc fixedseed mcp`.

  MCP tools: `search_models`, `get_model` (input schema, example, price), `upload_file`, `estimate` (what a
  plan costs), `generate` (queue, wait, download into `out_dir`, manifest line, previews),
  `generate_batch` (many at once under a `max_cents` cap), `get_request` (finish a long job),
  `get_balance`. The same server has a `passthrough` tool and prompt for running two games at once (see the
  mashup-mods skill).
- **Plain HTTP** works too: `https://run.fixedseed.com/v1/llms.txt` documents every endpoint and model with
  current prices, and `/v1/openapi.yaml` is the contract.

## Which interface
- **Discovery** (which model for X, its inputs, its price): MCP `search_models` / `get_model`, or
  `fsgc fixedseed search "<words>" [--kind image|video|audio|model]`, `fsgc fixedseed schema <model>`,
  `fsgc fixedseed price <model>`. The catalog is public and live, so these need no key. The defaults below were
  current in October 2026; check before a big batch.
- **Anything that must land on disk** (every game asset): `fsgc fixedseed <recipe>` or MCP `generate`. Both
  upload local inputs through `/v1/files`, queue, poll, download every output file, and append the model,
  inputs and request id to `<out>/fixedseed_manifest.jsonl`, so every asset can be traced and regenerated.
- **Long jobs** (video, 3D, long music): MCP `generate` with `wait: false` (or let it time out) returns a
  `request_id`; collect it with `get_request` or `fsgc fixedseed result <request_id>`.
- **Retries never pay twice:** MCP `generate` and `generate_batch` (and `fsgc fixedseed batch`) record every
  request in `<out>/.fixedseed_ledger.jsonl`. Asking again for the same model, input and name within an
  hour (after a timeout, a crash, a dropped connection) collects the earlier request. For a new variation,
  change the name or pass `fresh: true` (`--fresh`). A result never replaces an earlier file.
- **Many assets at once** (every item of a mod, a set of sounds): MCP `generate_batch` with `max_cents`, or
  `fsgc fixedseed batch plan.json --max-cents 300` with a plan of `{"model", "input", "name"}` jobs. New
  requests over the cap are refused before anything is spent; whatever is still running comes back as
  pending, and running the same batch again collects it.
- **Look at what came back:** MCP results carry small previews (sprites enlarged with hard edges, an
  archive's `preview.png`, video keyframes, audio waveforms). Check them before building on a result.

## Recipes (`fsgc fixedseed <recipe> --help` for options; `fsgc fs` is the same; `--model` overrides the model; `--set k=v` passes extra inputs)

| Asset | Command | Default model |
|---|---|---|
| Game item as true pixel art: exact grid, small palette, outline; Terraria's 2x style or plain | `fsgc fixedseed item "<the item>" [--style pixel] [--size 24] [--orientation diagonal]` | `fixedseed/item-sprite` (transparent PNG) |
| Voxel block: seamless 16/32 px face textures + Minecraft model, blockstate and item files | `fsgc fixedseed block "<material>" --namespace <modid> [--faces column\|top_bottom] [--block id]` | `fixedseed/block-texture` (ZIP, unpacked with its `assets/` tree and `preview.png`) |
| Sprite / icon, transparent background | `fsgc fixedseed sprite "<subject, view, style>" --name x` | `openai/gpt-image-2.5-sunburst` (`background=transparent`) |
| Concept art, key art, backgrounds | `fsgc fixedseed image "<prompt>" --aspect 16:9` | `google/nano-banana-2` |
| Consistent variants, extra frames, recolors, same character new pose | `fsgc fixedseed edit "<change>" --ref base.png` | `google/nano-banana-2` (`image_urls`) |
| Background removal (soft matting, no prompt) | `fsgc fixedseed rmbg in.png [--mode matting]` | `birefnet/v2` |
| Clean pixel art from any image | `fsgc sprite pixelate in.png out.png --size 32x32 --colors 24` (local, grid-exact) | none needed |
| Upscale | `fsgc fixedseed upscale in.png --factor 4x` | `topaz/image-upscale` |
| Seamless tiling texture | `fsgc fixedseed texture "mossy cobblestone" [--tiling horizontal]` | `tongyi/z-image-turbo-tiling` |
| PBR material (basecolor, normal, roughness, metalness, height) | `fsgc fixedseed pbr "rusted sheet metal" [--upscale 2]` | `patina/material` (ZIP, unpacked) |
| Depth / normal / albedo map of any image | `fsgc fixedseed maps in.png --map normals` | `fixedseed/image-maps` |
| Image → textured 3D model (GLB) | `fsgc fixedseed model3d concept.png [--engine trellis\|hunyuan\|tripo\|meshy]` | `microsoft/trellis-2` |
| Text → 3D model (GLB) | `fsgc fixedseed model3d --prompt "low-poly treasure chest"` | `tencent/hunyuan3d-3.1` |
| Game-ready low-poly remesh | `fsgc fixedseed remesh unit.glb --faces 8000 [--engine meshy]` | `tripo/remesh` |
| New texture on an existing mesh | `fsgc fixedseed retexture unit.glb reference.png` | `microsoft/trellis-2-retexture` |
| Auto-rig a humanoid (+ walk/run, optional preset) | `fsgc fixedseed rig character.glb [--animate 92]` | `meshy/rigging` (ZIP: GLB + FBX + animations) |
| Text → humanoid animation clip | `fsgc fixedseed motion "swings a greatsword overhead" --seconds 4` | `tencent/hunyuan-motion` (FBX) |
| SVG icons, emblems, UI art | `fsgc fixedseed vector "shield emblem icon" --color "#e4b355"` | `recraft/v4.1-text-to-vector` |
| Sound effect | `fsgc fixedseed sfx "plasma rifle shot, punchy" --seconds 1.2 [--loop]` | `elevenlabs/sound-effects-v2` |
| Music | `fsgc fixedseed music "tense boss battle, chiptune, 150 bpm" --seconds 90 [--vocals]` | `elevenlabs/music-v2.5` (`--engine song`: `fixedseed/song`, with lyrics) |
| Voice line, stock voice | `fsgc fixedseed voice "You dare challenge me?" --voice George` | `elevenlabs/eleven-v3` |
| Voice line, cloned | `fsgc fixedseed voice "..." --voice-ref actor.wav --direction "gruff dwarf"` | `bytedance/seed-audio-1.0` |
| Trailer / cutscene clip | `fsgc fixedseed video still.png "camera orbits the boss"` | `bytedance/seedance-2.5-i2v` |
| Video background removal (alpha) | `fsgc fixedseed video-rmbg clip.mp4 [--format mov]` | `pixelcut/video-background-removal` (WebM/ProRes 4444) |
| Anything else | `fsgc fixedseed run <model> key=value key:=json image_url=@local.png` | any |

Results with several files (rigs, PBR sets, motion clips, SVG, alpha video) arrive as one ZIP that `fsgc fixedseed`
and the MCP `generate` tool unpack into `<out>/<name>/`, with a `manifest.json` listing the files.

Other useful models (`fsgc fixedseed schema <model>` for inputs):
- Images: `openai/gpt-image-2.5-flare`, `google/nano-banana-pro`, `black-forest-labs/flux-2-pro`,
  `qwen/image-edit-max` (precise edits), `ideogram/v4` (lettering, logos), `bytedance/seedream-5-pro`.
- Upscale: `topaz/bloom-2-image` (creative upscale for low-res art), `black-forest-labs/flux-image-upscaler`.
- Video: `bytedance/seedance-2.5-t2v` / `-r2v` (reference-driven shots), `minimax/h3-max-i2v`, `google/veo-3.1`,
  `kling/video-v3-pro-motion-control` (copy motion from a reference clip), `topaz/video-upscale`.
- Characters: `fixedseed/character-turnaround` (6-panel turnaround sheet video from 1-3 refs),
  `fixedseed/character-expressions` (expression sheet).
- Audio: `deepgram/nova-3` (speech-to-text, e.g. subtitles for a showcase).
- Text: chat models through `POST /v1/chat/completions` (OpenAI format) for item names, dialogue and lore.

## Prompting game art that fits the game
- **Look at the game's own assets first:** pixel size, outline, palette, perspective, facing, how busy they
  are. Put that into a reusable style suffix. For Terraria: *"16-bit pixel art game sprite in the style of
  Terraria, crisp dark outline, limited palette, centered, plain flat white background, no shadow, no
  text"*.
- **Describe the view and orientation explicitly:** "perfectly horizontal side view with the muzzle pointing
  right" for held weapons, "seen from the side facing left" for enemies, "pointing straight down" for a
  falling bomb. Engines have conventions (Terraria items point right, NPCs face left) and fixing
  orientation afterwards costs quality.
- **Backgrounds:** transparent (`fsgc fixedseed sprite`, GPT Image 2.5 with `background=transparent`) or a flat
  colour that `fsgc sprite cutout` can flood-fill. Avoid gradients, scenery and ground shadows. If a soft shadow
  sneaks in, use `--grey` / `--keep-top` in cutout.
- **Player / team colour:** ask for "bright saturated blue accents" on the parts that should take the
  player's colour, then `fsgc sprite team-mask --hue blue` turns them into a mask.
- **Consistency across a set:** generate one hero image, then derive the rest with `fsgc fixedseed edit` and
  the hero as `--ref` ("same robot, now firing, muzzle flash"; refer to refs as @Image1, @Image2). Don't ask
  one prompt for a whole sprite sheet; grids come out uneven.
- **Many angles or frames of the same object:** go 3D. Take the concept, run `fsgc fixedseed model3d`, then
  `fsgc render3d` from the game's camera (asset-pipeline skill). That's how the AoE2 robotaxi got 16
  consistent headings × 5 animations. Generated meshes are dense: `fsgc fixedseed remesh --faces 8000` before
  shipping real-time 3D. For characters, `fixedseed/character-turnaround` gives matched front/side/back views
  to model or draw from.
- **Pixel art:** generate at 1K with a pixel-art prompt, then snap it to the real grid and palette locally
  with `fsgc sprite pixelate` / `fsgc sprite palette --from <game sprite>`; it uses the game's exact frame size.
- **No text or logos** in art unless wanted: models love to add them.

## Rigging and animation
- **Humanoids:** `fsgc fixedseed model3d char.png --engine meshy --set pose=a-pose` gives a clean A-pose, then
  `fsgc fixedseed rig char.glb` adds a skeleton plus walking and running clips (GLB and FBX); `--animate <id>`
  adds a preset from Meshy's animation library (0 = idle).
- **Custom moves:** `fsgc fixedseed motion "<what the character does>"` returns an FBX clip on a standard humanoid
  skeleton; retarget it in Blender or the engine (Unity Humanoid, Unreal IK Retargeter).
- **Sprites:** `fsgc render3d --anims` animates rigid parts procedurally, and `fsgc sprite frames` makes quick idle
  loops. For video-driven motion, `kling/video-v3-pro-motion-control` transfers motion from a reference clip.

## Audio for engines
- Every audio result is a WAV (ElevenLabs at 44.1/48 kHz, Song at 48 kHz stereo). Convert to what the engine
  wants:
  - `ffmpeg -i x.wav -ar 44100 x_44k.wav` (XNA/tModLoader, most engines);
  - `ffmpeg -i x.wav -c:a libvorbis -q:a 5 x.ogg` (Minecraft, Godot, Unity);
  - trim silence first: `-af silenceremove=start_periods=1:start_threshold=-50dB`.
- Loops: `fsgc fixedseed sfx ... --loop`, or ask Song for a loopable track and crossfade the ends.
- Keep SFX short (0.2-2 s) and normalize loudness (`-af loudnorm=I=-16`) so they sit with the game's own
  sounds.

## Cost and etiquette
- **Price the expensive stuff:** every model lists `starting_charge_cents` and `maximum_charge_cents`
  (`fsgc fixedseed price <model>` / MCP `get_model`). Before 3D, video, long music or any batch, run
  `fsgc fixedseed estimate model[:count] ...` (MCP `estimate`) and tell the user the range; ask before
  spending more than about $5. Failed requests are not charged.
- **Iterate cheap:** use low quality or resolution while exploring (`--quality low`, `--res 512` / `1K`),
  then re-run the winners at full quality with the same prompt (and seed where the model takes one).
- **Reproducibility:** keep `fixedseed_manifest.jsonl` with the assets; it records prompts, inputs and
  request ids.
- **Credits:** in the mod's README, credit that assets were generated with FixedSeed and name the models.
  Check the model's provider terms for commercial use (https://fixedseed.com/docs).
