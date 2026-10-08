import asyncio, json
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:25599") as ws:
        print(await ws.recv())
        # keep the host "attached" (explosion events are only sent while a host drives the camera)
        async def cam():
            while True:
                await ws.send(json.dumps({"t": "cam", "f": 1, "p": [0.5, 67.0, -4.0], "r": [0.0, 20.0, 0.0], "fov": 60, "fp": True}))
                await asyncio.sleep(1 / 30)
        task = asyncio.create_task(cam())
        await ws.send(json.dumps({"t": "ground", "c": [v for x in range(-10, 11) for z in range(-10, 11) for v in (x, z, 63, 63)]}))
        await ws.send(json.dumps({"t": "cmd", "c": "execute if block 0 63 0 minecraft:barrier"}))
        await ws.send(json.dumps({"t": "cmd", "c": "summon minecraft:tnt 2.5 64 8.5 {fuse:30}"}))
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), 5)
                print("event:", msg)
        except asyncio.TimeoutError:
            pass
        task.cancel()

asyncio.run(main())
