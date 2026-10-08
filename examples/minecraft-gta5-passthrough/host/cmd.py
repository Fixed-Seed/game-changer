"""Send server commands to the passthrough mod: python cmd.py "time set noon" "give @a tnt" ..."""
import asyncio, json, sys
import websockets

async def main(cmds):
    async with websockets.connect("ws://127.0.0.1:25599") as ws:
        await ws.recv()
        for c in cmds:
            await ws.send(json.dumps({"t": "cmd", "c": c}))
        await asyncio.sleep(0.5)

asyncio.run(main(sys.argv[1:]))
