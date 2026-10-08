"""Blender renders -> AoE2 DE .sld sprites, for the units in civ.py.

    python make_sprites.py render robotaxi      # 16 angles x every animation (+ shadow pass), with `fsgc render3d`
    python make_sprites.py pack robotaxi        # PNGs -> build/graphics/<sprite>_<anim>_x1.sld + a preview sheet
    python make_sprites.py all robotaxi drone   # both steps, both units
    python make_sprites.py pack drone --frames /elsewhere/drone     # frames rendered somewhere else

Rendering is the repo's `fsgc render3d --preset aoe2`: orthographic, looking down at 30 degrees, 16
headings clockwise from east (the stock knight's frame order), the unit's ground point at the canvas
centre (the hotspot), plus a pass of just the shadow it casts onto a shadow-catcher ground (the SLD
shadow layer). Its --anims flag names motions with fixed parameters (bob, walk, lunge, die, wreck).
The shipped units tuned some of them (the Robotaxi idles with a 0.3 px bob, the drone hovers 34 px
up), which that flag can't carry, so a unit with tuned motions goes through game_changer.render3d.render() in
Python instead: the same Blender script and camera, with the full motion per animation. --cli forces
the plain command line (tuned values dropped). The equivalent command is printed either way.

Player colour: the concept art asks for saturated blue trim; those pixels become the SLD player
mask and are desaturated to grey shading (how the stock sprites store player-coloured areas; the
same hue mask as `fsgc sprite team-mask --hue blue`). Death/decay frames are darkened to read as a
burnt-out wreck.
"""
import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import civ as C
import sld
from aoe2paths import DEFAULT_BUILD, HERE

REPO = HERE.parents[1]   # game-changer/: bin/fsgc and the fsgc package
NOT_MOTION = {"frames", "duration", "motion", "burn"}   # anim keys that aren't motion parameters


def unit(name):
    for u in C.UNITS:
        if name in (u["key"], u["id"], u["sprite"]):
            return u
    sys.exit(f"unknown unit {name!r} (civ.py has {', '.join(u['key'] for u in C.UNITS)})")


def render(u, frames_dir, cli=False):
    sys.path.insert(0, str(REPO))
    try:
        from game_changer.render3d import MOTIONS, render as render3d
    except ImportError:
        sys.exit(f"rendering needs the game-changer repo (game_changer/ in {REPO})")
    r = u["render"]
    glb = HERE / r["glb"]
    for anim, a in u["anims"].items():
        if a["motion"] not in MOTIONS:
            sys.exit(f"{u['key']} {anim}: unknown motion {a['motion']!r} (fsgc render3d has {', '.join(MOTIONS)})")
    args = [str(glb), str(frames_dir), "--preset", "aoe2", "--length", f"{r['length']:g}", "--forward-yaw", f"{r.get('forward_yaw', 0):g}",
            "--anims", ",".join(f"{anim}:{a['frames']}:{a['motion']}" for anim, a in u["anims"].items()),
            "--shadows", "--samples", str(r.get("samples", 40))]
    if r.get("canvas", 200) != 200:
        args += ["--canvas", str(r["canvas"])]
    if r.get("sun", 4.0) != 4.0:
        args += ["--sun", f"{r['sun']:g}"]
    tuned = {anim: {k: v for k, v in a.items() if k not in NOT_MOTION} for anim, a in u["anims"].items()}
    tuned = {anim: t for anim, t in tuned.items() if t}
    print("fsgc render3d " + shlex.join(args), flush=True)
    if cli or not tuned:
        if tuned:
            print("  --cli: without the tuned motion parameters", tuned, flush=True)
        subprocess.run([shutil.which("fsgc") or str(REPO / "bin/fsgc"), "render3d", *args], check=True)
        return
    print("  + tuned motion parameters that --anims can't carry, so through game_changer.render3d.render():", tuned, flush=True)
    anims = {anim: dict(frames=a["frames"], motion=dict(MOTIONS[a["motion"]] or {}, **tuned.get(anim, {}))) for anim, a in u["anims"].items()}
    render3d(str(glb), str(frames_dir), "aoe2", canvas=str(r.get("canvas", 200)), length=r["length"], forward_yaw=r.get("forward_yaw", 0),
             anims=anims, shadows=True, samples=r.get("samples", 40), sun=r.get("sun", 4.0))


def player_mask(rgb, alpha, sat_lo=0.25, val_lo=0.15):
    """Saturated blue/cyan pixels -> mask 0-255."""
    r, g, b = (rgb[..., i].astype(np.float32) / 255 for i in range(3))
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    sat = (mx - mn) / (mx + 1e-6)
    hue_blue = (b >= r * 1.25) & (b >= g * 0.9)
    m = np.clip((sat - sat_lo) / 0.35, 0, 1) * hue_blue * (alpha > 0) * (mx > val_lo)
    return (m * 255).astype(np.uint8)


def frame_arrays(png, shadow_png, burn=0.0, brighten=1.0):
    im = np.array(Image.open(png).convert("RGBA"))
    rgb, a = im[..., :3].astype(np.float32), im[..., 3]
    if brighten != 1.0:  # dark generated textures: lift shadows more than highlights
        rgb = 255 * (rgb / 255) ** (1 / brighten)
    # punch-through alpha (BC1): hard edge at 50%
    a = np.where(a >= 128, 255, 0).astype(np.uint8)
    m = player_mask(im[..., :3], a)
    lum = (0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2])[..., None]
    k = (m / 255.0)[..., None]
    rgb = rgb * (1 - k) + np.clip(lum * 1.15, 0, 255) * k
    if burn:
        rgb = rgb * (1 - 0.65 * burn) + np.array([25, 20, 18]) * 0.65 * burn
        m = (m * (1 - burn)).astype(np.uint8)
    rgba = np.concatenate([np.clip(rgb, 0, 255).astype(np.uint8), a[..., None]], -1)
    shadow = None
    if shadow_png and Path(shadow_png).exists():
        s = np.array(Image.open(shadow_png).convert("RGBA"))[..., 3].astype(np.float32)
        shadow = np.clip(s * 0.55, 0, 140).astype(np.uint8)
        shadow[a > 0] = 0
    return rgba, m, shadow


def pack(u, src, out):
    first = next(iter(u["anims"]))
    if not (src / f"{first}_00_000.png").exists():
        sys.exit(f"no frames in {src}: run `python make_sprites.py render {u['key']}` first (or pass --frames)")
    c = u["render"].get("canvas", 200)
    graphics, previews = out / "graphics", out / "previews"
    graphics.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)
    sheet_rows = []
    for anim, spec in u["anims"].items():
        frames = []
        n = spec["frames"]
        for k in range(16):
            for f in range(n):
                burn = (f / max(n - 1, 1)) if spec.get("burn") and anim.startswith("death") else (1.0 if spec.get("burn") else 0.0)
                rgba, m, shadow = frame_arrays(src / f"{anim}_{k:02d}_{f:03d}.png", src / f"{anim}_{k:02d}_{f:03d}_s.png", burn,
                                               u["render"].get("brighten", 1.0))
                frames.append(dict(rgba=rgba, hotspot=(c // 2, c // 2), player=m, shadow=shadow))
        frames.append(frames[0])  # the stock files carry one extra trailing frame
        path = graphics / f"{u['sprite']}_{anim}_x1.sld"
        sld.write(path, frames)
        print("wrote", path, len(frames), "frames")
        # preview: angle 0..15 (first frame), player colour shown red
        row = Image.new("RGBA", (16 * 100, 100), (80, 120, 60, 255))
        for k in range(16):
            fr = frames[k * n]
            rgb = fr["rgba"].copy()
            mk = (fr["player"] / 255.0)[..., None]
            rgb[..., :3] = (rgb[..., :3] * (1 - mk) + np.array([220, 40, 40]) * mk * (rgb[..., :3].mean(-1, keepdims=True) / 128)).clip(0, 255).astype(np.uint8)
            tile = Image.fromarray(rgb)
            if fr["shadow"] is not None:
                sh = Image.fromarray(np.dstack([np.zeros_like(fr["shadow"])] * 3 + [fr["shadow"]]))
                base = Image.new("RGBA", tile.size, (0, 0, 0, 0)); base.alpha_composite(sh); base.alpha_composite(tile); tile = base
            row.alpha_composite(tile.crop((c // 2 - 50, c // 2 - 50, c // 2 + 50, c // 2 + 50)), (k * 100, 0))
        sheet_rows.append(row)
    sheet = Image.new("RGBA", (1600, 100 * len(sheet_rows)))
    for i, r in enumerate(sheet_rows):
        sheet.paste(r, (0, 100 * i))
    sheet.save(previews / f"{u['key']}_sheet.png")
    print("sheet", previews / f"{u['key']}_sheet.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["render", "pack", "all"])
    ap.add_argument("units", nargs="+", help="unit keys from civ.py: " + ", ".join(u["key"] for u in C.UNITS))
    ap.add_argument("--out", default=str(DEFAULT_BUILD),
                    help="build folder: frames in <out>/frames/<unit>, sprites to <out>/graphics, sheets to <out>/previews")
    ap.add_argument("--frames", help="the frame folder instead of <out>/frames/<unit> (one unit only)")
    ap.add_argument("--cli", action="store_true", help="render with the plain `fsgc render3d` command line even if the unit has tuned motions")
    a = ap.parse_args()
    if a.frames and len(a.units) > 1:
        ap.error("--frames takes one unit")
    out = Path(a.out)
    for name in a.units:
        u = unit(name)
        frames = Path(a.frames) if a.frames else out / "frames" / u["key"]
        if a.step in ("render", "all"):
            render(u, frames, a.cli)
        if a.step in ("pack", "all"):
            pack(u, frames, out)
