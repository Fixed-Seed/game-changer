"""AoE2 DE .sld sprites: read and write. Needs only numpy (Pillow for to-png).

    python sld.py info u_cav_knight_idleA_x1.sld          # header, canvas, hotspot, layers
    python sld.py roundtrip u_cav_knight_idleA_x1.sld     # decode -> encode -> decode: what the encoder loses
    python sld.py to-png u_cav_knight_idleA_x1.sld out/   # every frame as a PNG (shadow under it, player colour blue)

    frames = sld.read(path)                  # [Frame]: .rgba (h, w, 4), .shadow, .player (h, w), .hx, .hy
    sld.write(path, [dict(rgba=..., hotspot=(x, y), player=mask, shadow=strength), ...])

Reverse-engineered from the game's own files (checked by decoding stock sprites):
  header   "SLDX" u16 version(4) u16 n_frames u16 0 u16 0x10 u32 0xff
           (7490 of the 7743 stock files; most others have 0x0e and a u16 of 100-775 after the 0xff -
           meaning unknown, and the game is happy with ours)
  frame    u16 canvas_w, canvas_h  i16 hotspot_x, hotspot_y  u8 layer_mask  u8 0  u16 frame_index
  layers   in bit order: 0x01 main (BC1), 0x02 shadow (BC4), 0x04 ?, 0x08 damage mask (BC1), 0x10 player colour (BC4)
           each: u32 length (incl. itself, padded to 4), [u16 x1 y1 x2 y2 for main/shadow], u8 flags, u8 ?,
                 u16 n_cmds, n_cmds x (u8 skip, u8 draw) over the layer's 4x4 blocks in row order, blocks (8 bytes each)
           flags & 0x80: blocks not drawn this frame are copied from the previous frame's layer
           layers without their own box use the main layer's box.
"""
import struct

import numpy as np

MAIN, SHADOW, UNK4, DAMAGE, PLAYER = 0x01, 0x02, 0x04, 0x08, 0x10
LAYER_ORDER = (MAIN, SHADOW, UNK4, DAMAGE, PLAYER)
HAS_BOX = (MAIN, SHADOW)
BC1_LAYERS = (MAIN, DAMAGE)


# ----------------------------------------------------------------------------- BC1 / BC4 blocks

def _rgb565(c):
    c = c.astype(np.uint32)
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.int32)


def bc1_decode(blocks):
    """blocks: (n, 8) uint8 -> (n, 4, 4, 4) RGBA uint8."""
    c0 = blocks[:, 0].astype(np.uint16) | (blocks[:, 1].astype(np.uint16) << 8)
    c1 = blocks[:, 2].astype(np.uint16) | (blocks[:, 3].astype(np.uint16) << 8)
    idx = blocks[:, 4:8].astype(np.uint32)
    bits = idx[:, 0] | (idx[:, 1] << 8) | (idx[:, 2] << 16) | (idx[:, 3] << 24)
    a, b = _rgb565(c0), _rgb565(c1)
    four = (c0 > c1)[:, None]
    p2 = np.where(four, (2 * a + b) // 3, (a + b) // 2)
    p3 = np.where(four, (a + 2 * b) // 3, 0)
    pal = np.stack([a, b, p2, p3], 1)                                  # (n, 4, 3)
    alpha = np.stack([np.full(len(c0), 255)] * 3 + [np.where(four[:, 0], 255, 0)], 1)
    sel = (bits[:, None] >> (2 * np.arange(16))) & 3                   # (n, 16)
    rgb = np.take_along_axis(pal, sel[..., None].repeat(3, -1).astype(np.int64), 1)
    al = np.take_along_axis(alpha, sel.astype(np.int64), 1)
    return np.concatenate([rgb, al[..., None]], -1).reshape(-1, 4, 4, 4).astype(np.uint8)


def bc4_decode(blocks):
    """blocks: (n, 8) uint8 -> (n, 4, 4) uint8."""
    a0, a1 = blocks[:, 0].astype(np.int32), blocks[:, 1].astype(np.int32)
    bits = np.zeros(len(blocks), np.uint64)
    for k in range(6):
        bits |= blocks[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
    eight = (a0 > a1)[:, None]
    i = np.arange(1, 7)
    p8 = ((7 - i) * a0[:, None] + i * a1[:, None]) // 7
    i6 = np.arange(1, 5)
    p6 = ((5 - i6) * a0[:, None] + i6 * a1[:, None]) // 5
    p6 = np.concatenate([p6, np.zeros((len(a0), 1), np.int32), np.full((len(a0), 1), 255)], 1)
    mids = np.where(eight, p8, p6)
    pal = np.concatenate([a0[:, None], a1[:, None], mids], 1)
    sel = ((bits[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))) & np.uint64(7)).astype(np.int64)
    return np.take_along_axis(pal, sel, 1).reshape(-1, 4, 4).astype(np.uint8)


def _to565(rgb):
    rgb = np.clip(rgb, 0, 255).astype(np.int32)
    return ((rgb[..., 0] >> 3) << 11) | ((rgb[..., 1] >> 2) << 5) | (rgb[..., 2] >> 3)


def bc1_encode(tiles):
    """tiles: (n, 4, 4, 4) RGBA uint8 -> (n, 8) uint8. Pixels with alpha < 128 become transparent
    (3-colour + transparent mode); fully opaque blocks use 4-colour mode. Endpoints: extremes along
    the block's principal colour axis."""
    n = len(tiles)
    px = tiles.reshape(n, 16, 4).astype(np.float32)
    rgb, opaque = px[..., :3], px[..., 3] >= 128
    w = opaque.astype(np.float32)[..., None]
    cnt = np.maximum(w.sum(1), 1)
    mean = (rgb * w).sum(1) / cnt
    d = (rgb - mean[:, None]) * w
    cov = np.einsum("nki,nkj->nij", d, d)
    axis = np.ones((n, 3), np.float32)
    for _ in range(8):  # power iteration
        axis = np.einsum("nij,nj->ni", cov, axis)
        axis /= np.linalg.norm(axis, axis=1, keepdims=True) + 1e-6
    proj = np.einsum("nki,ni->nk", rgb - mean[:, None], axis)
    lo = np.where(opaque, proj, np.inf).min(1)
    hi = np.where(opaque, proj, -np.inf).max(1)
    lo, hi = np.where(np.isfinite(lo), lo, 0), np.where(np.isfinite(hi), hi, 0)
    e0 = _to565(mean + axis * hi[:, None])
    e1 = _to565(mean + axis * lo[:, None])
    has_transp = (~opaque).any(1)
    # 4-colour mode needs c0 > c1, transparent mode needs c0 <= c1
    swap = np.where(has_transp, e0 > e1, e0 < e1)
    c0, c1 = np.where(swap, e1, e0), np.where(swap, e0, e1)
    same = (c0 == c1) & ~has_transp
    c1 = np.where(same & (c0 > 0), c0 - 1, c1)  # keep 4-colour mode valid for flat blocks
    c0 = np.where(same & (c0 == 0), 1, c0)
    a, b = _rgb565(c0).astype(np.float32), _rgb565(c1).astype(np.float32)
    four = (c0 > c1)[:, None, None]
    pal = np.where(four, np.stack([a, b, (2 * a + b) / 3, (a + 2 * b) / 3], 1),
                   np.stack([a, b, (a + b) / 2, np.full_like(a, 1e6)], 1))       # index 3 unusable for colour
    dist = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)                # (n, 16, 4)
    sel = dist.argmin(-1)
    sel = np.where(opaque, sel, 3)
    bits = (sel.astype(np.uint32) << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.zeros((n, 8), np.uint8)
    out[:, 0], out[:, 1] = c0 & 255, c0 >> 8
    out[:, 2], out[:, 3] = c1 & 255, c1 >> 8
    for k in range(4):
        out[:, 4 + k] = (bits >> (8 * k)) & 255
    return out


def bc4_encode(tiles):
    """tiles: (n, 4, 4) uint8 -> (n, 8) uint8 (8-value mode between the block's min and max)."""
    n = len(tiles)
    v = tiles.reshape(n, 16).astype(np.int32)
    a0, a1 = v.max(1), v.min(1)
    flat = a0 == a1
    a0 = np.where(flat & (a0 < 255), a0 + 1, a0)
    a1 = np.where(flat & (a0 == a1), a1 - 1, a1)
    i = np.arange(1, 7)
    pal = np.concatenate([a0[:, None], a1[:, None], ((7 - i) * a0[:, None] + i * a1[:, None]) // 7], 1)
    sel = np.abs(v[:, :, None] - pal[:, None, :]).argmin(-1).astype(np.uint64)
    bits = (sel << (np.uint64(3) * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.zeros((n, 8), np.uint8)
    out[:, 0], out[:, 1] = a0, a1
    for k in range(6):
        out[:, 2 + k] = ((bits >> np.uint64(8 * k)) & np.uint64(255)).astype(np.uint8)
    return out


# ----------------------------------------------------------------------------- file layout

class Frame:
    """One frame: canvas size + hotspot, and per layer the decoded image in canvas coordinates."""

    def __init__(self, w, h, hx, hy):
        self.w, self.h, self.hx, self.hy = w, h, hx, hy
        self.rgba = None      # (h, w, 4) main layer
        self.shadow = None    # (h, w) uint8 shadow strength
        self.player = None    # (h, w) uint8 player-colour mask
        self.damage = None    # (h, w, 4)
        self.raw = {}         # layer -> (box, flags, unk, cmds, blocks) as read


def _blocks_grid(box):
    x1, y1, x2, y2 = box
    return (x2 - x1) // 4, (y2 - y1) // 4


def read(path):
    data = open(path, "rb").read()
    assert data[:4] == b"SLDX", data[:4]
    version, n = struct.unpack_from("<HH", data, 4)
    pos = 16
    frames = []
    prev = {}
    for _ in range(n):
        w, h, hx, hy, mask, _u, idx = struct.unpack_from("<HHhhBBH", data, pos)
        pos += 12
        f = Frame(w, h, hx, hy)
        main_box = None
        for layer in LAYER_ORDER:
            if not mask & layer:
                continue
            (length,) = struct.unpack_from("<I", data, pos)
            start = pos
            p = pos + 4
            if layer in HAS_BOX:
                box = struct.unpack_from("<HHHH", data, p); p += 8
                if layer == MAIN:
                    main_box = box
            else:
                box = main_box
            flags, unk, ncmd = struct.unpack_from("<BBH", data, p); p += 4
            cmds = np.frombuffer(data, np.uint8, 2 * ncmd, p).reshape(-1, 2); p += 2 * ncmd
            nblocks = int(cmds[:, 1].sum())
            blocks = np.frombuffer(data, np.uint8, 8 * nblocks, p).reshape(-1, 8)
            f.raw[layer] = (box, flags, unk, cmds, blocks)
            pos = start + ((length + 3) & ~3)
            # decode into a block grid
            gw, gh = _blocks_grid(box)
            is_bc1 = layer in BC1_LAYERS
            dec = bc1_decode(blocks) if is_bc1 else bc4_decode(blocks)
            if flags & 0x80 and layer in prev and prev[layer].shape[:2] == (gh, gw):
                grid = prev[layer].copy()
            else:
                grid = np.zeros((gh, gw, 4, 4, 4) if is_bc1 else (gh, gw, 4, 4), np.uint8)
            k, b = 0, 0
            for skip, draw in cmds:
                k += int(skip)
                for _ in range(int(draw)):
                    grid[k // gw, k % gw] = dec[b]
                    k += 1; b += 1
            prev[layer] = grid
            img = grid.transpose(0, 2, 1, 3, 4).reshape(gh * 4, gw * 4, 4) if is_bc1 else grid.transpose(0, 2, 1, 3).reshape(gh * 4, gw * 4)
            canvas = np.zeros((h, w, 4) if is_bc1 else (h, w), np.uint8)
            x1, y1 = box[0], box[1]
            ch, cw = min(img.shape[0], h - y1), min(img.shape[1], w - x1)
            canvas[y1:y1 + ch, x1:x1 + cw] = img[:ch, :cw]
            if layer == MAIN: f.rgba = canvas
            elif layer == SHADOW: f.shadow = canvas
            elif layer == PLAYER: f.player = canvas
            elif layer == DAMAGE: f.damage = canvas
        frames.append(f)
    return frames


def _layer_bytes(box, grid_blocks, drawn, encoded, with_box, flags=0, unk=1):
    """grid_blocks: number of blocks in the box grid; drawn: bool mask (gh*gw) of blocks to store."""
    cmds = []
    k, n = 0, len(drawn)
    while k < n:
        skip = 0
        while k < n and not drawn[k] and skip < 255:
            skip += 1; k += 1
        draw = 0
        while k < n and drawn[k] and draw < 255:
            draw += 1; k += 1
        cmds.append((skip, draw))
    body = b""
    if with_box:
        body += struct.pack("<HHHH", *box)
    body += struct.pack("<BBH", flags, unk, len(cmds)) + bytes(np.array(cmds, np.uint8).flatten()) + encoded.tobytes()
    length = 4 + len(body)
    pad = (-length) % 4
    return struct.pack("<I", length) + body + b"\0" * pad


def _box(mask_img):
    ys, xs = np.nonzero(mask_img)
    if len(xs) == 0:
        return None
    x1, y1 = (xs.min() // 4) * 4, (ys.min() // 4) * 4
    x2, y2 = ((xs.max() + 4) // 4) * 4, ((ys.max() + 4) // 4) * 4
    return int(x1), int(y1), int(x2), int(y2)


def _tiles(img, box):
    x1, y1, x2, y2 = box
    sub = img[y1:y2, x1:x2]
    gh, gw = (y2 - y1) // 4, (x2 - x1) // 4
    if sub.ndim == 3:
        return sub.reshape(gh, 4, gw, 4, sub.shape[2]).transpose(0, 2, 1, 3, 4).reshape(gh * gw, 4, 4, sub.shape[2])
    return sub.reshape(gh, 4, gw, 4).transpose(0, 2, 1, 3).reshape(gh * gw, 4, 4)


def write(path, frames):
    """frames: list of dicts with 'rgba' (h, w, 4) uint8 on the canvas, 'hotspot' (x, y), optional
    'player' (h, w) uint8 player-colour mask (0-255) and 'shadow' (h, w) uint8. Canvas sizes must be
    multiples of 4."""
    out = [b"SLDX", struct.pack("<HHHHI", 4, len(frames), 0, 0x10, 0xFF)]
    for i, fr in enumerate(frames):
        rgba = fr["rgba"]
        h, w = rgba.shape[:2]
        if w % 4 or h % 4:
            raise ValueError(f"frame {i}: canvas {w}x{h} is not a multiple of 4 - pad it")
        hx, hy = fr["hotspot"]
        box = _box(rgba[..., 3] >= 128) or (0, 0, 4, 4)
        mask = MAIN | UNK4  # the stock files always carry the (empty) 0x04 layer
        shadow = fr.get("shadow")
        sbox = _box(shadow > 8) if shadow is not None else None
        if sbox: mask |= SHADOW
        player = fr.get("player")
        if player is not None and player.max() > 8: mask |= PLAYER
        out.append(struct.pack("<HHhhBBH", w, h, hx, hy, mask, 0, i))
        tiles = _tiles(rgba, box)
        drawn = (tiles[..., 3] >= 128).any((1, 2))
        out.append(_layer_bytes(box, len(tiles), drawn, bc1_encode(tiles[drawn]), True))
        if sbox:
            st = _tiles(shadow, sbox)
            sd = (st > 8).any((1, 2))
            out.append(_layer_bytes(sbox, len(st), sd, bc4_encode(st[sd]), True, flags=1))
        out.append(struct.pack("<IBBH", 8, 5, 0, 0))  # layer 0x04: flags 5, no blocks
        if mask & PLAYER:
            pt = _tiles(player, box)
            pd = (pt > 8).any((1, 2)) & drawn
            out.append(_layer_bytes(box, len(pt), pd, bc4_encode(pt[pd]), False, flags=1))
    open(path, "wb").write(b"".join(out))


# ----------------------------------------------------------------------------- command line

NAMES = {MAIN: "main", SHADOW: "shadow", UNK4: "0x04", DAMAGE: "damage", PLAYER: "player"}


def info(path):
    from collections import Counter
    data = open(path, "rb").read()
    version, n, _zero, f4 = struct.unpack_from("<HHHH", data, 4)
    frames = read(path)
    print(f"{path}: {len(data)} bytes, version {version}, {n} frames, header 0x{f4:02x} {data[12:16].hex()}")
    for (w, h, hx, hy), c in Counter((f.w, f.h, f.hx, f.hy) for f in frames).most_common(4):
        print(f"  canvas {w}x{h}, hotspot ({hx}, {hy}): {c} frames")
    if n > 1 and (n - 1) % 16 == 0:
        print(f"  = 16 angles x {(n - 1) // 16} frames + 1 trailing frame, like the stock unit files")
    count, blocks, delta = Counter(), Counter(), Counter()
    for f in frames:
        for layer, (box, flags, unk, cmds, blk) in f.raw.items():
            count[layer] += 1
            blocks[layer] += len(blk)
            delta[layer] += bool(flags & 0x80)
    for layer in LAYER_ORDER:
        if count[layer]:
            print(f"  layer {NAMES[layer]:6} in {count[layer]} frames, {blocks[layer]} blocks, "
                  f"{delta[layer]} frames reuse blocks of the previous one (flag 0x80)")


def roundtrip(path):
    """decode -> encode -> decode: how much this module's encoder loses on real game data."""
    import os
    import tempfile
    frames = read(path)
    src = []
    for f in frames:
        h4, w4 = -(-f.h // 4) * 4, -(-f.w // 4) * 4   # write() works in whole 4x4 blocks

        def pad(a):
            return None if a is None else np.pad(a, ((0, h4 - f.h), (0, w4 - f.w)) + ((0, 0),) * (a.ndim - 2))
        rgba = pad(f.rgba) if f.rgba is not None else np.zeros((h4, w4, 4), np.uint8)
        src.append(dict(rgba=rgba, hotspot=(f.hx, f.hy), player=pad(f.player), shadow=pad(f.shadow)))
    fd, tmp = tempfile.mkstemp(suffix=".sld")
    os.close(fd)
    try:
        write(tmp, src)
        size = os.path.getsize(tmp)
        again = read(tmp)
    finally:
        os.remove(tmp)
    err = {k: [0, 0] for k in ("rgb", "shadow", "player")}   # sum of abs differences, number of values
    alpha_bad = 0
    for a, b in zip(src, again):
        opaque = a["rgba"][..., 3] >= 128
        d = np.abs(a["rgba"][..., :3].astype(np.int32) - b.rgba[..., :3])[opaque]
        err["rgb"][0] += int(d.sum())
        err["rgb"][1] += d.size
        alpha_bad += int((opaque != (b.rgba[..., 3] >= 128)).sum())
        for k, mine, where in (("shadow", b.shadow, None), ("player", b.player, opaque)):
            if a[k] is None:
                continue
            mine = mine if mine is not None else np.zeros_like(a[k])
            m = where if where is not None else (a[k] > 0) | (mine > 0)   # shadow: where either has one
            err[k][0] += int(np.abs(a[k].astype(np.int32) - mine)[m].sum())
            err[k][1] += int(m.sum())
    print(f"roundtrip {path}: {len(frames)} frames, {os.path.getsize(path)} -> {size} bytes (no inter-frame reuse)")
    print(f"  main   RGB mean abs error {err['rgb'][0] / max(err['rgb'][1], 1):.2f}/255 over {err['rgb'][1] // 3} opaque pixels, "
          f"{alpha_bad} pixels changed opacity")
    for k in ("shadow", "player"):
        if err[k][1]:
            print(f"  {k:6} mean abs error {err[k][0] / err[k][1]:.2f}/255")
    if any(f.damage is not None for f in frames):
        print("  (the damage layer isn't written)")
    return err["rgb"][0] / max(err["rgb"][1], 1)


def preview(f, player_rgb=(45, 90, 230)):
    """A frame roughly as the game draws it for a blue player: shadow under the sprite, player areas tinted."""
    from PIL import Image
    im = Image.new("RGBA", (f.w, f.h))
    if f.shadow is not None:
        im.alpha_composite(Image.fromarray(np.dstack([np.zeros_like(f.shadow)] * 3 + [f.shadow])))
    if f.rgba is not None:
        rgba = f.rgba.copy()
        if f.player is not None:
            k = (f.player / 255.0)[..., None]
            rgb = rgba[..., :3].astype(np.float32)
            rgba[..., :3] = (rgb * (1 - k) + np.array(player_rgb) * (rgb.mean(-1, keepdims=True) / 128) * k).clip(0, 255).astype(np.uint8)
        im.alpha_composite(Image.fromarray(rgba))
    return im


def to_png(path, outdir, layers=False):
    from pathlib import Path
    from PIL import Image
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(path).stem
    frames = read(path)
    for i, f in enumerate(frames):
        preview(f).save(out / f"{stem}_{i:04d}.png")
        if layers:
            for name, img in (("main", f.rgba), ("shadow", f.shadow), ("player", f.player), ("damage", f.damage)):
                if img is not None:
                    Image.fromarray(img).save(out / f"{stem}_{i:04d}_{name}.png")
    print(f"wrote {len(frames)} frames to {out}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="header, canvas, hotspot and layers").add_argument("files", nargs="+")
    sub.add_parser("roundtrip", help="decode -> encode -> decode, print the mean abs error").add_argument("files", nargs="+")
    p = sub.add_parser("to-png", help="every frame as a PNG")
    p.add_argument("file")
    p.add_argument("outdir")
    p.add_argument("--layers", action="store_true", help="also each layer on its own (main, shadow, player, damage)")
    a = ap.parse_args()
    if a.cmd == "to-png":
        to_png(a.file, a.outdir, a.layers)
    else:
        for path in a.files:
            (info if a.cmd == "info" else roundtrip)(path)
