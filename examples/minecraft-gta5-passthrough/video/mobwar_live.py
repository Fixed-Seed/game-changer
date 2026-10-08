"""Mobs vs police with the player in control: set the scene (police barricade across the car park), then keep mob
waves coming at the far end of it, and police reinforcements, until <PASSTHROUGH_WIN_DIR>\\takes\\STOP appears.

Run with Windows Python (with websockets), like director.py:
    python mobwar_live.py
Only director ops go to the games (no keyboard or mouse input): the player plays meanwhile.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import websockets  # noqa: E402
from director import URL, WIN_DIR, Director, run_steps  # noqa: E402

STOP = Path(WIN_DIR) / "takes" / "STOP"
START = [58.0, -1712.0, 29.5]  # GTA: the east end of the Davis car park, facing west down it
ARENA = (30.0, -1712.0)        # GTA x, y: where the waves come in, beyond the barricade
GROUND_Z = 28.3                # GTA ground height there
WAVE = [("zombie", 8), ("skeleton", 2), ("creeper", 2), ("spider", 2)]
MAX_ALIVE = 26                 # no new wave while this many are still fighting
WAVE_EVERY = 20.0
COPS_EVERY = 50.0

SETUP = [
    ["time", 17, 30], ["weather", "EXTRASUNNY"],
    ["gta", "copsclear", {}], ["mobsclear"],
    ["gta", "mobfit", {"copsonly": 1}],
    ["teleport", START],
    ["view", 1],
    ["gta", "look", {"heading": 0, "pitch": -4}],
    ["wait", 5.0],
    ["gta", "cops", {"cars": 3, "dist": 11, "line": 1}],
    ["wait", 5.0],
]


async def main():
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.recv()
        d = Director(ws)
        await d.gta("safe")
        await run_steps(d, SETUP, "absolute", 90.0)
        state = await d.wait_state(3.0)
        yoff = state["yoff"] if state else -0.3
        at = [ARENA[0], GROUND_Z + yoff + 1.0, -ARENA[1]]  # Minecraft coordinates

        async def wave():
            for kind, n in WAVE:
                await d.mc(t="spawnmobs", k=kind, n=n, rmin=0, rmax=7, at=at)
            d.mark("wave")

        await wave()
        print("scene ready", flush=True)
        t0 = time.time()
        next_wave, next_cops = t0 + WAVE_EVERY, t0 + COPS_EVERY
        while not STOP.exists() and time.time() - t0 < 30 * 60:
            now = time.time()
            if now >= next_wave:
                next_wave = now + WAVE_EVERY
                d.info = None
                await d.gta("mobinfo")
                for _ in range(40):
                    if d.info is not None:
                        break
                    await asyncio.sleep(0.05)
                alive = len(d.info["mobs"]) if d.info else 0
                if alive < MAX_ALIVE:
                    await wave()
                print(json.dumps({"t": round(now - t0), "alive": alive, "hits": (d.info or {}).get("hits"), "dmg": (d.info or {}).get("dmg")}), flush=True)
            if now >= next_cops:
                next_cops = now + COPS_EVERY
                await d.gta("cops", cars=2, dist=30)  # more police, at the roads near the player
                d.mark("cops")
            await asyncio.sleep(0.5)
        print(json.dumps({"events": d.events}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
