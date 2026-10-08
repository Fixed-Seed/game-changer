"""Place TNT by 'right-clicking' (key messages) while the host camera looks at the barrier ground, then light it."""
import asyncio, json
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:25599") as ws:
        await ws.recv()
        state = {"yaw": 0.0, "pitch": 50.0}
        async def cam():
            f = 0
            while True:
                f += 1
                await ws.send(json.dumps({"t": "cam", "f": f, "p": [0.5, 65.62, 0.5], "r": [state["yaw"], state["pitch"], 0.0], "fov": 70, "fp": True}))
                await asyncio.sleep(1 / 60)
        task = asyncio.create_task(cam())
        await ws.send(json.dumps({"t": "ground", "c": [v for x in range(-12, 13) for z in range(-12, 13) for v in (x, z, 63, 63)]}))
        await ws.send(json.dumps({"t": "cmd", "c": "fill -12 64 -12 12 70 12 minecraft:air"}))
        await asyncio.sleep(1.0)
        await ws.send(json.dumps({"t": "slot", "n": 0}))
        await asyncio.sleep(0.3)
        for yaw in (-30, -15, 0, 15, 30):
            state["yaw"] = yaw
            await asyncio.sleep(0.25)
            await ws.send(json.dumps({"t": "key", "k": "use", "down": True}))
            await asyncio.sleep(0.08)
            await ws.send(json.dumps({"t": "key", "k": "use", "down": False}))
        await asyncio.sleep(0.5)
        await ws.send(json.dumps({"t": "cmd", "c": "execute if block 0 64 1 minecraft:tnt"}))
        await ws.send(json.dumps({"t": "cmd", "c": "execute store result score @p dummy run fill -3 64 -3 3 64 3 minecraft:tnt replace minecraft:tnt"}))
        await asyncio.sleep(0.5)
        state["yaw"] = 0
        await asyncio.sleep(0.3)
        await ws.send(json.dumps({"t": "slot", "n": 1}))
        await asyncio.sleep(0.3)
        await ws.send(json.dumps({"t": "key", "k": "use", "down": True}))
        await asyncio.sleep(0.08)
        await ws.send(json.dumps({"t": "key", "k": "use", "down": False}))
        n = 0
        try:
            while True:
                m = await asyncio.wait_for(ws.recv(), 8)
                if "explosion" in m:
                    n += 1
                    print("event:", m)
        except asyncio.TimeoutError:
            pass
        print("explosions:", n)
        task.cancel()

asyncio.run(main())
