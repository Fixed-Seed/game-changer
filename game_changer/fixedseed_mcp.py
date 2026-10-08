"""FixedSeed MCP server on stdio: the `fsgc fixedseed` client as MCP tools, for agents that prefer tools to a shell.

    fsgc fixedseed mcp        # what .mcp.json, .cursor/mcp.json, .vscode/mcp.json, .codex/config.toml and
                            # gemini-extension.json launch; reads FIXEDSEED_KEY (and FIXEDSEED_API) from the env

Tools: search_models, get_model, upload_file, estimate, generate, generate_batch, get_request, get_balance,
passthrough. `generate` uploads local files named in *_url / *_urls inputs, queues the request, waits (up to
timeout_seconds), downloads every output into out_dir and logs it to fixedseed_manifest.jsonl, the same as the CLI;
results come back with absolute paths and small previews the agent can see (images, an archive's preview, video
keyframes, an audio waveform). Long jobs come back as a request_id to finish with get_request. generate and
generate_batch keep a ledger in out_dir, so asking again for the same model, input and name within an hour (a client
that timed out, a retry) collects the earlier request instead of paying twice; generate_batch also refuses a plan
whose maximum cost is over its max_cents. `passthrough` plans two games running at once, one drawn inside the other (`fsgc
passthrough plan`; no key needed), and the `passthrough` prompt hands an agent that plan as a ready instruction:
clients that support MCP prompts show it as a slash command. Newline-delimited JSON-RPC 2.0, stdlib only; stdout
carries protocol messages only.
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

from game_changer import __version__
from game_changer import fixedseed as fs

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

_STR = {"type": "string"}
TOOLS = [
    dict(name="search_models",
         description="Search FixedSeed's live model catalog (image, video, 3D, audio, text). Returns model ids to pass to "
                     "get_model and generate. An empty query lists everything of that kind.",
         inputSchema={"type": "object", "properties": {
             "query": {"type": "string", "description": "words to match, e.g. 'image to 3d', 'upscale', 'sound effect'"},
             "kind": {"type": "string", "enum": ["image", "video", "audio", "model", "archive", "text", "json"],
                      "description": "output kind; archive = a ZIP of several files (rigs, PBR sets, motion, SVG)"},
             "limit": {"type": "integer", "default": 20}}}),
    dict(name="get_model",
         description="Input schema, example input and pricing of one model. Read it before calling generate.",
         inputSchema={"type": "object", "required": ["model"], "properties": {"model": _STR}}),
    dict(name="upload_file",
         description="Upload a local file and return a private file_url to use in model inputs. generate already does this "
                     "for local paths in *_url / *_urls fields, so this is only needed for unusual fields.",
         inputSchema={"type": "object", "required": ["path"], "properties": {"path": _STR}}),
    dict(name="estimate",
         description="What a plan would cost before anything is spent: each model's typical (starting) and maximum charge "
                     "times its count, from the live catalog, and the wallet balance when a key is set. Use it before "
                     "3D, video, long music or any batch, and tell the user the range.",
         inputSchema={"type": "object", "required": ["items"], "properties": {
             "items": {"type": "array", "items": {"type": "object", "required": ["model"], "properties": {
                 "model": _STR, "n": {"type": "integer", "minimum": 1, "default": 1}}}}}}),
    dict(name="generate",
         description="Run a FixedSeed model and download its outputs (PNG, MP4, WAV, GLB...) into out_dir; ZIP results are "
                     "unpacked into out_dir/<name>/ with their folders. `input` follows the model's schema from "
                     "get_model; local file paths in *_url / *_urls fields are uploaded automatically. The result lists "
                     "absolute file paths and shows small previews. If the job outlasts timeout_seconds the result is a "
                     "request_id: call get_request later, or call generate again with the same model, input and name, "
                     "which collects that request instead of paying again (within an hour). For a new variation of "
                     "the same request, give a new name or fresh: true.",
         inputSchema={"type": "object", "required": ["model", "input"], "properties": {
             "model": {"type": "string", "description": "e.g. fixedseed/item-sprite, openai/gpt-image-2.5-sunburst"},
             "input": {"type": "object", "description": "model input, per get_model's input_schema"},
             "out_dir": {"type": "string", "default": "assets/gen"},
             "name": {"type": "string", "description": "output file stem (default: last part of the model id)"},
             "wait": {"type": "boolean", "default": True, "description": "false = queue and return the request_id at once"},
             "timeout_seconds": {"type": "integer", "default": 600},
             "fresh": {"type": "boolean", "default": False, "description": "submit anew even if this exact request ran in the last hour"},
             "max_cents": {"type": "integer", "description": "refuse if the model's maximum charge is over this (US cents)"}}}),
    dict(name="generate_batch",
         description="Run several requests at once (every sprite for a mod, a set of sound effects) under a spend cap: new "
                     "requests are refused when their maximum cost adds up to more than max_cents. Files download into "
                     "out_dir as each finishes. Whatever is still running after timeout_seconds comes back as pending; "
                     "call generate_batch again with the same jobs to collect it: requests from the last hour with the "
                     "same model, input and name are collected, never paid twice.",
         inputSchema={"type": "object", "required": ["jobs", "max_cents"], "properties": {
             "jobs": {"type": "array", "minItems": 1, "maxItems": 50, "items": {
                 "type": "object", "required": ["model", "input"], "properties": {
                     "model": _STR, "input": {"type": "object"},
                     "name": {"type": "string", "description": "output file stem; unique within the batch"}}}},
             "max_cents": {"type": "integer", "minimum": 0, "description": "the most the new requests may cost, US cents"},
             "out_dir": {"type": "string", "default": "assets/gen"},
             "timeout_seconds": {"type": "integer", "default": 50, "description": "how long to wait before returning"},
             "fresh": {"type": "boolean", "default": False}}}),
    dict(name="get_request",
         description="Status of a request; when it has succeeded, download its outputs into out_dir.",
         inputSchema={"type": "object", "required": ["request_id"], "properties": {
             "request_id": _STR, "out_dir": {"type": "string", "default": "assets/gen"}, "name": _STR}}),
    dict(name="get_balance", description="The FixedSeed API wallet: spendable balance and pending holds, in US cents.",
         inputSchema={"type": "object", "properties": {}}),
    dict(name="passthrough",
         description="Plan a passthrough between two games: both run at once with a mod in each, one drawn inside the "
                     "other, with camera, collision and events crossing a local link. Fingerprints both games when "
                     "they're installed, stops at online-only games, picks the host (the game the player plays in), "
                     "lists what each engine offers, and returns the link contract, milestones with the proof each "
                     "needs, and prior field notes. Reads only; out_dir also writes PLAN.md and MODLOG.md there "
                     "(never replacing a file). Needs no FixedSeed key.",
         inputSchema={"type": "object", "required": ["game_a", "game_b"], "properties": {
             "game_a": {"type": "string", "description": "a game: its name (e.g. 'minecraft') or install folder"},
             "game_b": {"type": "string", "description": "the other game"},
             "host": {"type": "string", "description": "the game the player plays in (default: whichever hosts "
                                                       "better)"},
             "idea": {"type": "string", "description": "what should cross over, in one sentence"},
             "out_dir": {"type": "string", "description": "start the working folder here (PLAN.md, MODLOG.md)"}}}),
]

PROMPTS = [
    dict(name="passthrough", title="Passthrough two games",
         description="Plan and build a passthrough: two games running at once, one drawn inside the other.",
         arguments=[dict(name="game_a", description="a game (name or install folder)", required=True),
                    dict(name="game_b", description="the other game", required=True),
                    dict(name="idea", description="what should cross over, in one sentence", required=False)]),
]


def _absolute(value: dict) -> dict:
    """Result file paths as absolute paths: the server's working directory is not the agent's."""
    if isinstance(value.get("files"), list):
        value["files"] = [os.path.abspath(f) for f in value["files"]]
    for item in value.get("items") or []:
        item["files"] = [os.path.abspath(f) for f in item.get("files") or []]
    return value


def _generate(a: dict) -> dict:
    model, out = a["model"], a.get("out_dir") or "assets/gen"
    name = a.get("name") or model.split("/")[-1]
    timeout = int(a.get("timeout_seconds") or 600) if a.get("wait") is not False else 0
    res = fs.batch([dict(model=model, input=a.get("input") or {}, name=name)], out, a.get("max_cents"),
                   timeout=timeout, fresh=bool(a.get("fresh")), quiet=True)
    item = res["items"][0]
    if item["status"] in ("failed", "canceled"):
        raise RuntimeError(f"{model} {item['status']}: {item.get('error')} (request {item['request_id']})")
    if item["status"] == "download_failed":
        raise RuntimeError(f"{model} succeeded (request {item['request_id']}) but its files didn't download: "
                           f"{item.get('error')}. Call get_request with this id to collect them; don't generate again.")
    if item["status"] != "succeeded":
        item["note"] = "still running: call get_request with this id later, or generate again with the same input and name"
    return _absolute(item)


def _generate_batch(a: dict) -> dict:
    if not isinstance(a.get("max_cents"), int):
        raise ValueError("max_cents is required: the most the new requests may cost, in US cents")
    res = fs.batch(a.get("jobs") or [], a.get("out_dir") or "assets/gen", a["max_cents"],
                   timeout=int(a.get("timeout_seconds") or 50), fresh=bool(a.get("fresh")), quiet=True)
    if res["pending"] or res["not_submitted"]:
        res["note"] = ("some requests are still running or waiting for a free slot (the plan allows only so many at "
                       "once): call generate_batch again with the same jobs to continue; nothing is paid twice")
    return _absolute(res)


def _estimate(a: dict) -> dict:
    est = fs.estimate(a.get("items") or [])
    if os.environ.get("FIXEDSEED_KEY"):
        try:
            est["balance_cents"] = fs.balance().get("balance_cents")
        except SystemExit:
            pass
    return est


def _get_request(a: dict) -> dict:
    rid = a["request_id"]
    st = fs._req("GET", f"/v1/requests/{rid}")
    if st.get("status") != "succeeded":
        return st
    res = fs.result(rid) or {"request_id": rid, "output": st.get("output")}
    files = fs.save(res, st.get("model"), None, a.get("out_dir") or "assets/gen", a.get("name") or rid)
    return _absolute(dict(request_id=rid, status="succeeded", model=st.get("model"), files=files, output=res.get("output")))


def _get_model(a: dict) -> dict:
    return {**fs.schema(a["model"]), **fs.price(a["model"])}


def _passthrough(a: dict) -> str:
    from game_changer import passthrough as pt   # imported on first use; stdlib only, like this server
    p = pt.plan(a["game_a"], a["game_b"], host=a.get("host"), idea=a.get("idea"))
    text = pt.markdown(p)
    if a.get("out_dir"):
        wrote, kept = pt.write(p, a["out_dir"])
        text += "\n" + "".join([f"Wrote {f}\n" for f in wrote] + [f"Kept {f} (it already exists)\n" for f in kept])
    return text


HANDLERS = {
    "search_models": lambda a: fs.search(a.get("query") or "", a.get("kind"), int(a.get("limit") or 20)),
    "get_model": _get_model,
    "upload_file": lambda a: {"file_url": fs.upload(a["path"])},
    "estimate": _estimate,
    "generate": _generate,
    "generate_batch": _generate_batch,
    "get_request": _get_request,
    "get_balance": lambda a: fs.balance(),
    "passthrough": _passthrough,
}


def get_prompt(name: str, args: dict) -> dict:
    """prompts/get: the passthrough plan for two games, wrapped as an instruction to the agent."""
    if name != "passthrough":
        raise ValueError(f"unknown prompt {name!r}")
    a, b = args.get("game_a"), args.get("game_b")
    if not a or not b:
        raise ValueError("game_a and game_b are required")
    from game_changer import passthrough as pt
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        text = pt.prompt_text(a, b, args.get("idea") or None)
    return dict(description=f"Passthrough: {a} and {b}",
                messages=[dict(role="user", content=dict(type="text", text=text))])


PREVIEW_TOOLS = {"generate", "generate_batch", "get_request"}
PREVIEW_LIMIT = 4
PREVIEW_EDGE = 512


def _result_files(value) -> list[str]:
    if not isinstance(value, dict):
        return []
    files = list(value.get("files") or [])
    for item in value.get("items") or []:
        files += item.get("files") or []
    return [f for f in files if isinstance(f, str)]


def _png_block(img) -> dict:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return dict(type="image", data=base64.b64encode(buf.getvalue()).decode(), mimeType="image/png")


def _image_preview(path: str):
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGBA")
        w, h = im.size
        if max(w, h) < 160:                              # pixel art: enlarge with hard edges so every pixel shows
            k = max(1, 256 // max(w, h))
            im = im.resize((w * k, h * k), Image.NEAREST)
        elif max(w, h) > PREVIEW_EDGE:
            im.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.LANCZOS)
        bg = Image.new("RGBA", im.size, (43, 45, 49, 255))   # transparency shows as dark grey
        bg.alpha_composite(im)
        return bg.convert("RGB")


def _video_preview(path: str):
    """Three frames (start, middle, end) side by side; needs ffmpeg."""
    from PIL import Image

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([ffmpeg, "-loglevel", "error", "-i", path, "-vf", "thumbnail=60,scale=240:-2", "-frames:v", "3",
                        "-vsync", "vfr", os.path.join(tmp, "f%d.png")], capture_output=True, timeout=60)
        frames = [Image.open(os.path.join(tmp, f)).convert("RGB") for f in sorted(os.listdir(tmp))]
        if not frames:
            return None
        strip = Image.new("RGB", (sum(f.width for f in frames) + 4 * (len(frames) - 1), max(f.height for f in frames)))
        x = 0
        for f in frames:
            strip.paste(f, (x, 0))
            x += f.width + 4
        return strip


def _audio_preview(path: str):
    """The waveform of a WAV (other formats through ffmpeg), 640x120."""
    import wave
    from PIL import Image, ImageDraw

    src = path
    tmp = None
    if not path.lower().endswith(".wav"):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return None
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-i", path, "-ac", "1", "-ar", "8000", tmp],
                       capture_output=True, timeout=60)
        src = tmp
    try:
        with wave.open(src) as w:
            width, n = w.getsampwidth(), w.getnframes()
            if width != 2 or n == 0:
                return None
            data = w.readframes(n)
            channels = w.getnchannels()
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    import array
    samples = array.array("h", data)[::channels]
    cols, img = 640, Image.new("RGB", (640, 120), (43, 45, 49))
    d = ImageDraw.Draw(img)
    step = max(1, len(samples) // cols)
    for x in range(cols):
        chunk = samples[x * step:(x + 1) * step] or [0]
        lo, hi = min(chunk) / 32768, max(chunk) / 32768
        d.line([(x, 60 - hi * 58), (x, 60 - lo * 58)], fill=(120, 190, 255))
    return img


def previews(files: list[str]) -> list[dict]:
    """Small images of a result for the agent to look at: pictures, an archive's preview.png (or its first pictures),
    video keyframes, audio waveforms. Optional: nothing is shown without Pillow, and a file that can't be read is
    skipped."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return []
    chosen = [f for f in files if os.path.basename(f) == "preview.png"]
    chosen += [f for f in files if f not in chosen and os.path.basename(f) != "manifest.json"]
    out = []
    for f in chosen:
        if len(out) >= PREVIEW_LIMIT:
            break
        ext = os.path.splitext(f)[1].lower()
        try:
            if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                img = _image_preview(f)
            elif ext in (".mp4", ".webm", ".mov"):
                img = _video_preview(f)
            elif ext in (".wav", ".mp3", ".ogg", ".flac"):
                img = _audio_preview(f)
            else:
                continue
        except Exception:  # noqa: BLE001 - a preview is a convenience, never a failure
            continue
        if img is not None:
            out.append(_png_block(img))
    return out


def call_tool(name: str, args: dict) -> dict:
    """Run one tool. fsgc's helpers report errors by printing to stderr and exiting, so both are caught here."""
    if name not in HANDLERS:
        return dict(content=[dict(type="text", text=f"unknown tool {name}")], isError=True)
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(err):
            value = HANDLERS[name](args or {})
        text = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
        content = [dict(type="text", text=text)]
        if name in PREVIEW_TOOLS:
            content += previews(_result_files(value))
        return dict(content=content)
    except SystemExit:
        msg = err.getvalue().strip().splitlines()
        return dict(content=[dict(type="text", text=(msg[-1] if msg else "failed").removeprefix("fsgc: "))], isError=True)
    except Exception as e:  # noqa: BLE001 - a tool error must not kill the server
        traceback.print_exc(file=sys.stderr)
        return dict(content=[dict(type="text", text=f"{type(e).__name__}: {e}")], isError=True)


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None  # notifications (initialized, cancelled) need no reply
    if method == "initialize":
        asked = (msg.get("params") or {}).get("protocolVersion")
        result = dict(protocolVersion=asked if asked in PROTOCOLS else PROTOCOLS[0],
                      capabilities={"tools": {}, "prompts": {}},
                      serverInfo={"name": "fixedseed", "version": __version__},
                      instructions="FixedSeed generation for game assets: search_models -> get_model -> generate. "
                                   "Outputs land in out_dir with a fixedseed_manifest.jsonl line each. To put one "
                                   "game inside another, the passthrough tool (or prompt) plans it: host and guest, "
                                   "hooks, the link and milestones.")
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params") or {}
        result = call_tool(p.get("name"), p.get("arguments") or {})
    elif method == "prompts/list":
        result = {"prompts": PROMPTS}
    elif method == "prompts/get":
        p = msg.get("params") or {}
        try:
            result = get_prompt(p.get("name"), p.get("arguments") or {})
        except ValueError as e:
            return dict(jsonrpc="2.0", id=mid, error=dict(code=-32602, message=str(e)))
        except Exception as e:  # noqa: BLE001 - a bad prompt must not kill the server
            traceback.print_exc(file=sys.stderr)
            return dict(jsonrpc="2.0", id=mid, error=dict(code=-32603, message=f"{type(e).__name__}: {e}"))
    elif method == "ping":
        result = {}
    else:
        return dict(jsonrpc="2.0", id=mid, error=dict(code=-32601, message=f"method not found: {method}"))
    return dict(jsonrpc="2.0", id=mid, result=result)


def serve():
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            out.write(json.dumps(dict(jsonrpc="2.0", id=None, error=dict(code=-32700, message="parse error"))) + "\n")
            out.flush()
            continue
        reply = handle(msg)
        if reply is not None:
            out.write(json.dumps(reply) + "\n")
            out.flush()


if __name__ == "__main__":
    serve()
