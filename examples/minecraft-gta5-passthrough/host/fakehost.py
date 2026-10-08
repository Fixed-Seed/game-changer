"""A stand-in for GTA: drives Minecraft's camera along an orbit, gives it a flat ground (y = 64), and composites
Minecraft's exported frames over a synthetic "host" scene rendered for the same pose (checkerboard ground and a red
pillar), to check alignment and depth occlusion before the real host exists.

Run with Windows Python (the shared memory is a Windows named mapping), with numpy, Pillow and websockets:
    python fakehost.py [seconds] [outdir] [fp|tp]
outdir defaults to <PASSTHROUGH_WIN_DIR>\\fakehost_out (C:\\dev\\passthrough\\fakehost_out); tp = third person.
"""
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
import websockets

sys.path.insert(0, str(Path(__file__).parent))
from mcframe import MCFrames  # noqa: E402

URL = "ws://127.0.0.1:25599"
OUT = str(Path(os.environ.get("PASSTHROUGH_WIN_DIR", r"C:\dev\passthrough")) / "fakehost_out")
GROUND_Y = 64.0                   # host ground height; barriers fill y = 63 so their tops sit at 64
CENTER = (0.5, GROUND_Y, 6.5)     # what the camera orbits
HOST_PILLAR = ((-3.0, 64.0, 5.0), (-2.0, 67.0, 6.0))  # a red box that only exists in the "host" scene
MC_SETUP = [                      # Minecraft blocks placed around the centre
    "fill -30 64 -30 30 80 30 minecraft:air",
    "fill 0 64 6 0 66 6 minecraft:diamond_block",
    "setblock 2 64 6 minecraft:tnt",
    "setblock 2 64 8 minecraft:glass",
    "fill -1 64 9 1 64 9 minecraft:oak_planks",
    "setblock -2 64 3 minecraft:grass_block",
]


def basis(yaw, pitch):
    """Minecraft's camera axes (yaw 0 faces +Z, positive pitch looks down)."""
    y, p = math.radians(yaw), math.radians(pitch)
    fwd = np.array([-math.sin(y) * math.cos(p), -math.sin(p), math.cos(y) * math.cos(p)])
    right = np.array([-math.cos(y), 0.0, -math.sin(y)])
    up = np.cross(right, fwd)
    return fwd, right, up


def look_at(eye, target):
    d = np.subtract(target, eye)
    yaw = math.degrees(math.atan2(-d[0], d[2]))
    pitch = math.degrees(-math.atan2(d[1], math.hypot(d[0], d[2])))
    return yaw, pitch


def host_render(w, h, eye, yaw, pitch, fov, boxes=None):
    """The synthetic host frame: colour (h, w, 3) float and view-space depth (h, w)."""
    boxes = boxes if boxes is not None else [(HOST_PILLAR, (0.8, 0.15, 0.1))]
    fwd, right, up = basis(yaw, pitch)
    t = math.tan(math.radians(fov) / 2)
    xs = ((np.arange(w) + 0.5) / w * 2 - 1) * t * w / h
    ys = (1 - (np.arange(h) + 0.5) / h * 2) * t
    rays = fwd[None, None, :] + xs[None, :, None] * right[None, None, :] + ys[:, None, None] * up[None, None, :]
    eye = np.asarray(eye, float)
    depth = np.full((h, w), np.inf)
    color = np.zeros((h, w, 3))
    # sky gradient
    color[:] = (np.clip(ys, -1, 1)[:, None, None] * 0.25 + np.array([0.55, 0.7, 0.9]))
    # ground plane y = GROUND_Y (ray param = view depth, since rays have unit forward component)
    with np.errstate(divide="ignore", invalid="ignore"):
        tg = (GROUND_Y - eye[1]) / rays[..., 1]
    hit = (tg > 0) & np.isfinite(tg)
    p = eye + rays * tg[..., None]
    checker = ((np.floor(p[..., 0]) + np.floor(p[..., 2])) % 2 == 0)
    ground = np.where(checker[..., None], [0.35, 0.35, 0.38], [0.55, 0.55, 0.58])
    # thin grid lines on block edges make misalignment easy to see
    fx, fz = p[..., 0] - np.floor(p[..., 0]), p[..., 2] - np.floor(p[..., 2])
    line = (np.minimum(fx, 1 - fx) < 0.02) | (np.minimum(fz, 1 - fz) < 0.02)
    ground = np.where(line[..., None], [0.1, 0.1, 0.1], ground)
    color = np.where(hit[..., None], ground, color)
    depth = np.where(hit, tg, depth)
    for (lo, hi), rgb in boxes:  # boxes (slab test)
        lo, hi = np.array(lo, float), np.array(hi, float)
        with np.errstate(divide="ignore", invalid="ignore"):
            t1 = (lo - eye) / rays
            t2 = (hi - eye) / rays
        tmin = np.nanmax(np.minimum(t1, t2), axis=-1)
        tmax = np.nanmin(np.maximum(t1, t2), axis=-1)
        box = (tmax >= tmin) & (tmin > 0) & (tmin < depth)
        shade = 0.6 + 0.4 * ((np.abs(eye + rays * tmin[..., None] - lo) < 1e-3).any(-1))
        color = np.where(box[..., None], np.array(rgb) * shade[..., None], color)
        depth = np.where(box, tmin, depth)
    return color, depth


def composite(host_rgb, host_depth, frame, bias=0.02):
    """MC world over the host where it is nearer (premultiplied alpha), then the MC overlay on top."""
    world = frame.world_rgba.astype(np.float64) / 255.0
    over = frame.overlay_rgba.astype(np.float64) / 255.0
    mc_depth = frame.world_depth_m
    front = (mc_depth < host_depth + bias)[..., None]
    a = world[..., 3:4] * front
    out = world[..., :3] * front + host_rgb * (1 - a)
    out = over[..., :3] + out * (1 - over[..., 3:4])
    return np.clip(out, 0, 1)


def third_person(now):
    """Player walking a circle of radius 5 around the centre at 1.4 m/s; camera 4 m behind, 1.8 m up."""
    w = 1.4 / 5.0
    a = now * w
    feet = np.array([CENTER[0] + 5 * math.sin(a), GROUND_Y, CENTER[2] + 5 * math.cos(a)])
    vel = np.array([math.cos(a), 0.0, -math.sin(a)])      # d(feet)/da, direction of travel
    body_yaw = math.degrees(math.atan2(-vel[0], vel[2]))
    eye = feet - 4.0 * vel + np.array([0.0, 1.8 + 1.6, 0.0])
    yaw, pitch = look_at(eye, feet + np.array([0.0, 1.4, 0.0]))
    return tuple(eye), yaw, pitch, tuple(feet), body_yaw


async def run(seconds=12.0, outdir=OUT, mode="fp"):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    async with websockets.connect(URL, max_size=None) as ws:
        hello = json.loads(await ws.recv())
        print("hello:", hello)
        cols = [v for x in range(-40, 41) for z in range(-40, 41) for v in (x, z, int(GROUND_Y) - 1, int(GROUND_Y) - 1)]
        await ws.send(json.dumps({"t": "clear"}))
        await ws.send(json.dumps({"t": "ground", "c": cols}))
        for c in MC_SETUP:
            await ws.send(json.dumps({"t": "cmd", "c": c}))

        async def events():
            async for msg in ws:
                print("event:", msg)
        ev = asyncio.create_task(events())

        poses = {}
        reader = None
        saved = 0
        t0 = time.perf_counter()
        f = 0
        fov = 60.0
        while (now := time.perf_counter() - t0) < seconds:
            f += 1
            if mode == "tp":
                eye, yaw, pitch, feet, body = third_person(now)
                poses[f] = (eye, yaw, pitch, fov, feet)
                await ws.send(json.dumps({"t": "cam", "f": f, "p": list(eye), "r": [yaw, pitch, 0.0], "fov": fov, "fp": False,
                                          "pl": list(feet), "h": body}))
            else:
                a = now * 0.5
                eye = (CENTER[0] + 7 * math.sin(a), GROUND_Y + 2.2 + math.sin(a * 0.7), CENTER[2] + 7 * math.cos(a))
                yaw, pitch = look_at(eye, (CENTER[0], GROUND_Y + 1.0, CENTER[2]))
                poses[f] = (eye, yaw, pitch, fov, None)
                await ws.send(json.dumps({"t": "cam", "f": f, "p": list(eye), "r": [yaw, pitch, 0.0], "fov": fov, "fp": True}))
            if reader is None:
                try:
                    reader = MCFrames()
                except (OSError, RuntimeError):
                    pass
            if reader is not None and now > 2.0 and saved < 6 and f % 45 == 0:
                fr = reader.latest()
                if fr is not None and fr.host_frame in poses:
                    e, yw, pt, fv, feet = poses[fr.host_frame]
                    boxes = [(HOST_PILLAR, (0.8, 0.15, 0.1))]
                    if feet is not None:  # a flat blue marker where the host's player stands
                        boxes.append((((feet[0] - 0.3, GROUND_Y, feet[2] - 0.3), (feet[0] + 0.3, GROUND_Y + 0.02, feet[2] + 0.3)), (0.1, 0.3, 0.95)))
                    host_rgb, host_depth = host_render(fr.width, fr.height, e, yw, pt, fv, boxes)
                    comp = composite(host_rgb, host_depth, fr)
                    Image.fromarray((comp * 255).astype(np.uint8)).save(out / f"comp_{saved}.png")
                    Image.fromarray(fr.world_rgba[..., :3]).save(out / f"mc_world_{saved}.png")
                    Image.fromarray(fr.overlay_rgba).save(out / f"mc_overlay_{saved}.png")
                    lag = f - fr.host_frame
                    print(f"saved {saved}: mc frame {fr.mc_frame} for host frame {fr.host_frame} (now {f}, {lag} behind), "
                          f"{fr.width}x{fr.height}, near {fr.near} far {fr.far:.0f}, flags {fr.flags}, "
                          f"world alpha>0 {np.mean(fr.world_rgba[..., 3] > 0):.3f}, "
                          f"depth range {fr.world_depth.min():.5f}..{fr.world_depth.max():.5f}")
                    saved += 1
            await asyncio.sleep(1 / 60)
        ev.cancel()
        if reader is not None:
            print("published frames:", reader.published())


if __name__ == "__main__":
    asyncio.run(run(float(sys.argv[1]) if len(sys.argv) > 1 else 12.0, sys.argv[2] if len(sys.argv) > 2 else OUT,
                    sys.argv[3] if len(sys.argv) > 3 else "fp"))
