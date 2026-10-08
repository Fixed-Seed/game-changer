"""Plan a passthrough: two games running at once, a mod in each, one game drawn inside the other.

    fsgc passthrough plan minecraft "gta v"                   # host and guest, hooks, link, milestones, prior art
    fsgc passthrough plan minecraft skyrim --host minecraft   # choose the game you play in
    fsgc passthrough plan minecraft "gta v" --idea "build with blocks in Los Santos" --out ~/mods/mc-gta
    fsgc passthrough plan "D:\\Games\\Foo" doom --json        # install folders work too; --json for agents
    fsgc passthrough peer --as host --port 25600              # stand in for the host while the guest's mod is built
    fsgc passthrough peer --as guest --port 25600 --log peer.jsonl

The host is the game you play in. Its camera drives the guest, the guest's picture (or stand-ins for its objects)
is drawn into the host's frame against the host's depth, and the host's collision goes back so the guest's things
stand on the host's world. `plan` fingerprints each game with `fsgc scan` when it's installed (otherwise from a
table of well-known games), stops at online-only games, flags anti-cheat, picks the host, lists what each engine
offers, and proposes the link, the milestones with the proof each one needs, and the field notes to read first.
It only reads; `--out` writes PLAN.md and MODLOG.md and never replaces a file. `peer` speaks the link (TCP on
127.0.0.1, one JSON object per line) as either side and checks every message the other side sends: the oracle for
the first milestones. The method is the mashup-mods skill; examples/minecraft-gta5-passthrough is a working one.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import select
import socket
import sys
import time
import zlib
from pathlib import Path

from game_changer import __version__
from game_changer import scan
from game_changer.common import die, emit, to_posix

LINK_VERSION = 1
REPO_URL = "https://github.com/Fixed-Seed/game-changer/blob/main/"
ROOT = Path(__file__).resolve().parents[1]
METHOD = "skills/mashup-mods/SKILL.md"
PLAYBOOKS = "skills/mod-any-game/references/engines/"
ORACLES = "knowledge/techniques/oracles-how-agents-know-a-mod-works.md"
EXAMPLE = "examples/minecraft-gta5-passthrough"
SCORE = {0: "not possible", 1: "hard", 2: "workable", 3: "easy or proven"}

# --------------------------------------------------------------------------- what each engine offers


def _b(label, dim, host, guest, playbook, code, cam_out=None, cam_in=None, draw=None, picture=None, world_out=None,
       world_in=None, notes=()):
    """host / guest: how well the engine plays that role (0 = not possible ... 3 = easy or proven)."""
    return dict(label=label, dim=dim, host=host, guest=guest, playbook=playbook, code=code, cam_out=cam_out,
                cam_in=cam_in, draw=draw, picture=picture, world_out=world_out, world_in=world_in, notes=list(notes))


BRIDGE = {
    "minecraft": _b(
        "Minecraft Java (Fabric)", "3d", 2, 3, "minecraft.md",
        code="a Fabric mod (Java, Mixin), run from its own launcher profile so the player's worlds stay untouched",
        cam_out="the client camera (position, yaw, pitch, FOV) from a render mixin",
        cam_in="set from the link every frame (Camera / GameRenderer mixins), with view bobbing, sky, fog and clouds "
               "off",
        draw="the other game's objects rebuilt as blocks and entities, or its picture on a dynamic texture",
        picture="colour + depth read back after the world pass, the hand and HUD as a separate layer, into named "
                "shared memory; it keeps rendering unfocused (pause on focus loss off) at the host's picture size",
        world_out="the blocks around the player",
        world_in="the host's ground and walls as barrier blocks around the player",
        notes=["Java Edition only: Bedrock has no Fabric."]),
    "rage": _b(
        "Rockstar RAGE", "3d", 3, 1, "big-frameworks.md",
        code="a ScriptHookV script (C++ .asi through the ASI loader), story mode only",
        cam_out="GET_FINAL_RENDERED_CAM_COORD / _ROT / _FOV every frame; they describe the frame being prepared, one "
                "ahead of the screen",
        cam_in="a script camera (CREATE_CAM, SET_CAM_PARAMS, RENDER_SCRIPT_CAMS)",
        draw="a ReShade add-on, loaded as ReShade64.asi through the ASI loader, composites the guest against GTA's "
             "reversed-Z depth; invisible props stand in for guest objects",
        picture="a ReShade add-on reading back colour + depth",
        world_out="ground probes (GET_GROUND_Z_FOR_3D_COORD) and shape tests around the player",
        world_in="invisible collision props (keep them to a few hundred script objects)",
        notes=["GTA V Legacy is proven (examples/minecraft-gta5-passthrough); Enhanced (DX12) needs another "
               "compositor path."]),
    "creation": _b(
        "Bethesda Creation", "3d", 3, 1, "bethesda.md",
        code="a script-extender plugin in C++ (SKSE with CommonLibSSE-NG, F4SE, SFSE or xNVSE), with Papyrus for "
             "game logic",
        cam_out="the PlayerCamera and its NiCamera's world-to-camera matrix, read by the plugin every frame",
        cam_in="a free camera driven by the plugin",
        draw="spawned references (PlaceAtMe with your own meshes) that the game lights and shadows, or a ReShade "
             "add-on composite against the game's depth",
        picture="a ReShade add-on readback",
        world_out="ray casts from the plugin around the player",
        world_in="invisible collision references",
        notes=["The 2026 Minecraft-in-Skyrim clip had Steve in Skyrim's own lighting: spawned geometry, not a flat "
               "overlay."]),
    "fromsoft": _b(
        "FromSoftware", "3d", 2, 1, "big-frameworks.md",
        code="a native DLL (C++ or Rust) loaded by ModEngine2 or me3, which start the game offline",
        cam_out="the camera's matrices in game memory (find them with RenderDoc and Cheat Engine; community structs "
                "help)",
        cam_in="the same structs, written every frame (hard)",
        draw="a ReShade add-on (or your own Present hook) compositing against the game's depth",
        picture="a ReShade add-on readback",
        world_out="the game's own ray cast, reversed from the binary (hard), or the nearby collision mesh exported "
                  "once",
        world_in="invisible map objects (hard)"),
    "unity-mono": _b(
        "Unity (Mono)", "any", 3, 3, "unity.md",
        code="a BepInEx 5 plugin (C#) with HarmonyX patches",
        cam_out="Camera.main: its transform, fieldOfView, worldToCameraMatrix and projectionMatrix",
        cam_in="the camera's transform and fieldOfView, set in LateUpdate",
        draw="real scene objects: meshes for the guest's geometry, or a quad textured from shared memory, so Unity's "
             "depth and lighting apply",
        picture="a camera into a RenderTexture (colour + depth), AsyncGPUReadback, then a MemoryMappedFile",
        world_out="Physics.Raycast and OverlapBox around the player",
        world_in="invisible BoxColliders",
        notes=["Check the render pipeline (built-in, URP or HDRP) before hooking rendering."]),
    "unreal": _b(
        "Unreal Engine", "3d", 2, 1, "unreal.md",
        code="UE4SS: Lua mods for logic, C++ mods for anything per frame",
        cam_out="the PlayerCameraManager (GetCameraLocation, GetCameraRotation, GetFOVAngle)",
        cam_in="a C++ mod that overrides the view every frame",
        draw="spawned actors (static or procedural meshes), or a ReShade add-on composite against scene depth when "
             "the game exposes it",
        picture="a SceneCapture2D into a render target, from a C++ mod",
        world_out="LineTraceSingle and BoxOverlapActors (KismetSystemLibrary) around the player",
        world_in="spawned invisible blocking actors",
        notes=["Check depth before betting on ReShade: UE5 games can hide or jitter it "
               "(knowledge/games/black-myth-wukong/reshade-depth-dead-end.md)."]),
    "godot": _b(
        "Godot", "any", 2, 2, "godot.md",
        code="the project recovered with GDRE Tools, patched through a PCK overlay or Godot Mod Loader, with a "
             "GDExtension for shared memory",
        cam_out="get_viewport().get_camera_3d(): its global_transform and fov",
        cam_in="that camera's transform and fov, set from the link",
        draw="MeshInstance3D nodes for the guest's geometry, or a quad with an ImageTexture",
        picture="a SubViewport rendering from the host's camera (get_image() is slow; a GDExtension reads it back "
                "faster)",
        world_out="PhysicsDirectSpaceState3D.intersect_ray and intersect_shape",
        world_in="StaticBody3D collision shapes",
        notes=["StreamPeerTCP is built in, so the link is easy from GDScript."]),
    "xna-fna": _b(
        "XNA / FNA / MonoGame (.NET)", "2d", 2, 2, "dotnet-xna.md",
        code="the game's loader in C# (tModLoader, SMAPI or Everest), else Harmony / MonoMod",
        cam_out="the screen position (Terraria: Main.screenPosition; Stardew: Game1.viewport)",
        cam_in="the screen position, set from the link",
        draw="SpriteBatch in a draw hook: a Texture2D filled from shared memory, or sprites at world positions",
        picture="draw into a RenderTarget2D, GetData, then a MemoryMappedFile",
        world_out="the tiles around the player",
        world_in="solid tiles or invisible platforms"),
    "source": _b(
        "Source", "3d", 2, 1, "source.md",
        code="a Source SDK 2013 mod (C++) for single player, or a server plugin on a listen server you run",
        cam_out="the view setup (eye position, angles, FOV) in the SDK",
        cam_in="a point_viewcontrol, or camera code in an SDK mod",
        draw="an SDK mod renders anything (custom meshes, a dynamic texture on a prop); a stock game gets props and "
             "sprites",
        picture="an SDK mod rendering to a texture",
        world_out="UTIL_TraceLine / enginetrace",
        world_in="invisible brushes or props",
        notes=["VAC: never on official servers; local and -insecure only."]),
    "gmod": _b(
        "Garry's Mod (Source + Lua)", "3d", 3, 1, "source.md",
        code="Lua addons (client and server), plus a binary module (gmcl_*.dll) for sockets or shared memory",
        cam_out="the CalcView hook / render.GetViewSetup()",
        cam_in="the CalcView hook",
        draw="clientside models and the mesh library in PostDrawOpaqueRenderables, or a render-target material",
        picture="render.Capture (slow), or a binary module",
        world_out="util.TraceLine and util.TraceHull",
        world_in="invisible props with physics",
        notes=["G64 (Super Mario 64 inside Garry's Mod, via libsm64) is the reference embed."]),
    "source2": _b(
        "Source 2", "3d", 1, 0, "source.md",
        code="Workshop Tools addons with VScript and Panorama",
        cam_out="the player's eye position and angles, from VScript",
        draw="map entities and particles spawned from VScript",
        world_out="VScript traces",
        notes=["VScript has no sockets, so a live link needs a file or console bridge; a content port usually fits "
               "better."]),
    "re-engine": _b(
        "Capcom RE Engine", "3d", 2, 1, "big-frameworks.md",
        code="REFramework: Lua scripts, or C++ plugins",
        cam_out="sdk.get_primary_camera(): its world matrix and FOV",
        cam_in="the camera's transform, written by a script every frame",
        draw="REFramework's d2d / imgui overlays, or a ReShade add-on composite against the game's depth",
        picture="a ReShade add-on readback",
        world_out="the game's own ray casts through sdk.call_native_func (title by title)",
        world_in="title by title (hard)",
        notes=["Online parts (lobbies, ranked) stay unmodded."]),
    "redengine": _b(
        "CD Projekt REDengine", "3d", 2, 1, "big-frameworks.md",
        code="Cyber Engine Tweaks (Lua) for logic, RED4ext (C++) per frame, ArchiveXL / TweakXL for new records",
        cam_out="the active camera's world transform and FOV",
        cam_in="the way free-camera mods do it, from RED4ext",
        draw="spawned entities (ArchiveXL meshes), or a ReShade add-on composite against the game's depth",
        picture="a ReShade add-on readback",
        world_out="ray casts through the spatial queries system",
        world_in="spawned invisible entities"),
    "doom": _b(
        "Doom-engine source port", "3d", 2, 3, "misc-engines.md",
        code="your fork of an open-source port (Chocolate Doom, GZDoom, dsda-doom)",
        cam_out="the player's view, in the port's code",
        cam_in="the player's view, set from the link in the port",
        draw="anything: the port is your code",
        picture="the port's framebuffer into shared memory",
        world_out="the port's own line and blockmap traces",
        world_in="things or lines the port spawns",
        notes=["The user's own IWAD (doom.wad, doom2.wad) is the game data; ship code only."]),
    "idtech": _b(
        "id Tech", "3d", 1, 1, "misc-engines.md",
        code="WAD / PK3 / PK4 data mods; native hooks for code",
        draw="a ReShade add-on composite against the game's depth",
        picture="a ReShade add-on readback",
        notes=["Classic Doom and Quake are open source: fork a source port instead (name the game \"doom\")."]),
    "sm64": _b(
        "Super Mario 64 decomp (libsm64)", "3d", 0, 3, "retro-decomp.md",
        code="libsm64: the decomp as a library, built from the user's own ROM",
        cam_in="none needed: the host draws Mario with its own camera",
        picture="Mario's mesh, returned by the library every tick for the host to draw",
        world_in="the host's collision triangles near Mario, loaded into the library",
        notes=["One process and no link: the host's mod calls the library."]),
    "genie": _b(
        "Genie (Age of Empires DE)", "2d", 0, 0, "genie-aoe2.md",
        code="data mods (the .dat via genieutils), scenarios and AI scripts; no code plugins",
        notes=["No runtime code hook: bring the other game's content into the data instead (examples/aoe2-de-civ)."]),
    "clausewitz": _b(
        "Paradox Clausewitz / Jomini", "2d", 0, 0, "misc-engines.md",
        code="plain-text script mods",
        notes=["No sockets or code hooks: port content as script mods."]),
    "gamemaker": _b(
        "GameMaker", "2d", 1, 1, "misc-engines.md",
        code="GML edits in data.win with UndertaleModTool",
        cam_out="view_camera[0] (camera_get_view_x / _y)",
        cam_in="camera_set_view_pos",
        draw="draw events: sprite_add and surfaces for the guest's picture",
        picture="a surface copied into a buffer (buffer_get_surface) and sent over the socket",
        world_out="collision functions around the player (collision_rectangle, place_meeting)",
        world_in="solid instances",
        notes=["network_create_socket gives you the link."]),
    "rpgmaker-mvmz": _b(
        "RPG Maker MV / MZ (NW.js)", "2d", 1, 1, "misc-engines.md",
        code="a JavaScript plugin in js/plugins (NW.js has Node's net module)",
        cam_out="the map scroll ($gameMap.displayX / displayY)",
        cam_in="$gameMap.setDisplayPos",
        draw="PIXI sprites in the current scene",
        picture="the renderer's extract (slow)",
        world_out="$gameMap.isPassable",
        world_in="events used as obstacles"),
    "rpgmaker-rgss": _b(
        "RPG Maker XP / VX / VX Ace (RGSS)", "2d", 1, 0, "misc-engines.md",
        code="Ruby in Scripts.rvdata2 (Win32API for sockets)",
        draw="sprites in the current scene",
        notes=["Old and 2D: port content unless you need its runtime."]),
    "renpy": _b(
        "Ren'Py", "2d", 1, 0, "misc-engines.md",
        code="Python in .rpy files (sockets and threads work)",
        draw="displayables updated from the link",
        notes=["A visual novel: show the other game as a scene, or react to its events."]),
    "dotnet": _b(
        ".NET application", "any", 1, 1, "dotnet-xna.md",
        code="Harmony / MonoMod patches through BepInEx or a launcher",
        notes=["It depends on what the game is built on: read the exe with ILSpy first."]),
    "electron": _b(
        "Electron / NW.js / HTML5", "any", 2, 2, "misc-engines.md",
        code="patched JavaScript in resources/app.asar (or package.nw); Node's net module where Node is enabled",
        cam_out="the engine's camera object (Phaser, Construct, three.js ...)",
        cam_in="the same camera object, set from the link",
        draw="an extra canvas layer, or the engine's own sprites and meshes",
        picture="canvas readback (toDataURL, readPixels)",
        world_out="the engine's collision queries",
        world_in="the engine's own static bodies"),
    "love2d": _b(
        "LÖVE (Lua)", "2d", 1, 1, "misc-engines.md",
        code="Lua injected with lovely (or a patched .love); LuaSocket ships with LÖVE",
        cam_out="the game's camera transform",
        cam_in="the same transform, set from the link",
        draw="love.graphics in love.draw: an Image updated from the link",
        picture="a Canvas read into ImageData",
        world_out="the game's own collision",
        world_in="the game's own bodies"),
    "java": _b(
        "Java", "any", 1, 1, "misc-engines.md",
        code="the game's loader, or a Java agent with Mixin / ASM",
        notes=["Minecraft is planned separately: name it \"minecraft\"."]),
    "cryengine": _b(
        "CryEngine", "3d", 1, 0, "native.md",
        code="pak overrides, Lua where exposed, native hooks otherwise",
        draw="a ReShade add-on composite against the game's depth"),
    "frostbite": _b(
        "Frostbite", "3d", 0, 0, "big-frameworks.md",
        code="Frosty Tool Suite for supported single-player titles, offline",
        notes=["Most titles ship kernel anti-cheat: stop unless it's a supported offline single-player game."]),
    "defold": _b("Defold", "2d", 1, 0, "misc-engines.md", code="Lua scripts unpacked from game.arcd"),
    "cocos": _b("Cocos2d-x", "2d", 1, 0, "native.md", code="bundled Lua or JavaScript, else native hooks"),
    "haxe": _b("Haxe / OpenFL", "2d", 1, 0, "misc-engines.md", code="asset overrides; hscript loaders (Polymod) "
                                                                     "where present"),
    "native": _b(
        "native engine (no loader)", "3d", 1, 1, "native.md",
        code="a proxy DLL (dinput8, version, winmm) or the ASI loader, with MinHook / SafetyHook",
        cam_out="the view and projection matrices: find them in constant buffers with RenderDoc, then their owner "
                "in memory with Cheat Engine",
        cam_in="those values, written back every frame (hard)",
        draw="a ReShade add-on composite against the game's depth (most D3D9-12, OpenGL and Vulkan games)",
        picture="a ReShade add-on or Present-hook readback",
        world_out="the game's ray cast, reversed (hard), or none",
        world_in="hard",
        notes=["The most work: read the native playbook first."]),
}
BRIDGE["unity-il2cpp"] = dict(
    BRIDGE["unity-mono"], label="Unity (IL2CPP)", host=2, guest=2,
    code="BepInEx 6 (IL2CPP) or MelonLoader, through Il2CppInterop wrappers",
    notes=["Everything goes through the interop wrappers: slower to write, and stripped methods may be missing.",
           "Check the render pipeline (built-in, URP or HDRP) before hooking rendering."])

# Well-known games, so a plan works before (or without) the install. `over` replaces fields of the engine's entry;
# scan=False skips the install scan (Minecraft lives in its launcher, Mario 64 is a ROM).
GAMES = [
    dict(name="Minecraft Java Edition", short="Minecraft", key="minecraft", scan=False,
         aliases=["minecraft", "minecraft java", "minecraft java edition"]),
    dict(name="Grand Theft Auto V", short="GTA V", key="rage",
         aliases=["gta v", "gta 5", "gtav", "gta5", "grand theft auto 5", "grand theft auto v legacy",
                  "grand theft auto v enhanced"],
         note="BattlEye guards GTA Online: story mode only, launched with BattlEye off (-nobattleye); never online"),
    dict(name="Red Dead Redemption 2", short="RDR2", key="rage",
         aliases=["rdr2", "red dead 2", "red dead redemption ii"],
         note="story mode only; never Red Dead Online",
         over=dict(code="a ScriptHookRDR2 script (C++ .asi through the ASI loader), story mode only",
                   cam_out="the CAM natives every frame (one frame ahead of the screen, as in GTA V)",
                   draw="a ReShade add-on composite against the game's depth; invisible props stand in for guest "
                        "objects",
                   notes=[])),
    dict(name="The Elder Scrolls V: Skyrim Special Edition", short="Skyrim", key="creation",
         aliases=["skyrim", "skyrim se", "skyrim ae", "skyrim special edition", "skyrim anniversary edition"],
         over=dict(code="an SKSE plugin in C++ (CommonLibSSE-NG), with Papyrus for game logic")),
    dict(name="Fallout 4", key="creation", aliases=["fallout 4", "fo4"],
         over=dict(code="an F4SE plugin in C++ (CommonLibF4), with Papyrus for game logic", notes=[])),
    dict(name="Fallout: New Vegas", short="New Vegas", key="creation",
         aliases=["fallout new vegas", "new vegas", "fnv"],
         over=dict(code="an xNVSE plugin in C++ (a public bridge-plugin template exists: see mashup-mods)", notes=[])),
    dict(name="Starfield", key="creation", aliases=["starfield"], over=dict(code="an SFSE plugin in C++", notes=[])),
    dict(name="Elden Ring", key="fromsoft", aliases=["elden ring"],
         note="Easy Anti-Cheat: offline only, launched through ModEngine2 or me3; never online"),
    dict(name="Dark Souls III", key="fromsoft", aliases=["dark souls 3", "dark souls iii", "ds3"],
         note="Easy Anti-Cheat: offline only; never online"),
    dict(name="Sekiro: Shadows Die Twice", short="Sekiro", key="fromsoft", aliases=["sekiro"]),
    dict(name="Terraria", key="xna-fna", aliases=["terraria", "tmodloader"],
         over=dict(code="a tModLoader mod (C#): ModSystem draw hooks, Main.screenPosition for the camera")),
    dict(name="Stardew Valley", key="xna-fna", aliases=["stardew", "stardew valley"],
         over=dict(code="a SMAPI mod (C#) with Harmony")),
    dict(name="Celeste", key="xna-fna", aliases=["celeste"], over=dict(code="an Everest code mod (C#, MonoMod hooks)")),
    dict(name="Cyberpunk 2077", key="redengine", aliases=["cyberpunk", "cyberpunk 2077", "cp2077"]),
    dict(name="Half-Life 2", key="source", aliases=["half-life 2", "half life 2", "hl2"]),
    dict(name="Portal 2", key="source", aliases=["portal 2"]),
    dict(name="Garry's Mod", key="gmod", aliases=["garry's mod", "garrys mod", "gmod"],
         note="VAC on official servers: single player or a listen server you run"),
    dict(name="Doom / Doom II", short="Doom", key="doom",
         aliases=["doom", "doom 2", "doom ii", "doom 1993", "ultimate doom", "the ultimate doom", "doom + doom ii",
                  "final doom"]),
    dict(name="Super Mario 64", short="Mario 64", key="sm64", scan=False,
         aliases=["super mario 64", "mario 64", "sm64"],
         note="not a PC game: libsm64 is built from the user's own ROM"),
    dict(name="Valheim", key="unity-mono", aliases=["valheim"]),
    dict(name="Lethal Company", key="unity-mono", aliases=["lethal company"]),
    dict(name="Risk of Rain 2", key="unity-mono", aliases=["risk of rain 2", "ror2"]),
    dict(name="Subnautica", key="unity-mono", aliases=["subnautica"]),
    dict(name="Hollow Knight", key="unity-mono", aliases=["hollow knight"]),
    dict(name="Half Sword", key="unreal", aliases=["half sword"]),
    dict(name="Black Myth: Wukong", key="unreal", aliases=["black myth wukong", "wukong"]),
    dict(name="Halo: The Master Chief Collection", short="Halo MCC", key="native",
         aliases=["halo mcc", "halo master chief collection", "master chief collection", "mcc", "halo 3"],
         note="Easy Anti-Cheat guards matchmaking: mod only in the launcher's official anti-cheat-disabled mode, "
              "offline",
         over=dict(code="the official mod tools for content; a native DLL only in the anti-cheat-disabled mode")),
    dict(name="Age of Empires II: Definitive Edition", short="AoE2", key="genie",
         aliases=["aoe2", "aoe2 de", "age of empires 2", "age of empires ii", "age of empires ii de"]),
    dict(name="Balatro", key="love2d", aliases=["balatro"], over=dict(code="lovely + Steamodded (Lua)")),
]

MILESTONES = {
    "passthrough": [
        ("Lab", "Back up both games' saves, use separate profiles or worlds, run both windowed at the size you'll "
                "record with pause on focus loss off, and use the offline launch options.",
         "backup names and the exact launch steps in MODLOG.md"),
        ("Both mods load and talk", "Each mod writes a line to its game's log, and hello and beat cross the link "
                                    "both ways.",
         "both log lines and a `fsgc passthrough peer` summary with no problems"),
        ("Each side against the stand-in", "The guest follows the peer's camera orbit (`peer --as host`), and the "
                                           "host's camera stream passes the peer's checks (`peer --as guest`).",
         "the peer logs and a screenshot of the guest following the orbit"),
        ("One cube", "One guest object drawn in the host at a fixed world point, at the right size and place, seen "
                     "from two angles.",
         "two `fsgc win shot` screenshots"),
        ("Camera every frame", "The host's camera drives the guest every frame. Measure the pose lag with a scene "
                               "only one side draws (a guest wall against the host's skyline), then fix the lead or "
                               "lag by re-projecting to the pose each frame was rendered with.",
         "frame-by-frame offsets before and after"),
        ("Depth", "Host geometry hides guest content, and guest content hides host geometry.",
         "screenshots at an occluder, from both sides"),
        ("Collision", "The host's ground and walls reach the guest, so the guest's things stand on the host's world.",
         "a guest object resting on host ground"),
        ("Events both ways", "One guest event acted out in the host (an explosion, a hit) and one host event in the "
                             "guest.",
         "a short recorded clip (`fsgc win record`)"),
        ("The idea", "The real features, one at a time, each checked in both real games.", "a clip per feature"),
        ("Ship it", "A 20-45 s showcase (the showcase-video skill), `fsgc publish check --game`, and a field note "
                    "(`fsgc kb new --route passthrough`).",
         "the clip, a clean publish check and the note"),
    ],
    "embed": [
        ("Lab", "Build the library from the user's own ROM on their machine; the ROM and anything made from it never "
                "ship.", "the build log"),
        ("The library alone", "A small harness steps it over a flat floor: the character stands, falls and lands.",
         "logged positions"),
        ("In the host", "The host's mod loads the library, feeds a flat floor and draws the returned mesh at the "
                        "right place.", "a screenshot"),
        ("Real collision", "The host's collision triangles near the character go in every tick: walls stop it, "
                           "slopes slide.", "a clip"),
        ("Input and camera", "The player's input drives the character, and the host's camera follows.", "a clip"),
        ("Ship it", "A showcase clip, `fsgc publish check --game`, and a field note.",
         "the clip, a clean publish check and the note"),
    ],
    "port": [
        ("Lab", "Back up the host's saves and work in a lab profile or world.", "the backup name in MODLOG.md"),
        ("Source of truth", "Read the guest's real numbers and behaviour: decompile it, read its data, or take the "
                            "wiki's exact values.",
         "the numbers in MODLOG.md, each with where it came from"),
        ("Vertical slice", "One guest thing (an enemy, a weapon, a block) working in the host with placeholder art.",
         "a screenshot you looked at, and the host's log"),
        ("Behaviour matches", "Compare it with the original side by side: a trace replay, or the same scene "
                              "recorded in both games.", "the comparison"),
        ("Assets", "New lookalike art with FixedSeed (the fixedseed-assets skill), or a converter that reads the "
                   "user's own install at runtime; never the guest's files in the mod.",
         "fixedseed_manifest.jsonl, or the converter"),
        ("Ship it", "A showcase clip, `fsgc publish check --game`, and a field note.",
         "the clip, a clean publish check and the note"),
    ],
}

RULES = [
    "Only games the user owns, offline, in story mode or on servers they run. Never an online client with "
    "anti-cheat, and never an anti-cheat, DRM or ownership bypass.",
    "Back up saves before the first modded launch. Ask before installing a loader into a game folder or changing "
    "settings or the registry.",
    "Ship your own code and converters only: no game files, decompiled code or extracted assets "
    "(`fsgc publish check --game`).",
    "Don't drive the mouse and keyboard while the user is typing (`fsgc win drive --proc <exe> idle`), and stop "
    "processes by exact PID (`fsgc win kill`).",
]

# --------------------------------------------------------------------------- the two games


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _known(query: str) -> dict | None:
    q = _norm(query)
    return next((g for g in GAMES if q and q in {_norm(g["name"]), *map(_norm, g["aliases"])}), None) if q else None


def _installed(query: str, names: set[str] | None) -> dict | None:
    """`fsgc scan` of the installed game: an exact store name for a known game, else what `fsgc scan` would pick."""
    try:
        games = scan.all_games()
    except OSError:
        games = []
    if names is not None:
        game = next((g for g in games if _norm(g.get("name")) in names), None)
    else:
        game = scan.find_game(query, games)
    return scan.scan_game(game) if game else None


def profile(query: str) -> dict:
    """One game: its fingerprint when installed, what its engine offers a passthrough, and its safety notes."""
    entry = _known(query)
    names = {_norm(entry["name"]), *map(_norm, entry["aliases"])} if entry else None
    scanned = not (entry and not entry.get("scan", True))
    rep = _installed(query, names) if scanned else None
    if not entry and rep:
        entry = _known(rep["name"])
    key = entry["key"] if entry else rep["engine"]["key"] if rep else None
    side = dict(BRIDGE[key], **entry.get("over", {})) if key in BRIDGE and entry else BRIDGE.get(key)
    name = entry["name"] if entry else rep["name"] if rep else query
    playbook = rep["playbook"] if rep else (PLAYBOOKS + side["playbook"]) if side else None
    return dict(
        query=query, name=name, short=(entry or {}).get("short") or name, key=key, side=side, known=bool(entry),
        scanned=scanned, installed=bool(rep),
        aliases=[_norm(a) for a in (entry or {}).get("aliases", [])], path=rep["path"] if rep else None,
        engine=rep["engine"]["label"] if rep else side["label"] if side else None, playbook=playbook,
        anti_cheat=rep["anti_cheat"] if rep else [], loaders=rep["mod_loaders_installed"] if rep else [],
        saves=rep["saves"] if rep else [], warnings=rep["warnings"] if rep else [],
        note=(entry or {}).get("note"), online=scan.online_only(name) or scan.online_only(query))


def _same_game(p: dict, names: set[str]) -> bool:
    mine = {n for n in (_norm(p["name"]), _norm(p["query"]), *p["aliases"]) if n}
    return any(m == n or (min(len(m), len(n)) >= 6 and (m in n or n in m)) for m in mine for n in names)


def _prior_art(ps: list[dict]) -> list[dict] | None:
    """Field notes about either game, or any passthrough, from knowledge/index.json (None: no knowledge base here)."""
    from game_changer import kb
    root = kb.local_root()
    if root is None:
        cache = Path(os.environ.get("FSGC_HOME", Path.home() / ".game-changer")) / "kb" / kb.REPO.replace("/", "__")
        root = cache / "knowledge" if (cache / "knowledge" / "index.json").exists() else None
    try:
        entries = json.loads((root / "index.json").read_text(encoding="utf-8")) if root else None
    except (OSError, json.JSONDecodeError):
        entries = None
    if entries is None:
        return None
    keys = {p["key"] for p in ps if p["key"]}
    out = []
    for e in entries:
        games = {_norm(x) for x in [e.get("game"), *(e.get("games_also") or [])] if x}
        hit = [p for p in ps if _same_game(p, games)]
        tags = {str(t).lower() for t in e.get("tags") or []}
        if len(hit) == 2:
            why, rank = "this exact pair", 0
        elif hit:
            why, rank = hit[0]["name"], 1
        elif e.get("route") == "passthrough" or tags & {"passthrough", "mashup"}:
            why, rank = "a passthrough or mashup between other games", 2
        elif e.get("engine") in keys:
            why, rank = f"same engine ({e.get('engine')})", 3
        else:
            continue
        out.append(dict(path="knowledge/" + e["path"], title=e.get("title"), route=e.get("route"),
                        status=e.get("status"), why=why, rank=rank))
    out.sort(key=lambda x: (x["rank"], x["path"]))
    return out[:8]


# --------------------------------------------------------------------------- the plan


def _roles(pa: dict, pb: dict, host: str | None) -> tuple[dict, dict, str, bool, bool]:
    """-> host, guest, why, chosen by the user, a live passthrough is possible."""
    def score(p, role):
        return p["side"][role] if p["side"] else 1   # an unknown engine: assume hard, recon decides

    def level(p, role):
        return SCORE[score(p, role)] if p["side"] else "unknown until it's scanned"
    if host:
        h = _norm(host)
        hits = [p for p in (pa, pb) if h in (_norm(p["query"]), _norm(p["name"]), *p["aliases"])]
        hits = hits or [p for p in (pa, pb) if h and (h in _norm(p["name"]) or h in _norm(p["query"]))]
        if len(hits) != 1:
            die(f"--host {host!r} should name one of the two games")
        hp = hits[0]
        gp = pb if hp is pa else pa
        why = (f"your choice ({hp['short']} hosting is {level(hp, 'host')}; {gp['short']} alongside is "
               f"{level(gp, 'guest')})")
        return hp, gp, why, True, bool(score(hp, "host") and score(gp, "guest"))
    if "sm64" in (pa["key"], pb["key"]):
        gp = pa if pa["key"] == "sm64" else pb
        hp = pb if gp is pa else pa
        return hp, gp, f"{gp['short']} can only run inside another game's process", False, bool(score(hp, "host"))
    ways = []
    for h, g in ((pb, pa), (pa, pb)):   # the second game named comes first, so a tie reads "A inside B"
        hs, gs = score(h, "host"), score(g, "guest")
        ways.append((hs + gs if hs and gs else 0, h, g, hs, gs))
    best = max(ways, key=lambda w: w[0])
    other = ways[1] if best is ways[0] else ways[0]
    _, hp, gp, hs, gs = best
    if not best[0]:   # no live pairing: content goes into whichever game takes code or data best
        hp, gp = (pb, pa) if score(pb, "host") >= score(pa, "host") else (pa, pb)
        return hp, gp, "the game that can take new content", False, False
    why = f"{hp['short']} hosts ({level(hp, 'host')}) and {gp['short']} runs alongside ({level(gp, 'guest')})"
    if other[0] == best[0]:
        why += "; the other way round is just as good, so the second game named hosts"
    elif other[0]:
        why += f"; the other way round would be {SCORE[other[3]]} / {SCORE[other[4]]}"
    else:
        why += "; the other way round isn't possible"
    return hp, gp, why, False, True


def plan(a: str, b: str, host: str | None = None, idea: str | None = None) -> dict:
    """The whole plan as data: what `fsgc passthrough plan --json` prints and the MCP tool formats."""
    pa, pb = profile(a), profile(b)
    if _norm(pa["name"]) == _norm(pb["name"]) or (pa["path"] and pa["path"] == pb["path"]):
        die("a passthrough needs two different games")
    p = dict(games=[pa, pb], idea=idea, created=dt.date.today().isoformat())
    stop = [f"{x['name']} is an online game" + (f" ({x['online']})" if _norm(x["online"]) != _norm(x["name"]) else "")
            + ": modding its client breaks its terms and gets accounts banned" for x in (pa, pb) if x["online"]]
    if stop:
        p.update(pattern="stop", stop=stop, host=None, guest=None, rules=RULES,
                 read=[f"`{METHOD}` (Pattern 1: port the content)"])
        return p
    hp, gp, why, chosen, live = _roles(pa, pb, host)
    pattern = "embed" if gp["key"] == "sm64" else "passthrough" if live else "port"
    slug = f"{_norm(gp['short'])[:20]}_{_norm(hp['short'])[:20]}"
    p.update(pattern=pattern, host=hp, guest=gp, why=why, chosen=chosen, slug=slug)
    if pattern == "port":
        if gp["side"] and not gp["side"]["guest"]:
            p["port_reason"] = f"{gp['short']} can't run a mod alongside another game ({gp['side']['label']})"
        else:
            p["port_reason"] = f"{hp['short']} has no runtime code hook ({hp['side']['label'] if hp['side'] else '?'})"
    if pattern == "passthrough":
        p["link"] = dict(version=LINK_VERSION, port=25600 + zlib.crc32(slug.encode()) % 400,
                         shm=f"Local\\Passthrough_{slug}")
        dims = (hp["side"] or {}).get("dim"), (gp["side"] or {}).get("dim")
        p["dims"] = ("2D host, 3D guest: draw the guest as a screen in the host's world, or give the guest an "
                     "orthographic side camera locked to the host's grid so the two worlds line up"
                     if dims == ("2d", "3d") else
                     "3D host, 2D guest: the guest's picture becomes a screen or billboard in the host's world, or "
                     "its sprites become billboards at world positions" if dims == ("3d", "2d") else None)
    p["lab"] = _lab(p)
    p["milestones"] = [dict(id=f"M{i}", name=n, goal=goal, proof=proof)
                       for i, (n, goal, proof) in enumerate(MILESTONES[pattern])]
    p["prior_art"] = _prior_art([pa, pb])
    p["ask"] = _ask(p)
    p["rules"] = RULES
    pattern_no = {"passthrough": 2, "embed": 3, "port": 1}[pattern]
    read = [f"`{METHOD}` (Pattern {pattern_no})"]
    books: dict[str, list[str]] = {}
    for x in (hp, gp):
        if x["playbook"]:
            books.setdefault(x["playbook"], []).append(x["short"])
    read += [f"`{path}` ({' and '.join(names)})" for path, names in books.items()]
    if pattern == "passthrough":
        read.append(f"`{EXAMPLE}` (a working passthrough: Minecraft inside GTA V)")
    read.append(f"`{ORACLES}` (how to know each step works)")
    p["read"] = read
    return p


def _lab(p: dict) -> list[str]:
    out = []
    for x in (p["host"], p["guest"]):
        if x["key"] == "minecraft":
            out.append("Give Minecraft its own launcher profile and game folder, so the player's worlds and options "
                       "stay untouched.")
        elif x["key"] == "sm64":
            continue
        elif x["saves"]:
            out.append(f"Back up {x['short']}'s saves: `fsgc backup create \"{x['saves'][0]}\" --name "
                       f"{_norm(x['short'])[:24]}-saves`.")
        else:
            out.append(f"Back up {x['short']}'s saves (`fsgc scan \"{x['query']}\"` finds the folder once it's "
                       "installed; then `fsgc backup create`).")
        out += [f"{x['short']}: {w}." for w in x["warnings"] if not w.startswith("anti-cheat present")]
    if any(x["note"] or x["anti_cheat"] for x in (p["host"], p["guest"])):
        out.append("Launch offline, the way each game's safety line says.")
    if p["pattern"] == "passthrough":
        out.append("Run both windowed at the size you'll record, with pause on focus loss off. The guest keeps "
                   "rendering while unfocused, at the host's resolution.")
    out.append("Ask before installing a loader into a game folder. Install scripts list what they add and remove "
               "exactly that.")
    return out


def _ask(p: dict) -> list[str]:
    h, g = p["host"], p["guest"]
    out = [f"What done means for \"{p['idea']}\" (usually a 20-45 s clip in the real games)." if p["idea"] else
           "The idea in one sentence, and what done means (usually a 20-45 s clip in the real games)."]
    if p["pattern"] == "passthrough" and not p["chosen"]:
        out.append(f"Is {h['short']} the game they want to play in? (`--host \"{g['query']}\"` swaps the roles.)")
    missing = [x["short"] for x in (h, g) if x["scanned"] and not x["installed"]]
    if missing:
        out.append(f"Which PC the games are on: {' and '.join(missing)} {'was' if len(missing) == 1 else 'were'} not "
                   "found here, so that side of the plan comes from the known-games table. Run the plan again "
                   "there.")
    if any(x["note"] or x["anti_cheat"] for x in (h, g)):
        out.append("That they're fine keeping these games offline (see the safety lines).")
    return out


# --------------------------------------------------------------------------- formatting


def _side_lines(x: dict, role: str, p: dict) -> list[str]:
    s = x["side"]
    other = p["guest"] if role == "host" else p["host"]
    out = [f"## The {role}: {x['name']}"]
    if x["installed"]:
        out.append(f"- Installed: `{x['path']}` ({x['engine']}).")
    elif not x["scanned"]:
        out.append("- Planned from the known-games table (no install scan for this one).")
    elif x["known"]:
        out.append("- Not found on this machine; planned from the known-games table.")
    else:
        out.append("- Not found on this machine, and not a game the table knows: run the plan where it's installed, "
                   "or pass its install folder.")
    if s:
        out.append(f"- Engine: {s['label']}." + (f" Playbook: `{x['playbook']}`." if x["playbook"] else ""))
        out.append(f"- Your code: {s['code']}.")
        if p["pattern"] == "port":
            if role == "guest":
                out.append(f"- Read its real numbers and behaviour first, then rebuild them with {other['short']}'s "
                           "modding tools.")
        else:
            fields = ([("Camera out", "cam_out"), ("Drawing the guest", "draw"), ("Collision out", "world_out")]
                      if role == "host" else
                      [("Camera in", "cam_in"), ("Picture out", "picture"), ("Collision in", "world_in")])
            if p["pattern"] == "embed":   # one process: no camera crosses a link
                fields = [f for f in fields if not f[1].startswith("cam_")]
            out += [f"- {label}: {s[k]}." for label, k in fields if s.get(k)]
        out += [f"- {n}" for n in s["notes"]]
    if x["loaders"]:
        out.append(f"- Already installed: {', '.join(x['loaders'])}.")
    if x["anti_cheat"]:
        out.append(f"- **Anti-cheat found:** {', '.join(x['anti_cheat'])}. Offline only, through the game's official "
                   "offline option; never a bypass.")
    if x["note"]:
        out.append(f"- **Safety:** {x['note']}.")
    return out


def markdown(p: dict) -> str:
    """The plan as Markdown: PLAN.md, the CLI's output and the MCP tool's answer."""
    a, b = p["games"]
    if p["pattern"] == "stop":
        online = [x for x in (a, b) if x["online"]]
        other = next((x for x in (a, b) if not x["online"]), None)
        out = [f"# Passthrough plan: {a['short']} x {b['short']}: stop", ""]
        out += [f"- **Stop:** {s}." for s in p["stop"]]
        out += ["", "What still works:"]
        if other:
            out.append(f"- Rebuild what you like about {online[0]['short']} inside {other['short']} as new content, "
                       "with your own art (`fsgc fixedseed`): Pattern 1 in the mashup-mods skill. The online game's "
                       "client and files stay untouched.")
        out.append("- Or pick a single-player game for that side and plan again.")
        out += ["", "## Rules"] + [f"- {r}" for r in p["rules"]]
        return "\n".join(out) + "\n"
    h, g = p["host"], p["guest"]
    H, G = h["short"], g["short"]
    title = {"passthrough": f"{G} inside {H}",
             "embed": f"{G} inside {H} (embedded)",
             "port": f"{G} content in {H}"}[p["pattern"]]
    out = [f"# Passthrough plan: {title}", ""]
    if p["idea"]:
        out += [f"Idea: {p['idea']}", ""]
    if p["pattern"] == "passthrough":
        out.append(f"**Pattern: passthrough.** Both games run at once with a mod in each. {H} is the host, the "
                   f"game you play in: its camera drives {G}, {G}'s picture (or stand-ins for its "
                   f"objects) is drawn into {H}'s frame against its depth, and {H}'s collision goes "
                   f"back so {G}'s things stand on its world. Why this way round: {p['why']}.")
    elif p["pattern"] == "embed":
        out.append(f"**Pattern: embed.** {G} runs as a library inside {H}'s process: your {H} mod feeds it "
                   "collision and input every tick and draws the mesh it returns. There's no second game process and "
                   "no link.")
    else:
        out.append(f"**Pattern: content port.** A live passthrough isn't practical here: {p['port_reason']}. The "
                   f"closest thing is to rebuild what you want from {G} as new {H} content, with art "
                   "made fresh or converted from the user's own files at install time.")
    out.append("")
    out += _side_lines(h, "host", p) + [""] + _side_lines(g, "guest", p) + [""]
    if p.get("dims"):
        head, text = p["dims"].split(": ", 1)
        out += [f"**{head}:** {text}.", ""]
    if p.get("link"):
        k = p["link"]
        out += [
            f"## The link (passthrough link v{k['version']})",
            f"- **Control:** TCP on 127.0.0.1:{k['port']}, one JSON object per line. {G}'s mod listens; "
            f"{H}'s connects and retries every second, so either game can start first.",
            "- **Every message** has `t` (type), `seq` (per sender, from 1) and `ts` (the sender's monotonic clock, "
            "in ms).",
            f"- **{H} to {G}:** `hello`; `beat` every second; `cam` every frame (`pos`, `rot` as "
            "[pitch, yaw, roll] in degrees, `fov`, `aspect`, `near`, `far`, `frame`); `ground` a few times a second "
            "(`origin`, `cell`, `size`, `heights`, or `boxes`); `input` (forwarded buttons).",
            f"- **{G} to {H}:** `hello`; `beat`; `event` (`kind`, `pos` ...); `entities` (a `list` of "
            "`id`, `kind`, `pos`, `yaw`).",
            "- **Positions** on the link are in the host's coordinates, and the guest converts both ways. Write the "
            "mapping (units, up axis, handedness, angle conventions) in MODLOG.md at the cube milestone.",
            f"- **Pictures** (when the guest's picture is drawn rather than rebuilt from `entities`): named shared "
            f"memory `{k['shm']}`, three slots. A header holds a magic, version, width, height, format and the "
            "newest slot; each slot holds colour, depth and the camera pose and host frame it was rendered for, so "
            "the host can re-project to its current pose. The hand and HUD go in a separate layer.",
            "- **Watchdog:** after 3 s without a message, the host hides the guest's layer and keeps playing.",
            f"- **Stand-in:** `fsgc passthrough peer --as host --port {k['port']} --log peer-host.jsonl` plays "
            f"{H} for {G}'s mod, and `--as guest` plays {G} for {H}'s. Both check "
            "every message against this contract.",
            ""]
    out.append("## Before the first launch")
    out += [f"- {x}" for x in p["lab"]] + [""]
    out.append("## Milestones (put each one's proof in MODLOG.md before the next)")
    out += [f"{i + 1}. **{m['id']} {m['name']}.** {m['goal']} Proof: {m['proof']}." for i, m in
            enumerate(p["milestones"])] + [""]
    out.append("## Prior art")
    if p["prior_art"] is None:
        out.append("- No knowledge base here: `fsgc kb sync`, then plan again (or read "
                   f"{REPO_URL}knowledge/INDEX.md).")
    elif not p["prior_art"]:
        out.append("- None yet. Yours will be the first note: `fsgc kb new --route passthrough`.")
    for n in p["prior_art"] or []:
        detail = "; ".join(str(v) for v in (n["why"], n["route"], n["status"]) if v)
        out.append(f"- `{n['path']}`: {n['title']} ({detail})")
    out += ["", "## Ask the user first"] + [f"- {q}" for q in p["ask"]]
    out += ["", "## Rules"] + [f"- {r}" for r in p["rules"]]
    out += ["", "## Read next"] + [f"- {r}" for r in p["read"]]
    if not (ROOT / METHOD).exists():
        out.append(f"- These paths are in the game-changer repo: {REPO_URL}")
    return "\n".join(out) + "\n"


def modlog(p: dict) -> str:
    """The journal's first page: the decisions so far and the milestones to tick off."""
    h, g = p["host"], p["guest"]
    H, G = h["short"], g["short"]
    a, b = p["games"]
    out = [f"# MODLOG: {G} inside {H} ({p['pattern']})", "",
           f"Started {p['created']} from `fsgc passthrough plan \"{a['query']}\" \"{b['query']}\"`; the plan is in "
           "PLAN.md. Write down every confirmed fact, every dead end and why, and the next step: this journal is what "
           "survives a context reset.", "", "## Decisions",
           f"- Host: {H}. Guest: {G}. Why: {p['why']}.", f"- Pattern: {p['pattern']}."]
    if p.get("link"):
        out.append(f"- Link: TCP 127.0.0.1:{p['link']['port']} (passthrough link v{p['link']['version']}); pictures in "
                   f"`{p['link']['shm']}`.")
        out.append("- Coordinates: (units, up axis, handedness, angle conventions; fill in at the cube milestone)")
    out += [f"- Idea: {p['idea'] or '(one sentence, agreed with the user)'}",
            "- Done means: (agreed with the user; usually a 20-45 s clip in the real games)", "", "## Milestones"]
    out += [f"- [ ] {m['id']} {m['name']}. Proof: {m['proof']}." for m in p["milestones"]]
    out += ["", "## Facts", "", "## Dead ends", "", "## Next", f"- {p['milestones'][0]['id']}: "
            f"{p['milestones'][0]['goal']}", ""]
    return "\n".join(out)


def write(p: dict, out_dir: str) -> tuple[list[str], list[str]]:
    """PLAN.md and MODLOG.md into out_dir. An existing MODLOG.md is kept; an existing PLAN.md gets a PLAN-2.md."""
    if p["pattern"] == "stop":
        die("nothing to start: the plan says stop")
    out = Path(to_posix(out_dir)).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    out = out.resolve()
    wrote, kept = [], []
    plan_path = out / "PLAN.md"
    n = 1
    while plan_path.exists():
        n += 1
        plan_path = out / f"PLAN-{n}.md"
    plan_path.write_text(markdown(p), encoding="utf-8", newline="\n")
    wrote.append(str(plan_path))
    log = out / "MODLOG.md"
    if log.exists():
        kept.append(str(log))
    else:
        log.write_text(modlog(p), encoding="utf-8", newline="\n")
        wrote.append(str(log))
    return wrote, kept


def method_text() -> str | None:
    """The mashup-mods skill, when this package runs from the repo (clone or plugin install)."""
    try:
        return (ROOT / METHOD).read_text(encoding="utf-8")
    except OSError:
        return None


PROMPT = """Build a passthrough between {a} and {b}{idea}: both games running at once with a mod in each, one drawn \
inside the other, with camera, collision and events crossing a local link.

1. The plan below comes from the `passthrough` tool: host and guest, what each engine gives you, the link contract, \
milestones with the proof each one needs, and prior field notes. Run the tool again once a game is installed, or to \
swap the host.
2. Before building, agree three things with me: which game I play in (the host), the idea in one sentence, and what \
done means.
3. Work through the milestones in order. Keep MODLOG.md in the working folder and put each milestone's proof in it \
before moving on. While one side isn't ready, `fsgc passthrough peer` stands in for it.
4. Ask me before installing a loader into a game folder or changing game settings, and back up saves first.
5. Offline, story mode or servers I run only. Never bypass anti-cheat or DRM, and never ship game files.
"""


def prompt_text(a: str, b: str, idea: str | None = None) -> str:
    """The `passthrough` MCP prompt: the instructions, the plan, and the method."""
    try:
        body = markdown(plan(a, b, idea=idea))
    except SystemExit:
        body = "(The plan couldn't be made here; call the `passthrough` tool to see why.)\n"
    method = method_text()
    text = PROMPT.format(a=a, b=b, idea=f" ({idea})" if idea else "") + "\n" + body
    if method:
        text += f"\n---\n\nThe method ({METHOD}):\n\n{method}"
    else:
        text += f"\nThe method: {REPO_URL}{METHOD}\n"
    return text


# --------------------------------------------------------------------------- the stand-in peer

TYPES = {
    "hello": {"v": "int", "role": "str", "game": "str"},
    "beat": {},
    "cam": {"pos": "vec3", "rot": "vec3", "fov": "num"},
    "ground": {"origin": "vec3"},
    "input": {},
    "event": {"kind": "str"},
    "entities": {"list": "list"},
    "cmd": {"op": "str"},
    "ack": {"ack": "int"},
}


def _is(v, kind: str) -> bool:
    if kind == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if kind == "num":
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    if kind == "str":
        return isinstance(v, str) and v != ""
    if kind == "list":
        return isinstance(v, list)
    return isinstance(v, list) and len(v) == 3 and all(_is(x, "num") for x in v)   # vec3


def check_message(m) -> list[str]:
    """What's wrong with one link message ([] = fine). Extra fields and extra message types are allowed."""
    if not isinstance(m, dict):
        return ["not a JSON object"]
    t = m.get("t")
    if not _is(t, "str"):
        return ["no `t` (message type)"]
    probs = [] if _is(m.get("seq"), "int") else ["`seq` missing or not an integer"]
    if not _is(m.get("ts"), "num"):
        probs.append("`ts` missing or not a number")
    probs += [f"`{k}` should be {kind}" for k, kind in TYPES.get(t, {}).items() if not _is(m.get(k), kind)]
    if t == "ground" and not ({"heights", "cell", "size"} <= m.keys() or "boxes" in m):
        probs.append("`ground` needs `heights` + `cell` + `size`, or `boxes`")
    if t == "hello" and _is(m.get("v"), "int") and m["v"] != LINK_VERSION:
        probs.append(f"link version {m['v']}; this peer speaks {LINK_VERSION}")
    return probs


def _orbit(t: float, origin, up: str) -> dict:
    ox, oy, oz = origin
    ang = 2 * math.pi * ((t / 8.0) % 1.0)
    c, s = 8.0 * math.cos(ang), 8.0 * math.sin(ang)
    pos = [ox + c, oy + s, oz + 2.0] if up == "z" else [ox + c, oy + 2.0, oz + s]
    return dict(pos=[round(v, 4) for v in pos], rot=[-10.0, round((math.degrees(ang) + 180.0) % 360.0, 3), 0.0],
                fov=60.0, aspect=round(16 / 9, 6), near=0.1, far=1000.0)


def _flat_ground(origin, up: str, n: int = 16) -> dict:
    ox, oy, oz = origin
    corner = [ox - n / 2, oy - n / 2, oz] if up == "z" else [ox - n / 2, oy, oz - n / 2]
    return dict(origin=corner, cell=1.0, size=[n, n], heights=[0.0] * (n * n))


def _receive(line: bytes, st: dict, log, t0: float):
    try:
        m = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        st["bad"] += 1
        _problem(st, f"not JSON: {line[:80]!r}")
        return
    if log:
        log.write(json.dumps(dict(at=round(time.monotonic() - t0, 3), dir="in", msg=m)) + "\n")
    probs = check_message(m)
    t = m.get("t") if isinstance(m, dict) and isinstance(m.get("t"), str) else "?"
    st["got"][t] = st["got"].get(t, 0) + 1
    if isinstance(m, dict):
        seq = m.get("seq")
        if _is(seq, "int"):
            if st["last_seq"] is not None and seq != st["last_seq"] + 1:
                st["gaps"] += 1
                _problem(st, f"seq went from {st['last_seq']} to {seq}")
            st["last_seq"] = seq
        if t not in TYPES:
            st["extra"] += 1
        if t == "hello":
            st["hello"] = m
            print(f"<- hello {json.dumps(m)}")
        elif t == "cam":
            st["last_cam"] = m
        elif t not in ("beat", "ground") and st["shown"].get(t, 0) < 3:
            st["shown"][t] = st["shown"].get(t, 0) + 1
            print(f"<- {json.dumps(m)[:200]}")
    if probs:
        st["invalid"] += 1
        _problem(st, f"{t} #{m.get('seq') if isinstance(m, dict) else '?'}: {'; '.join(probs)}")


def _problem(st: dict, text: str):
    st["problems"].append(text)
    if len(st["problems"]) <= 20:
        print(f"!! {text}")


def _session(sock: socket.socket, args, st: dict, deadline: float, log, t0: float):
    """One connection: say hello, keep our side's stream going, read and check theirs until the deadline."""
    sock.settimeout(2.0)
    seq, frame, buf, started = 0, 0, b"", time.monotonic()
    st["last_seq"] = None   # a new connection restarts the other side's numbering

    def send(t, **fields):
        nonlocal seq
        seq += 1
        m = dict(t=t, seq=seq, ts=round(time.monotonic() * 1000, 3), **fields)
        sock.sendall((json.dumps(m, separators=(",", ":")) + "\n").encode())
        st["sent"][t] = st["sent"].get(t, 0) + 1
        if log:
            log.write(json.dumps(dict(at=round(time.monotonic() - t0, 3), dir="out", msg=m)) + "\n")

    now = time.monotonic()
    due = dict(beat=now, cam=now, ground=now) if args.role == "host" else dict(beat=now, event=now + 3.0)
    try:
        send("hello", v=LINK_VERSION, role=args.role, game=f"fsgc passthrough peer ({args.role})", mod=__version__)
        while True:
            now = time.monotonic()
            if now >= deadline:
                return
            if now >= due["beat"]:
                send("beat")
                due["beat"] = max(due["beat"] + 1.0, now)
            if args.role == "host":
                if now >= due["cam"]:
                    frame += 1
                    send("cam", frame=frame, **_orbit(now - t0, args.origin, args.up))
                    due["cam"] = max(due["cam"] + 1 / 60, now)
                if now >= due["ground"]:
                    send("ground", **_flat_ground(args.origin, args.up))
                    due["ground"] = max(due["ground"] + 0.2, now)
            elif now >= due["event"]:
                if st["last_cam"] and _is(st["last_cam"].get("pos"), "vec3"):
                    send("event", kind="ping", pos=st["last_cam"]["pos"])
                due["event"] = now + 3.0
            wait = max(0.0, min(min(due.values()), deadline) - time.monotonic())
            ready, _, _ = select.select([sock], [], [], wait)
            if ready:
                chunk = sock.recv(65536)
                if not chunk:
                    print("the other side closed the link")
                    return
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for line in lines:
                    if line.strip():
                        _receive(line, st, log, t0)
    except OSError as e:
        print(f"the link dropped: {e}")
    finally:
        sock.close()
        st["linked"] += time.monotonic() - started


def _summary(st: dict, args, secs: float) -> bool:
    linked = max(st["linked"], 1e-6)

    def rates(d):
        return ", ".join(f"{k} {n} ({n / linked:.1f}/s)" for k, n in sorted(d.items())) or "nothing"
    print(f"\npeer as {args.role} on 127.0.0.1:{args.port}: {secs:.1f} s, {st['connects']} connection(s), linked for "
          f"{st['linked']:.1f} s")
    print("  their hello: " + (json.dumps(st["hello"]) if st["hello"] else "none (the other side never said hello)"))
    print("  got:  " + rates(st["got"]))
    print("  sent: " + rates(st["sent"]))
    print(f"  problems: {st['invalid']} invalid, {st['bad']} not JSON, {st['gaps']} seq gaps "
          f"({st['extra']} messages of extra types, which is fine)")
    if args.log:
        print(f"  log: {args.log}")
    return bool(st["hello"]) and not (st["invalid"] or st["bad"] or st["gaps"])


def peer(args):
    """Stand in for one side of the link: exit 0 only if the other side said hello and every message checked out."""
    t0 = time.monotonic()
    deadline = t0 + args.seconds
    st = dict(got={}, sent={}, shown={}, bad=0, invalid=0, gaps=0, extra=0, hello=None, last_seq=None, last_cam=None,
              problems=[], connects=0, linked=0.0)
    log = open(Path(to_posix(args.log)).expanduser(), "a", encoding="utf-8") if args.log else None
    try:
        if args.role == "host":
            print(f"playing the host: connecting to the guest's mod on 127.0.0.1:{args.port}")
            while time.monotonic() < deadline:
                try:
                    sock = socket.create_connection(("127.0.0.1", args.port), timeout=1.0)
                except OSError:
                    time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
                    continue
                st["connects"] += 1
                print("connected")
                _session(sock, args, st, deadline, log, t0)
        else:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if os.name != "nt":   # on Windows SO_REUSEADDR would let two listeners share the port
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                srv.bind(("127.0.0.1", args.port))
            except OSError:
                die(f"127.0.0.1:{args.port} is taken: if that's the guest's own mod, test it with --as host instead")
            srv.listen(1)
            srv.settimeout(0.5)
            print(f"playing the guest: listening on 127.0.0.1:{args.port} for the host's mod")
            try:
                while time.monotonic() < deadline:
                    try:
                        sock, _ = srv.accept()
                    except socket.timeout:
                        continue
                    st["connects"] += 1
                    print("the host connected")
                    _session(sock, args, st, deadline, log, t0)
            finally:
                srv.close()
    except KeyboardInterrupt:
        pass
    finally:
        if log:
            log.close()
    ok = _summary(st, args, time.monotonic() - t0)
    sys.exit(0 if ok else 1)


# --------------------------------------------------------------------------- CLI


def _vec3(s: str) -> tuple[float, float, float]:
    try:
        x, y, z = (float(v) for v in s.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("expected x,y,z") from None
    return x, y, z


def main_plan(args):
    p = plan(args.game_a, args.game_b, host=args.host, idea=args.idea)
    wrote, kept = write(p, args.out) if args.out else ([], [])
    if args.json:
        emit(dict(p, files=dict(wrote=wrote, kept=kept)) if args.out else p, as_json=True)
        return
    print(markdown(p), end="")
    for f in wrote:
        print(f"wrote {f}")
    for f in kept:
        print(f"kept {f} (it already exists)")


def register(sub):
    p = sub.add_parser("passthrough", help="two games at once: plan host and guest, hooks, link and milestones; a "
                                           "stand-in for the link",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("plan", help="fingerprint two games and plan the passthrough between them")
    q.add_argument("game_a", help="a game: name or install folder")
    q.add_argument("game_b", help="the other game")
    q.add_argument("--host", help="the game you play in (default: whichever hosts better; a tie goes to the second)")
    q.add_argument("--idea", help="what should cross over, in one sentence")
    q.add_argument("--out", metavar="DIR", help="write PLAN.md and MODLOG.md here (never replaces a file)")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main_plan)
    q = cs.add_parser("peer", help="stand in for one side of the link and check every message the other side sends")
    q.add_argument("--as", dest="role", choices=["host", "guest"], required=True, help="which game to stand in for")
    q.add_argument("--port", type=int, default=25600, help="the plan's link port")
    q.add_argument("--seconds", type=float, default=30.0, help="how long to run (default 30)")
    q.add_argument("--origin", type=_vec3, default=(0.0, 0.0, 0.0), metavar="X,Y,Z",
                   help="host coordinates the stand-in camera orbits, as host")
    q.add_argument("--up", choices=["y", "z"], default="y", help="the host's up axis, for the stand-in camera and "
                                                                "ground")
    q.add_argument("--log", help="append every message, both ways, to this JSONL file")
    q.set_defaults(func=peer)
