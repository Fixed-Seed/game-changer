"""FixedSeed MCP server on stdio: the `fsgc fixedseed` client as MCP tools, for agents that prefer tools to a shell.

    fsgc fixedseed mcp        # what .mcp.json, .cursor/mcp.json, .vscode/mcp.json, .codex/config.toml and
                            # gemini-extension.json launch; reads FIXEDSEED_KEY (and FIXEDSEED_API) from the env

Tools: search_models, get_model, upload_file, generate, get_request, get_balance, passthrough. `generate` uploads
local files named in *_url / *_urls inputs, queues the request, waits (up to timeout_seconds), downloads every output
into out_dir and logs it to fixedseed_manifest.jsonl, the same as the CLI. Long jobs come back as a request_id to
finish with get_request. `passthrough` plans two games running at once, one drawn inside the other (`fsgc
passthrough plan`; no key needed), and the `passthrough` prompt hands an agent that plan as a ready instruction:
clients that support MCP prompts show it as a slash command. Newline-delimited JSON-RPC 2.0, stdlib only; stdout
carries protocol messages only.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import time
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
    dict(name="generate",
         description="Run a FixedSeed model and download its outputs (PNG, MP4, WAV, GLB...) into out_dir; ZIP results are "
                     "unpacked into out_dir/<name>/. `input` follows the "
                     "model's schema from get_model; local file paths in *_url / *_urls fields are uploaded automatically. "
                     "If the job outlasts timeout_seconds the result is a request_id: call get_request later.",
         inputSchema={"type": "object", "required": ["model", "input"], "properties": {
             "model": {"type": "string", "description": "e.g. openai/gpt-image-2.5-sunburst, tencent/hunyuan3d-3.1"},
             "input": {"type": "object", "description": "model input, per get_model's input_schema"},
             "out_dir": {"type": "string", "default": "assets/gen"},
             "name": {"type": "string", "description": "output file stem (default: last part of the model id)"},
             "wait": {"type": "boolean", "default": True, "description": "false = queue and return the request_id at once"},
             "timeout_seconds": {"type": "integer", "default": 600}}}),
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


def _generate(a: dict) -> dict:
    model, out = a["model"], a.get("out_dir") or "assets/gen"
    name = a.get("name") or model.split("/")[-1]
    inp = fs.resolve_inputs(a.get("input") or {})
    job = fs.submit(model, inp)
    rid = job["request_id"]
    if a.get("wait") is False:
        return dict(request_id=rid, status=job.get("status"), note="call get_request with this id to collect the result")
    deadline = time.time() + int(a.get("timeout_seconds") or 600)
    while True:
        st = fs._req("GET", f"/v1/requests/{rid}")
        s = st.get("status")
        if s == "succeeded":
            res = fs.result(rid) or {"request_id": rid, "output": st.get("output")}
            return dict(request_id=rid, status=s, files=fs.save(res, model, inp, out, name), output=res.get("output"))
        if s in ("failed", "canceled"):
            raise RuntimeError(f"{model} {s}: {st.get('error') or 'no detail'} (request {rid})")
        if time.time() > deadline:
            return dict(request_id=rid, status=s, queue_position=st.get("queue_position"),
                        note="still running; call get_request with this id later")
        time.sleep(2.0)


def _get_request(a: dict) -> dict:
    rid = a["request_id"]
    st = fs._req("GET", f"/v1/requests/{rid}")
    if st.get("status") != "succeeded":
        return st
    res = fs.result(rid) or {"request_id": rid, "output": st.get("output")}
    files = fs.save(res, st.get("model"), None, a.get("out_dir") or "assets/gen", a.get("name") or rid)
    return dict(request_id=rid, status="succeeded", model=st.get("model"), files=files, output=res.get("output"))


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
    "generate": _generate,
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


def call_tool(name: str, args: dict) -> dict:
    """Run one tool. fsgc's helpers report errors by printing to stderr and exiting, so both are caught here."""
    if name not in HANDLERS:
        return dict(content=[dict(type="text", text=f"unknown tool {name}")], isError=True)
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(err):
            value = HANDLERS[name](args or {})
        text = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
        return dict(content=[dict(type="text", text=text)])
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
