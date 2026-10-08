"""game-changer: tools any AI agent (Claude Code, Codex, Cursor, Gemini CLI, ...) uses to mod games.

Subcommands (see `fsgc --help`):
  scan         find installed games and fingerprint one: engine, runtime, anti-cheat, mod loaders, routes
  passthrough  two games at once: host and guest, hooks, link and milestones; a stand-in for either side of the link
  fixedseed    generate game assets with FixedSeed (sprites, textures, PBR maps, 3D, SFX, music, voice, video); alias fs
  sprite       cut out, fit, pixelate, recolor and pack 2D sprites
  render3d     render a GLB into sprite frames from a game's camera (Blender)
  video        compile styled showcase videos, trim, mux
  win          Windows (and WSL): screenshots, recording with game-only audio, input, processes
  backup       snapshot and restore save folders before you touch them
  publish      lint a mod folder before sharing: game files, decompiled code, secrets, credits
  kb           the knowledge base: search prior field notes, write your own, check it, open a PR
"""

__version__ = "0.2.0"
