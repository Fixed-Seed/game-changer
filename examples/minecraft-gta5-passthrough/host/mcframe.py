"""Reader for the frames Minecraft publishes in the shared memory "Local\\MCPassthroughFrame" (Windows only).

Layout: see mc/src/client/java/com/fixedseed/passthrough/client/FrameExporter.java.

    reader = MCFrames()
    f = reader.latest()          # None until Minecraft has published a frame
    f.world_rgba, f.world_depth_m, f.overlay_rgba   # top-down numpy arrays, premultiplied RGBA uint8 / metres
"""
import mmap
import struct
from dataclasses import dataclass

import numpy as np

NAME = "Local\\MCPassthroughFrame"
MAGIC = 0x5450434D
HEADER = 4096
SLOT_DESC = 256
SLOT_DESC_BYTES = 128


@dataclass
class Frame:
    slot: int
    mc_frame: int
    host_frame: int
    width: int
    height: int
    near: float
    far: float
    fov: float
    flags: int
    cam: tuple
    rot: tuple
    first_person: bool
    capture_ns: int
    publish_ns: int
    world_rgba: np.ndarray      # (h, w, 4) uint8, premultiplied, top row first
    world_depth: np.ndarray     # (h, w) float32 raw depth-buffer values, top row first
    overlay_rgba: np.ndarray    # (h, w, 4) uint8, premultiplied, top row first

    @property
    def world_depth_m(self):
        """View-space depth (metres along the view axis); inf where Minecraft drew nothing."""
        d = self.world_depth.astype(np.float64)
        n, f = self.near, self.far
        if self.flags & 4:  # reversed Z: 1 = near, 0 = far
            if self.flags & 1:  # [0, 1] depth range
                z = n * f / (n + d * (f - n))
            else:                # [-1, 1] NDC range mapped to [0, 1] window depth
                ndc = 2.0 * d - 1.0
                z = 2.0 * n * f / ((f + n) + ndc * (f - n))
            z[d <= 0.0] = np.inf
        else:
            if self.flags & 1:
                z = n * f / (f - d * (f - n))
            else:
                ndc = 2.0 * d - 1.0
                z = 2.0 * n * f / ((f + n) - ndc * (f - n))
            z[d >= 1.0] = np.inf
        return z


class MCFrames:
    def __init__(self):
        probe = mmap.mmap(-1, HEADER, tagname=NAME, access=mmap.ACCESS_READ)
        magic, version, header, slots, stride, maxw, maxh = struct.unpack_from("<iiiiqii", probe, 0)
        probe.close()
        if magic != MAGIC:
            raise RuntimeError("no Minecraft frame export (is the passthrough mod running with a host attached?)")
        self.slots, self.stride = slots, stride
        self.mm = mmap.mmap(-1, header + stride * slots, tagname=NAME, access=mmap.ACCESS_READ)
        self.header = header

    def published(self):
        return struct.unpack_from("<q", self.mm, 32)[0]

    def latest(self, copy=True):
        """The most recently completed frame, or None. Retries if Minecraft overwrote it mid-read."""
        for _ in range(4):
            slot = struct.unpack_from("<i", self.mm, 40)[0]
            if slot < 0:
                return None
            d = SLOT_DESC + SLOT_DESC_BYTES * slot
            seq = struct.unpack_from("<q", self.mm, d)[0]
            if seq & 1:
                continue
            (mc_frame, host_frame, w, h, near, far, fov, flags, cx, cy, cz, yaw, pitch, roll, fp,
             cap, pub) = struct.unpack_from("<qqiifffidddfffiqq", self.mm, d + 8)
            n = w * h * 4
            base = self.header + self.stride * slot
            buf = memoryview(self.mm)[base:base + 3 * n]
            world = np.frombuffer(buf, np.uint8, n, 0).reshape(h, w, 4)[::-1]
            depth = np.frombuffer(buf, np.float32, w * h, n).reshape(h, w)[::-1]
            over = np.frombuffer(buf, np.uint8, n, 2 * n).reshape(h, w, 4)[::-1]
            if copy:
                world, depth, over = world.copy(), depth.copy(), over.copy()
            if struct.unpack_from("<q", self.mm, d)[0] != seq:
                continue
            if not flags & 2:  # rows already top-down
                world, depth, over = world[::-1], depth[::-1], over[::-1]
            return Frame(slot, mc_frame, host_frame, w, h, near, far, fov, flags, (cx, cy, cz), (yaw, pitch, roll),
                         bool(fp), cap, pub, world, depth, over)
        return None
