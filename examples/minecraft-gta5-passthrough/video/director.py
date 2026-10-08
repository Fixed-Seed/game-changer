"""Scripted shots for the demo videos, driven through Minecraft's link: GTA ops go to the GTA plugin
({"t":"gta",...}, relayed by the mod), Minecraft input (hotbar, right/left click) goes to the mod itself.

Run with Windows Python (Minecraft's link listens on Windows' 127.0.0.1), with websockets installed:
    python director.py scout [x y z]    # teleport there (GTA coordinates; default: stay) and grab screenshots all round
    python director.py shoot [cfg.json] # the sequence; prints a JSON event log (for titles) at the end
    python director.py op <op> ['{json}']   # one GTA op, e.g. op teleport '{"x":..,"y":..,"z":..}'; prints the state
Screenshots go to <PASSTHROUGH_WIN_DIR>\\shots (C:\\dev\\passthrough\\shots), taken with FSGC_FFMPEG_WIN (default: the
ffmpeg on PATH; it needs gfxcapture, which `fsgc win setup` provides).
"""
import asyncio
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import websockets

URL = "ws://127.0.0.1:25599"
WIN_DIR = os.environ.get("PASSTHROUGH_WIN_DIR", r"C:\dev\passthrough")
FFMPEG = os.environ.get("FSGC_FFMPEG_WIN", "ffmpeg")
SHOTS = Path(WIN_DIR) / "shots"


def smooth(t):
    return t * t * (3 - 2 * t)


class Director:
    def __init__(self, ws):
        self.ws = ws
        self.state = None
        self.events = []
        self.t0 = time.time()
        self.boomed = asyncio.Event()
        self.jumped = asyncio.Event()
        self.probe = None
        self.info = None
        self.reader = asyncio.create_task(self._read())

    async def _read(self):
        async for m in self.ws:
            if '"gtastate"' in m:
                self.state = json.loads(m)
            elif '"explosion"' in m:
                self.mark("explosion")
                self.boomed.set()
            elif '"jump"' in m:
                self.mark("jump")
                self.jumped.set()
            elif '"probe"' in m:
                self.probe = json.loads(m)["probe"]
            elif '"gtainfo"' in m and ('"mobs"' in m or '"fx"' in m):
                self.info = json.loads(m)

    def mark(self, name):
        self.events.append((round(time.time() - self.t0, 3), name))

    async def gta(self, op, **kw):
        await self.ws.send(json.dumps({"t": "gta", "op": op, **kw}, separators=(",", ":")))

    async def mc(self, **msg):
        await self.ws.send(json.dumps(msg, separators=(",", ":")))

    async def slot(self, n):
        await self.mc(t="slot", n=n)
        await asyncio.sleep(0.25)

    async def click(self, key="use", hold=0.06):
        await self.mc(t="key", k=key, down=True)
        await asyncio.sleep(hold)
        await self.mc(t="key", k=key, down=False)

    async def look(self, heading, pitch, duration=0.0, start=None):
        """Camera relative to the player: heading (degrees, + = left), pitch (+ = up). Eased like a mouse move."""
        if duration <= 0 or start is None:
            await self.gta("look", heading=heading, pitch=pitch)
            return
        h0, p0 = start
        n = max(1, int(duration * 60))
        for i in range(1, n + 1):
            k = smooth(i / n)
            await self.gta("look", heading=h0 + (heading - h0) * k, pitch=p0 + (pitch - p0) * k)
            await asyncio.sleep(1 / 60)

    async def wait_state(self, timeout=5.0):
        self.state = None
        t = time.time()
        while self.state is None and time.time() - t < timeout:
            await asyncio.sleep(0.05)
        return self.state


def screenshot(name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / f"{name}.png"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "gfxcapture=window_exe=GTA5.exe:capture_cursor=0,hwdownload,format=bgra", "-frames:v", "1", str(out)], timeout=30)
    return out


def offset(p, heading, dist):
    """The point `dist` metres from p in GTA heading direction (0 = +y, 90 = -x)."""
    h = math.radians(heading)
    return [p[0] - math.sin(h) * dist, p[1] + math.cos(h) * dist, p[2]]


async def scout(d, p=None):
    """Screenshots in four directions from GTA position p (default: where the player stands now)."""
    if p is None:
        s = await d.wait_state()
        if s is None:
            sys.exit("no state from GTA: is the plugin connected?")
        p = s["pos"]
    await d.gta("safe")
    await d.gta("time", h=18, m=0)
    await d.gta("weather", w="EXTRASUNNY")
    await d.gta("view", mode=1)
    for h in (0, 90, 180, 270):
        await d.gta("teleport", x=p[0], y=p[1], z=p[2], h=h)
        await asyncio.sleep(2.5)
        print(h, await d.wait_state())
        screenshot(f"scout_{round(p[0])}_{round(p[1])}_{h}")


async def shoot(d, cfg):
    """The sequence. cfg keys: start, stand (GTA xyz), h_in (heading to face while building), pattern [[dh, pitch], ...]."""
    await d.gta("safe")
    await d.gta("time", h=cfg.get("hour", 18), m=0)
    await d.gta("weather", w="EXTRASUNNY")
    await d.slot(4)  # TNT (the hotbar is set in PassthroughClient.SETUP)
    start, stand, h_in = cfg["start"], cfg["stand"], cfg["h_in"]
    await d.gta("teleport", x=start[0], y=start[1], z=start[2], h=h_in)
    await d.gta("view", mode=1)
    await asyncio.sleep(cfg.get("settle", 3.0))

    d.mark("approach")
    await d.gta("walk", x=stand[0], y=stand[1], z=stand[2], speed=cfg.get("walk_speed", 1.0), h=h_in)
    await asyncio.sleep(cfg.get("walk_time", 5.0))
    await d.gta("face", h=h_in)

    d.mark("first_person")
    await d.gta("view", mode=4)
    await asyncio.sleep(0.8)
    await d.look(0, -10)
    d.mark("place")
    prev = (0, -10)
    for dh, pitch in cfg["pattern"]:
        await d.look(dh, pitch, duration=cfg.get("aim_time", 0.22), start=prev)
        prev = (dh, pitch)
        await d.click()
        await asyncio.sleep(cfg.get("click_gap", 0.12))

    d.mark("light")
    await d.slot(5)  # flint and steel
    light = cfg.get("light", [0, -40])
    await d.look(light[0], light[1], duration=0.35, start=prev)
    await d.click()
    d.mark("lit")
    await asyncio.sleep(0.6)

    # run: third person, away from the build, then turn to watch
    await d.gta("view", mode=1)
    away = offset(stand, h_in + 180, cfg.get("run_dist", 14))
    await d.gta("walk", x=away[0], y=away[1], z=away[2], speed=3.0, h=h_in + 180)
    d.mark("run")
    await asyncio.sleep(cfg.get("run_time", 3.2))
    await d.gta("face", h=h_in)
    await d.look(0, 5)
    d.mark("watch")
    await asyncio.sleep(cfg.get("watch_time", 9.0))
    d.mark("end")


async def run_steps(d, steps, origin=None, h_in=0.0):
    """A data-driven shot list. Positions are [right, forward, up] metres from `origin` (GTA xyz) in the frame of
    heading `h_in`, so the whole sequence can be moved/turned by changing two numbers; with no origin (or
    "absolute") they are plain GTA coordinates. Steps:
      ["time", h], ["weather", "EXTRASUNNY"], ["view", mode], ["wait", s], ["mark", name], ["slot", n],
      ["teleport", [r, f, u], dh], ["walk", [r, f, u], speed, wait_s], ["face", dh], ["look", dh, pitch, secs],
      ["place", [[dh, pitch], ...], aim_s, gap_s], ["click", key], ["ped", model, [r, f, u], dh, scenario],
      ["car", model, [r, f, u], dh], ["cmd", "minecraft command"], ["gta", op, {...}]
    dh = heading relative to h_in. ["gta", "ped", {..., "anim_dict": d, "anim": a}] plays a looped animation on
    the new ped instead of a scenario."""
    absolute = origin is None or origin == "absolute"   # positions are plain GTA coordinates

    def world(rfu):
        if absolute:
            return list(rfu)
        h = math.radians(h_in)
        fx, fy = -math.sin(h), math.cos(h)   # forward
        rx, ry = math.cos(h), math.sin(h)    # right
        r, f, u = rfu
        return [origin[0] + rx * r + fx * f, origin[1] + ry * r + fy * f, origin[2] + u]

    look = (0.0, 0.0)
    for step in steps:
        kind, args = step[0], step[1:]
        if kind == "time":
            await d.gta("time", h=args[0], m=args[1] if len(args) > 1 else 0)
        elif kind == "weather":
            await d.gta("weather", w=args[0])
        elif kind == "view":
            await d.gta("view", mode=args[0])
        elif kind == "wait":
            await asyncio.sleep(args[0])
        elif kind == "mark":
            d.mark(args[0])
        elif kind == "slot":
            await d.slot(args[0])
        elif kind == "teleport":
            x, y, z = world(args[0])
            await d.gta("teleport", x=x, y=y, z=z, h=h_in + (args[1] if len(args) > 1 else 0))
            look = (0.0, 0.0)
        elif kind == "walk":
            x, y, z = world(args[0])
            await d.gta("walk", x=x, y=y, z=z, speed=args[1] if len(args) > 1 else 1.0)
            if len(args) > 2:
                await asyncio.sleep(args[2])
        elif kind == "face":
            await d.gta("face", h=h_in + args[0])
        elif kind == "look":
            secs = args[2] if len(args) > 2 else 0.3
            await d.look(args[0], args[1], duration=secs, start=look)
            look = (args[0], args[1])
        elif kind == "place":
            aim = args[1] if len(args) > 1 else 0.22
            gap = args[2] if len(args) > 2 else 0.12
            for dh, pitch in args[0]:
                await d.look(dh, pitch, duration=aim, start=look)
                look = (dh, pitch)
                await d.click()
                await asyncio.sleep(gap)
        elif kind == "click":
            await d.click(args[0] if args else "use")
        elif kind == "ped":
            x, y, z = world(args[1])
            await d.gta("ped", model=args[0], x=x, y=y, z=z, h=h_in + (args[2] if len(args) > 2 else 180), scenario=args[3] if len(args) > 3 else "")
        elif kind == "car":
            x, y, z = world(args[1])
            await d.gta("car", model=args[0], x=x, y=y, z=z, h=h_in + (args[2] if len(args) > 2 else 90))
        elif kind == "wait_explosion":  # until Minecraft's first explosion (or a timeout)
            try:
                await asyncio.wait_for(d.boomed.wait(), args[0] if args else 10.0)
            except asyncio.TimeoutError:
                pass
        elif kind == "ensure_boom":  # if nothing has exploded within args[0] s, prime one in front of the player
            try:
                await asyncio.wait_for(d.boomed.wait(), args[0] if args else 5.0)
            except asyncio.TimeoutError:
                await d.mc(t="cmd", c="execute as @p at @s run summon minecraft:tnt ^ ^ ^2.5 {fuse:15}")
                d.mark("fallback_ignite")
        elif kind == "drive":  # Minecraft flies the player, GTA follows: ["drive", on, dist, height]
            await d.gta("drive", on=args[0], dist=args[1] if len(args) > 1 else 5.5, height=args[2] if len(args) > 2 else 1.4)
        elif kind == "cops":  # a police squad vs Minecraft's mobs: ["cops", cars, dist]
            await d.gta("cops", cars=args[0] if args else 3, dist=args[1] if len(args) > 1 else 40)
        elif kind == "spawnmobs":  # ["spawnmobs", "zombie", n, rmin, rmax, arc, yaw]: on the ground in front of Steve
            a = list(args) + [None] * 6
            await d.mc(t="spawnmobs", k=a[0], n=a[1] or 5, rmin=a[2] or 8, rmax=a[3] or 16, arc=a[4] or 40, yaw=a[5] or 0)
        elif kind == "portal":  # ["portal", dist]: build and light a nether portal `dist` m in front of the player
            s = await d.wait_state(3.0)
            h = math.radians(s["h"])
            px, py = s["pos"][0] - math.sin(h) * args[0], s["pos"][1] + math.cos(h) * args[0]
            await d.mc(t="portal", at=[px, s["pos"][2] - 1.0 + s["yoff"], -py], yaw=180.0 - s["h"])
        elif kind == "netheroff":
            await d.mc(t="netheroff")
        elif kind == "mobsclear":
            await d.mc(t="mobsclear")
            await d.gta("mobwarclear")
        elif kind == "armdrive":
            # fly as soon as the player drops off an edge: ["armdrive", heading, pitch, speed, dist, height]
            await d.gta("armdrive", h=args[0], p=args[1], speed=args[2], dist=args[3] if len(args) > 3 else 5.5,
                        height=args[4] if len(args) > 4 else 1.4)
            d.jumped.clear()
        elif kind == "wait_jump":  # until the drop starts the flight: ["wait_jump", timeout_s, fallback_speed]
            try:
                await asyncio.wait_for(d.jumped.wait(), args[0])
            except asyncio.TimeoutError:
                await d.gta("drive", on=1)
                await d.mc(t="glide", on=True, speed=args[1] if len(args) > 1 else 1.0)
                d.mark("fallback_jump")
        elif kind == "glide":  # elytra on and launch along the look: ["glide", speed]
            await d.mc(t="glide", on=True, speed=args[0] if args else 1.4)
        elif kind == "fly":
            # ["fly", [[t, heading, pitch], ...], boost_every_s]: ease through look keyframes (GTA heading/pitch),
            # firing a firework (the use key, rockets in hand) every boost_every_s
            keys, every = args[0], args[1] if len(args) > 1 else 0
            t0 = time.time()
            next_boost = 0.0
            while (t := time.time() - t0) < keys[-1][0]:
                k = max(i for i in range(len(keys)) if keys[i][0] <= t)
                a, b = keys[k], keys[min(k + 1, len(keys) - 1)]
                u = 0.0 if b[0] == a[0] else smooth((t - a[0]) / (b[0] - a[0]))
                dh = (b[1] - a[1] + 540.0) % 360.0 - 180.0
                await d.gta("flylook", h=a[1] + dh * u, p=a[2] + (b[2] - a[2]) * u)
                if every and t >= next_boost:
                    next_boost = t + every
                    await d.click()
                    d.mark("boost")
                await asyncio.sleep(1 / 60)
        elif kind == "boom":  # a GTA explosion of its own: ["boom", [r, f, u], type, scale]
            x, y, z = world(args[0])
            await d.gta("explode", x=x, y=y, z=z, type=args[1] if len(args) > 1 else 5, scale=args[2] if len(args) > 2 else 1.0)
        elif kind == "cmd":
            await d.mc(t="cmd", c=args[0])
        elif kind == "gta":
            await d.gta(args[0], **(args[1] if len(args) > 1 else {}))


async def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "scout"
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.recv()
        d = Director(ws)
        if what == "scout":
            await scout(d, [float(v) for v in sys.argv[2:5]] if len(sys.argv) > 4 else None)
        elif what == "shoot":
            cfg = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}
            if "steps" in cfg:
                await d.gta("safe")
                await run_steps(d, cfg["steps"], cfg.get("origin"), cfg.get("h_in", 0.0))
            else:
                await shoot(d, cfg)
        elif what == "op":  # one GTA op: python director.py op teleport '{"x":..}'
            await d.gta(sys.argv[2], **(json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}))
            print(json.dumps(await d.wait_state(3.0)))
            if d.probe is not None:
                print(json.dumps({"probe": d.probe}))
            if d.info is not None:
                print(json.dumps(d.info))
        print(json.dumps({"events": d.events}))


if __name__ == "__main__":
    asyncio.run(main())
