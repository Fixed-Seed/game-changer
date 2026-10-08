"""Game assets from the FixedSeed API (https://fixedseed.com): plain REST, no SDK needed. Needs FIXEDSEED_KEY (env or a .env file).

    fsgc fixedseed sprite "a rusty scrap drone enemy, side view facing left, 16-bit pixel art" --out assets/gen --name drone
    fsgc fixedseed image "key art: ..." --aspect 16:9
    fsgc fixedseed edit "same drone, rotors blurred, second animation frame" --ref assets/gen/drone.png
    fsgc fixedseed rmbg in.png                       # background removal with soft matting (BiRefNet v2)
    fsgc fixedseed upscale in.png --factor 4x        # Topaz image upscaler
    fsgc fixedseed texture "mossy cobblestone"       # natively seamless tiling texture (Z-Image Turbo tiling)
    fsgc fixedseed pbr "rusted sheet metal"          # basecolor/normal/roughness/metalness/height maps (PATINA)
    fsgc fixedseed maps photo.png --map normals      # depth / normals / albedo map of any image
    fsgc fixedseed model3d concept.png               # image -> textured GLB (--engine trellis|hunyuan|tripo|meshy)
    fsgc fixedseed remesh model.glb --faces 8000     # game-ready low-poly remesh (--engine tripo|meshy)
    fsgc fixedseed retexture model.glb ref.png       # new texture on an existing mesh
    fsgc fixedseed rig character.glb --animate 92    # auto-rig a humanoid -> rigged GLB/FBX + walk/run animations
    fsgc fixedseed motion "a knight swings a sword"  # text -> humanoid animation (FBX)
    fsgc fixedseed vector "shield emblem icon"       # SVG icons and emblems
    fsgc fixedseed sfx "laser rifle shot, sci-fi, punchy" --seconds 1.5
    fsgc fixedseed music "tense boss battle, chiptune, 140 bpm" --seconds 60
    fsgc fixedseed voice "You dare challenge the Mothership?" --voice George
    fsgc fixedseed video still.png "camera orbits the boss as it powers up"
    fsgc fixedseed video-rmbg clip.mp4               # video background -> transparency (WebM/ProRes 4444)
    fsgc fixedseed run <model> key=value key:=json image_url=@local.png   # any of the catalog's models
    fsgc fixedseed search "image to 3d" | fsgc fixedseed schema tencent/hunyuan3d-3.1 | fsgc fixedseed price tencent/hunyuan3d-3.1
    fsgc fixedseed balance                           # API wallet
    fsgc fixedseed mcp                               # stdio MCP server with the same tools (see game_changer/fixedseed_mcp.py)

`fsgc fs ...` is the same command. Every call appends a line to <out>/fixedseed_manifest.jsonl (model, inputs,
request id, files) so an asset can be traced and regenerated. Local files passed as inputs are uploaded through
/v1/files first. Multi-file results (rigs, PBR sets, motion, SVG, alpha video) arrive as a ZIP and are unpacked
into <out>/<name>/. The catalog changes: `fsgc fixedseed search` (or the MCP's search_models) lists what is live.
Base URL: FIXEDSEED_API (default https://run.fixedseed.com). Keys: https://fixedseed.com/developers/keys.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from game_changer.common import die

DEFAULT_API = "https://run.fixedseed.com"

# Defaults per recipe (checked against the FixedSeed catalog 2026-10; override any with --model).
MODELS = {
    "image": "google/nano-banana-2",
    "sprite": "openai/gpt-image-2.5-sunburst",   # supports background=transparent
    "edit": "google/nano-banana-2",
    "rmbg": "birefnet/v2",
    "upscale": "topaz/image-upscale",
    "texture": "tongyi/z-image-turbo-tiling",
    "pbr": "patina/material",
    "maps": "fixedseed/image-maps",
    "retexture": "microsoft/trellis-2-retexture",
    "rig": "meshy/rigging",
    "motion": "tencent/hunyuan-motion",
    "vector": "recraft/v4.1-text-to-vector",
    "sfx": "elevenlabs/sound-effects-v2",
    "music": "elevenlabs/music-v2.5",
    "song": "fixedseed/song",
    "voice": "elevenlabs/eleven-v3",
    "voice_clone": "bytedance/seed-audio-1.0",
    "video": "bytedance/seedance-2.5-i2v",
    "video-rmbg": "pixelcut/video-background-removal",
}
MODEL3D = {"trellis": "microsoft/trellis-2", "hunyuan": "tencent/hunyuan3d-3.1",
           "tripo": "tripo/h3.1-image-to-3d", "meshy": "meshy/v7.1-image-to-3d"}
REMESH = {"tripo": "tripo/remesh", "meshy": "meshy/remesh-v5"}
SPRITE_STYLE = ("a single game sprite, the whole subject in frame and centered, clean readable silhouette, "
                "no text, no watermark, no ground shadow, no background scenery")
TERMINAL = ("succeeded", "failed", "canceled")


# --------------------------------------------------------------------------- auth + http


def api_base() -> str:
    return (os.environ.get("FIXEDSEED_API") or DEFAULT_API).rstrip("/")


def fixedseed_key() -> str:
    k = os.environ.get("FIXEDSEED_KEY")
    if not k and os.environ.get("FIXEDSEED_KEY_FILE"):
        k = Path(os.environ["FIXEDSEED_KEY_FILE"]).expanduser().read_text().strip()
    if not k:
        for env in (Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"):
            if env.exists():
                m = re.search(r"^\s*FIXEDSEED_KEY\s*=\s*['\"]?([^'\"\s]+)", env.read_text(), re.M)
                if m:
                    k = m.group(1)
                    break
    if not k:
        die("FIXEDSEED_KEY is not set. Create a key at https://fixedseed.com/developers/keys and `export FIXEDSEED_KEY=...` "
            "(or put FIXEDSEED_KEY=... in a .env file here)")
    return k


def _req(method: str, path: str, body=None, headers=None, auth=True, raw=False, timeout=120, ok=(200, 201, 202)):
    """JSON request against the API (path like /v1/models) or an absolute URL. Retries 429/5xx; POSTs carry an
    Idempotency-Key from the caller, so a retried submit never queues (or charges) twice."""
    url = path if path.startswith("http") else api_base() + path
    h = {"Accept": "application/json", "User-Agent": "game-changer", **(headers or {})}
    if auth:
        h["Authorization"] = "Key " + fixedseed_key()
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = r.read()
                return payload if raw else (json.loads(payload) if payload else {})
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:1500]
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                wait = e.headers.get("Retry-After")
                time.sleep(float(wait) if wait and wait.isdigit() else 2 * (attempt + 1))
                continue
            die(f"fixedseed {method} {url.split('?')[0]} -> HTTP {e.code}: {detail}")
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            die(f"fixedseed {method} {url}: {e.reason}")


# --------------------------------------------------------------------------- files


def upload(path: str | Path) -> str:
    """Local file -> a private file_url FixedSeed models can read (POST /v1/files, then PUT the exact bytes)."""
    p = Path(path)
    if not p.is_file():
        die(f"no such file: {p}")
    data = p.read_bytes()
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if p.suffix.lower() == ".glb":
        ctype = "model/gltf-binary"
    slot = _req("POST", "/v1/files", {"extension": p.suffix.lstrip(".").lower() or "bin", "size_bytes": len(data)})
    put = urllib.request.Request(slot["upload_url"], data=data, headers={"Content-Type": ctype}, method="PUT")
    try:
        urllib.request.urlopen(put, timeout=600).read()
    except urllib.error.HTTPError as e:
        die(f"upload of {p.name} failed: HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")
    return slot["file_url"]


def _as_url(v):
    """'@path' or an existing local path -> uploaded URL; URLs pass through."""
    if isinstance(v, str) and v.startswith("@"):
        return upload(v[1:])
    if isinstance(v, str) and not re.match(r"^(https?|data):", v) and Path(v).is_file():
        return upload(v)
    return v


def resolve_inputs(obj, key=""):
    """Upload local files wherever the model expects a URL: *_url, *_urls, and {"url": ...} objects."""
    if isinstance(obj, dict):
        return {k: resolve_inputs(v, k) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [resolve_inputs(x, key[:-1] if key.endswith("urls") else key) for x in obj]
    if key == "url" or key.endswith("_url"):
        return _as_url(obj)
    return obj


def _urls_in(obj, trail=""):
    """Yield (json_path, url, content_type) for every downloadable file in a result."""
    if isinstance(obj, dict):
        u = obj.get("url")
        if isinstance(u, str) and u.startswith("http"):
            yield trail, u, obj.get("content_type") or ""
        for k, v in obj.items():
            if k not in ("url", "get_url"):
                yield from _urls_in(v, f"{trail}.{k}" if trail else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _urls_in(v, f"{trail}[{i}]")


EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif", "audio/mpeg": ".mp3", "audio/wav": ".wav",
       "audio/x-wav": ".wav", "video/mp4": ".mp4", "model/gltf-binary": ".glb", "application/zip": ".zip",
       "application/octet-stream": ""}


def _unpack(zip_path: Path, dest: Path) -> list[str]:
    """Multi-file results (rigs, PBR sets, motion clips, SVG, alpha video) arrive as one ZIP: unpack it into dest/."""
    import zipfile

    dest.mkdir(parents=True, exist_ok=True)
    files = []
    with zipfile.ZipFile(zip_path) as z:
        for member in z.infolist():
            name = Path(member.filename).name  # flat archives; never write outside dest
            if member.is_dir() or not name:
                continue
            target = dest / name
            target.write_bytes(z.read(member))
            files.append(str(target))
    zip_path.unlink()
    return files


def download_outputs(result, out: Path, name: str) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    files, used, first_key = [], set(), None
    for trail, url, ctype in _urls_in(result):
        ext = Path(urllib.parse.urlparse(url).path).suffix or EXT.get(ctype.split(";")[0], "")
        key = re.sub(r"\[\d+\]", "", trail).split(".")[-1] or "file"
        idx = re.findall(r"\[(\d+)\]", trail)
        first_key = first_key or key
        # images[0] -> name, images[1] -> name_2; other outputs (mask, thumbnail) -> name_<key>
        if key == first_key:
            stem = name if not idx or idx[-1] == "0" else f"{name}_{int(idx[-1]) + 1}"
        else:
            stem = f"{name}_{key}" + (f"_{int(idx[-1]) + 1}" if idx and idx[-1] != "0" else "")
        path = out / f"{stem}{ext}"
        n = 1
        while path.name in used:
            n += 1
            path = out / f"{stem}_{n}{ext}"
        used.add(path.name)
        req = urllib.request.Request(url, headers={"User-Agent": "game-changer"})
        with urllib.request.urlopen(req, timeout=600) as r:
            path.write_bytes(r.read())
        if path.suffix == ".zip" and key == "archive":
            files += _unpack(path, out / stem)
        else:
            files.append(str(path))
    return files


# --------------------------------------------------------------------------- queue


def submit(model: str, inp: dict, idempotency_key: str | None = None) -> dict:
    return _req("POST", f"/v1/queue/{model}", inp, headers={"Idempotency-Key": idempotency_key or str(uuid.uuid4())})


def result(request_id: str) -> dict | None:
    """The finished output, or None while the request is still queued or running."""
    url = f"{api_base()}/v1/requests/{request_id}/result"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "game-changer",
                                               "Authorization": "Key " + fixedseed_key()})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            if r.status == 202:
                return None
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        die(f"request {request_id}: HTTP {e.code}: {e.read().decode(errors='replace')[:800]}")


def run(model: str, inp: dict, timeout: float = 1800, quiet: bool = False) -> dict:
    """Queue, poll (printing status to stderr), return {"request_id", "output"}."""
    job = submit(model, inp)
    rid = job["request_id"]
    if not quiet:
        print(f"  [{model}] queued as {rid}", file=sys.stderr)
    t0, last = time.time(), ""
    while True:
        st = _req("GET", f"/v1/requests/{rid}")
        s = st.get("status")
        if not quiet and s != last:
            pos = f" (queue position {st['queue_position']})" if s == "queued" and st.get("queue_position") else ""
            print(f"  [{model}] {s}{pos}", file=sys.stderr)
        last = s
        if s == "succeeded":
            res = result(rid) or {"request_id": rid, "output": st.get("output")}
            return res
        if s in ("failed", "canceled"):
            die(f"{model} {s}: {st.get('error') or 'no detail'} (request {rid})")
        if time.time() - t0 > timeout:
            die(f"{model}: still {s} after {timeout:.0f}s (request {rid}); fetch it later with `fsgc fixedseed result {rid}`")
        time.sleep(1.0 if time.time() - t0 < 30 else 3.0)


def save(res: dict, model: str, inp: dict | None, out: str | Path, name: str) -> list[str]:
    """Download a finished request's files into out/ and append its fixedseed_manifest.jsonl line."""
    out = Path(out)
    files = download_outputs(res.get("output"), out, name)
    rec = dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), model=model, name=name, request_id=res.get("request_id"), files=files, input=inp)
    with open(out / "fixedseed_manifest.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    return files


def generate(model: str, inp: dict, out: str | Path, name: str, quiet=False) -> dict:
    """run + download every output file + manifest line. Returns {'files': [...], 'request_id': ..., 'output': ...}."""
    inp = resolve_inputs(inp)
    res = run(model, inp, quiet=quiet)
    files = save(res, model, inp, out, name)
    if not quiet:
        for p in files:
            print(p)
    return dict(files=files, request_id=res.get("request_id"), output=res.get("output"))


# --------------------------------------------------------------------------- catalog


_CATALOG: dict | None = None
STOPWORDS = {"a", "an", "the", "to", "of", "for", "and", "or", "with", "from", "in", "on", "into", "model"}


def catalog() -> list[dict]:
    """Every live model with its input schema and price (public, no key needed)."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = _req("GET", "/v1/public/catalog", auth=False)
    return _CATALOG.get("models", [])


def model_info(model: str) -> dict:
    for m in catalog():
        if m["id"] == model:
            return m
    die(f"unknown model {model!r}; `fsgc fixedseed search <words>` lists live ones")


def search(q: str = "", kind: str | None = None, limit: int = 20) -> list[dict]:
    """Rank catalog models by how many query words hit the id, name and summary. kind = image|video|audio|model|text|json."""
    words = [w for w in re.split(r"\W+", q.lower()) if w and w not in STOPWORDS]
    hits = []
    for m in catalog():
        if kind and m.get("output_kind") != kind:
            continue
        hay = f"{m['id']} {m.get('name', '')} {m.get('summary', '')}".lower()
        score = sum(w in hay for w in words) if words else 1
        if score:
            hits.append((score, m))
    hits.sort(key=lambda x: -x[0])
    return [dict(model=m["id"], name=m.get("name"), kind=m.get("output_kind"), summary=m.get("summary"))
            for _, m in hits[:limit]]


def schema(model: str) -> dict:
    m = model_info(model)
    s = m.get("input_schema") or {}
    return dict(model=model, output_kind=m.get("output_kind"), required=s.get("required", []),
                any_of=s.get("anyOf"), input=s.get("properties", {}), example=m.get("example_input"))


def price(model: str) -> dict:
    m = model_info(model)
    return dict(model=model, timeout_seconds=m.get("timeout_seconds"), pricing=m.get("pricing"))


def balance() -> dict:
    return _req("GET", "/v1/billing/balance")


# --------------------------------------------------------------------------- recipes


def _kv(pairs: list[str]) -> dict:
    """key=value (string) and key:=json (number/bool/list/object); value '@file' uploads a local file."""
    out = {}
    for p in pairs or []:
        if ":=" in p:
            k, v = p.split(":=", 1)
            out[k] = json.loads(v)
        elif "=" in p:
            k, v = p.split("=", 1)
            out[k] = v
        else:
            die(f"bad argument {p!r}: use key=value or key:=json")
    return out


def _name(args, fallback: str) -> str:
    if getattr(args, "name", None):
        return args.name
    words = re.sub(r"[^a-z0-9 ]", "", fallback.lower()).split()[:5]
    return "_".join(words) or "asset"


def _repeat(n: int, model: str, inp: dict, out, name: str) -> list[str]:
    """FixedSeed returns one result per request, so --n queues n requests."""
    files = []
    for i in range(max(1, n)):
        files += generate(model, inp, out, name if i == 0 else f"{name}_{i + 1}")["files"]
    return files


def _stem(path_or_url: str, suffix: str) -> str:
    return Path(urllib.parse.urlparse(path_or_url).path).stem + suffix


def cmd(args):
    r = args.recipe
    out = getattr(args, "out", "assets/gen")
    extra = _kv(getattr(args, "set", None))
    model = getattr(args, "model", None)
    if r == "mcp":
        from game_changer import fixedseed_mcp
        fixedseed_mcp.serve()
        return
    if r == "search":
        for m in search(args.query, args.kind, args.limit):
            print(f"{m['model']:50} {m['kind'] or '':7}  {m['name']}")
        return
    if r == "schema":
        print(json.dumps(schema(args.model_id), indent=2))
        return
    if r == "price":
        print(json.dumps(price(args.model_id), indent=2))
        return
    if r == "balance":
        print(json.dumps(balance(), indent=2))
        return
    if r == "result":
        res = result(args.request_id)
        if res is None:
            print(f"{args.request_id} is still processing", file=sys.stderr)
            return
        st = _req("GET", f"/v1/requests/{args.request_id}")
        for p in save(res, st.get("model"), None, out, args.name or args.request_id):
            print(p)
        print(json.dumps(res, indent=2))
        return
    if r == "upload":
        print(upload(args.file))
        return
    if r == "run":
        generate(args.model_id, _kv(args.params), out, args.name or args.model_id.split("/")[-1])
        return

    if r == "image":
        inp = dict(prompt=args.prompt, aspect_ratio=args.aspect, resolution=args.res)
        _repeat(args.n, model or MODELS["image"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "sprite":
        prompt = f"{args.prompt}. {SPRITE_STYLE}"
        inp = dict(prompt=prompt, background="transparent", quality=args.quality, resolution=args.res, aspect_ratio=args.aspect)
        _repeat(args.n, model or MODELS["sprite"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "edit":
        inp = dict(prompt=args.prompt, image_urls=args.ref, aspect_ratio=args.aspect, resolution=args.res)
        _repeat(args.n, model or MODELS["edit"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "rmbg":
        inp = dict(image_url=args.image, mode=args.mode, resolution=args.resolution, mask_only=args.mask_only or None)
        generate(model or MODELS["rmbg"], {**inp, **extra}, out, args.name or _stem(args.image, "_cut"))
    elif r == "upscale":
        inp = dict(image_url=args.image, upscale_factor=args.factor, enhance_model=args.enhance)
        generate(model or MODELS["upscale"], {**inp, **extra}, out, args.name or _stem(args.image, "_up"))
    elif r == "texture":
        inp = dict(prompt=f"{args.prompt}, seamless tileable texture, flat top-down view, even diffuse lighting",
                   resolution=args.res, aspect_ratio=args.aspect, tiling=args.tiling, seed=args.seed)
        _repeat(args.n, model or MODELS["texture"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "pbr":
        maps = [m.strip() for m in args.maps.split(",") if m.strip()]
        inp = dict(prompt=args.prompt, maps=maps, resolution=args.res, aspect_ratio=args.aspect, tiling=args.tiling,
                   upscale_factor=args.upscale, image_url=args.image, seed=args.seed)
        generate(model or MODELS["pbr"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "maps":
        inp = dict(image_url=args.image, map=args.map, resolution=args.res)
        generate(model or MODELS["maps"], {**inp, **extra}, out, args.name or _stem(args.image, f"_{args.map}"))
    elif r == "model3d":
        engine = "hunyuan" if args.prompt and not args.image else args.engine
        if not args.image and not args.prompt:
            die("model3d needs an image or --prompt")
        if args.prompt and engine != "hunyuan":
            die("text-to-3D (--prompt) runs on --engine hunyuan")
        if engine == "trellis":
            inp = dict(image_url=args.image, vertex_count=args.faces, texture_size=args.texture)
        elif engine == "hunyuan":
            inp = dict(image_url=args.image, prompt=None if args.image else args.prompt, face_count=max(args.faces, 3000),
                       pbr=not args.no_pbr)
        elif engine == "tripo":
            inp = dict(image_url=args.image, face_limit=args.faces, pbr=not args.no_pbr)
        else:
            inp = dict(image_url=args.image, face_count=min(args.faces, 300000), pbr=not args.no_pbr)
        name = args.name or (_stem(args.image, "") if args.image else _name(args, args.prompt))
        generate(model or MODEL3D[engine], {**inp, **extra}, out, name)
    elif r == "remesh":
        if args.engine == "tripo":
            inp = dict(model_url=args.model_file, face_limit=min(max(args.faces, 500), 20000), bake=not args.no_bake)
        else:
            inp = dict(model_url=args.model_file, face_count=args.faces, topology=args.topology)
        generate(model or REMESH[args.engine], {**inp, **extra}, out, args.name or _stem(args.model_file, "_remesh"))
    elif r == "retexture":
        inp = dict(model_url=args.model_file, image_url=args.image, texture_size=args.texture)
        generate(model or MODELS["retexture"], {**inp, **extra}, out, args.name or _stem(args.model_file, "_retex"))
    elif r == "rig":
        inp = dict(model_url=args.model_file, height_meters=args.height, animation=args.animate is not None,
                   animation_id=args.animate)
        generate(model or MODELS["rig"], {**inp, **extra}, out, args.name or _stem(args.model_file, "_rigged"))
    elif r == "motion":
        inp = dict(prompt=args.prompt, duration=args.seconds, seed=args.seed)
        generate(model or MODELS["motion"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "vector":
        inp = dict(prompt=args.prompt, aspect_ratio=args.aspect, colors=args.color, background_color=args.background)
        generate(model or MODELS["vector"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "sfx":
        inp = dict(prompt=args.prompt, duration_seconds=args.seconds, loop=args.loop)
        generate(model or MODELS["sfx"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "music":
        if args.engine == "song":
            inp = dict(style_brief=args.prompt, max_duration=int(args.seconds or 60), seed=args.seed)
            if args.lyrics:
                inp["lyrics"] = args.lyrics
            elif args.lyrics_brief:
                inp["lyrics_brief"] = args.lyrics_brief
            else:
                inp["lyrics"] = "" if not args.vocals else None   # empty lyrics = instrumental
            generate(model or MODELS["song"], {**inp, **extra}, out, _name(args, args.prompt))
        else:
            inp = dict(prompt=args.prompt, duration_seconds=args.seconds, instrumental=not args.vocals)
            generate(model or MODELS["music"], {**inp, **extra}, out, _name(args, args.prompt))
    elif r == "voice":
        if args.voice_ref:  # cloning a reference voice
            who = f"@Audio1 ({args.direction})" if args.direction else "@Audio1"
            inp = dict(prompt=f"{who} says, with no music or background sound: \"{args.text}\"", audio_urls=args.voice_ref,
                       speed=args.speed, sample_rate=44100)
            generate(model or MODELS["voice_clone"], {**inp, **extra}, out, _name(args, args.text))
        else:
            inp = dict(text=args.text, voice=args.voice, stability=args.stability, timestamps=args.timestamps or None)
            generate(model or MODELS["voice"], {**inp, **extra}, out, _name(args, args.text))
    elif r == "video":
        inp = dict(image_url=args.image, prompt=args.prompt, duration=args.seconds, resolution=args.res, generate_audio=args.audio)
        generate(model or MODELS["video"], {**inp, **extra}, out, args.name or _stem(args.image, "_video"))
    elif r == "video-rmbg":
        inp = dict(video_url=args.video, background=args.background, background_color=args.color, output_format=args.format)
        generate(model or MODELS["video-rmbg"], {**inp, **extra}, out, args.name or _stem(args.video, "_cut"))


def register(sub):
    p = sub.add_parser("fixedseed", aliases=["fs"], help="generate assets with FixedSeed (sprites, textures, PBR, 3D, rigs, SFX, music, voice, video)",
                       description=__doc__, formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
    rs = p.add_subparsers(dest="recipe", metavar="<recipe>")

    def recipe(name, help_, *positional, out=True):
        q = rs.add_parser(name, help=help_)
        for pos in positional:
            q.add_argument(pos)
        if out:
            q.add_argument("--out", default="assets/gen", help="output folder (default assets/gen)")
            q.add_argument("--name", help="output file stem")
            q.add_argument("--model", help="override the model")
            q.add_argument("--set", action="append", metavar="K=V", help="extra model input (repeatable; K:=json for numbers)")
        q.set_defaults(func=cmd)
        return q

    q = recipe("image", "text -> image (Nano Banana 2)", "prompt")
    q.add_argument("--aspect", default="1:1", help="e.g. 1:1, 16:9, 3:4, 21:9")
    q.add_argument("--res", default="1K", choices=["512", "1K", "2K", "4K"])
    q.add_argument("--n", type=int, default=1, help="number of images (one request each)")
    q = recipe("sprite", "text -> sprite on a transparent background (GPT Image 2.5 Sunburst)", "prompt")
    q.add_argument("--quality", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    q.add_argument("--res", default="1K", choices=["1K", "2K", "4K"])
    q.add_argument("--aspect", default="1:1")
    q.add_argument("--n", type=int, default=1)
    q = recipe("edit", "edit / make variants of reference images (consistent sets, animation frames)", "prompt")
    q.add_argument("--ref", action="append", required=True, help="reference image (path or URL), repeatable; @Image1.. in the prompt")
    q.add_argument("--aspect", default="auto")
    q.add_argument("--res", default="1K", choices=["512", "1K", "2K", "4K"])
    q.add_argument("--n", type=int, default=1)
    q = recipe("rmbg", "remove the background with soft matting (BiRefNet v2)", "image")
    q.add_argument("--mode", default="general", choices=["general", "general_2k", "general_heavy", "matting", "portrait", "dynamic"],
                   help="matting for hair/fur/smoke edges, general_2k for big images")
    q.add_argument("--resolution", default="1024", choices=["1024", "2048", "2304"], help="2304 needs --mode dynamic")
    q.add_argument("--mask-only", action="store_true", help="return the mask instead of the cutout")
    q = recipe("upscale", "upscale an image (Topaz)", "image")
    q.add_argument("--factor", default="2x", choices=["2x", "4x"])
    q.add_argument("--enhance", default="High Fidelity V2", help="Standard V2, Low Resolution V2, CGI, High Fidelity V2, Text Refine")
    q = recipe("texture", "natively seamless tiling texture (Z-Image Turbo tiling)", "prompt")
    q.add_argument("--res", default="1K", choices=["512", "1K", "2K"])
    q.add_argument("--aspect", default="1:1", choices=["1:1", "2:1", "1:2", "4:3", "3:4", "16:9", "9:16"])
    q.add_argument("--tiling", default="both", choices=["both", "horizontal", "vertical"])
    q.add_argument("--seed", type=int)
    q.add_argument("--n", type=int, default=1)
    q = recipe("pbr", "seamless PBR material: basecolor, normal, roughness, metalness, height (PATINA)", "prompt")
    q.add_argument("--maps", default="basecolor,normal,roughness,metalness,height")
    q.add_argument("--res", default="1K", choices=["512", "1K", "2K"])
    q.add_argument("--aspect", default="1:1", choices=["1:1", "2:1", "1:2", "4:3", "3:4", "16:9", "9:16"])
    q.add_argument("--tiling", default="both", choices=["both", "horizontal", "vertical"])
    q.add_argument("--upscale", type=int, default=0, choices=[0, 2, 4], help="upscale the maps 2x or 4x")
    q.add_argument("--image", help="derive the material from this image instead of only the prompt")
    q.add_argument("--seed", type=int)
    q = recipe("maps", "depth / normals / albedo map of an image (Image Maps)", "image")
    q.add_argument("--map", default="depth", choices=["depth", "normals", "albedo"])
    q.add_argument("--res", default="1K", choices=["1K", "2K"])
    q = recipe("model3d", "image (or --prompt) -> textured 3D model GLB")
    q.add_argument("image", nargs="?", help="concept image (path or URL)")
    q.add_argument("--engine", default="trellis", choices=list(MODEL3D),
                   help="trellis (TRELLIS.2), hunyuan (Hunyuan3D 3.1, also text-to-3D), tripo (Tripo H3.1), meshy (Meshy 7.1)")
    q.add_argument("--prompt", help="text-to-3D when no image is given (hunyuan)")
    q.add_argument("--faces", type=int, default=50_000, help="target faces/vertices (game-ready: 5k-50k)")
    q.add_argument("--texture", type=int, default=2048, choices=[1024, 2048, 4096], help="texture size (trellis)")
    q.add_argument("--no-pbr", action="store_true", help="plain textures instead of PBR")
    q = recipe("remesh", "rebuild a model as game-ready low-poly topology", "model_file")
    q.add_argument("--engine", default="tripo", choices=list(REMESH), help="tripo (500-20k faces, bakes textures) or meshy")
    q.add_argument("--faces", type=int, default=8000)
    q.add_argument("--topology", default="triangle", choices=["triangle", "quad"], help="meshy only")
    q.add_argument("--no-bake", action="store_true", help="tripo: don't bake textures onto the new mesh")
    q = recipe("retexture", "paint a new texture onto an existing model from a reference image (TRELLIS.2)", "model_file", "image")
    q.add_argument("--texture", type=int, default=2048, choices=[1024, 2048, 4096])
    q = recipe("rig", "auto-rig a humanoid model (Meshy) -> rigged GLB/FBX + walk/run animations", "model_file")
    q.add_argument("--height", type=float, default=1.7, help="character height in meters")
    q.add_argument("--animate", type=int, metavar="ID", help="also apply an animation preset from Meshy's library (0 = idle)")
    q = recipe("motion", "text -> humanoid animation clip, FBX (Hunyuan Motion)", "prompt")
    q.add_argument("--seconds", type=float, default=5)
    q.add_argument("--seed", type=int)
    q = recipe("vector", "SVG icons, emblems and UI art (Recraft V4.1)", "prompt")
    q.add_argument("--aspect", default="1:1", choices=["1:1", "4:3", "3:4", "16:9", "9:16"])
    q.add_argument("--color", action="append", metavar="#RRGGBB", help="preferred colour, repeatable")
    q.add_argument("--background", metavar="#RRGGBB", help="background colour")
    q = recipe("sfx", "sound effect (ElevenLabs Sound Effects v2)", "prompt")
    q.add_argument("--seconds", type=float, help="0.5-22; chosen from the prompt when omitted")
    q.add_argument("--loop", action="store_true")
    q = recipe("music", "music track (ElevenLabs Music; --engine song for FixedSeed Song with lyrics)", "prompt")
    q.add_argument("--engine", default="elevenlabs", choices=["elevenlabs", "song"])
    q.add_argument("--seconds", type=float, default=60)
    q.add_argument("--vocals", action="store_true", help="allow vocals (default: instrumental)")
    q.add_argument("--lyrics", help="song: lyrics with [verse]/[chorus] tags")
    q.add_argument("--lyrics-brief", help="song: one line; the model writes the lyrics")
    q.add_argument("--seed", type=int)
    q = recipe("voice", "voice line / narration (ElevenLabs v3 stock voices, or --voice-ref to clone)", "text")
    q.add_argument("--voice", default="Rachel", help="stock voice: Aria, Roger, Sarah, Laura, Charlie, George, Callum, River, Liam, ...")
    q.add_argument("--stability", type=float, default=0.5)
    q.add_argument("--timestamps", action="store_true", help="also return word timings")
    q.add_argument("--voice-ref", action="append", help="reference audio to clone (path or URL, <=30 s); switches to Seed Audio")
    q.add_argument("--direction", help="with --voice-ref: who is speaking and how")
    q.add_argument("--speed", type=float, default=1.0)
    q = recipe("video", "image -> video clip (Seedance 2.5): trailers, cutscenes", "image", "prompt")
    q.add_argument("--seconds", type=int, default=5)
    q.add_argument("--res", default="720p", choices=["480p", "720p", "1080p"])
    q.add_argument("--audio", action="store_true")
    q = recipe("video-rmbg", "remove a video's background (Pixelcut): transparent WebM/ProRes or a solid colour", "video")
    q.add_argument("--background", default="transparent", choices=["transparent", "black", "white", "green", "blue", "magenta", "custom"])
    q.add_argument("--color", metavar="#RRGGBB", help="with --background custom")
    q.add_argument("--format", choices=["webm", "mov", "mp4", "gif"], help="webm (alpha) by default for transparent")
    q = recipe("run", "any model: key=value / key:=json / key=@file", "model_id")
    q.add_argument("params", nargs="*")
    q = recipe("search", "search the FixedSeed catalog", "query", out=False)
    q.add_argument("--kind", choices=["image", "video", "audio", "model", "archive", "text", "json"], help="output kind")
    q.add_argument("--limit", type=int, default=20)
    recipe("schema", "input fields of a model", "model_id", out=False)
    recipe("price", "pricing of a model", "model_id", out=False)
    recipe("balance", "API wallet balance", out=False)
    q = recipe("result", "fetch (and download) a finished request", "request_id")
    recipe("upload", "upload a local file, print its URL", "file", out=False)
    recipe("mcp", "run the FixedSeed MCP server on stdio (for agents without the CLI)", out=False)
