"""Render a GLB into sprite frames from a game's camera. Runs inside Blender:

    blender -b --python render_sprites.py -- config.json

(`fsgc render3d` writes the config and calls this.) The model is normalised so its longest horizontal
side is `length_px` pixels at 1x and its ground point sits at the canvas centre (the hotspot), or at
`ground_y` px from the top if given. For each heading and animation frame it renders the model on a
transparent background, plus (optionally) a shadow pass: the shadow it casts onto a shadow-catcher
ground with the model itself invisible - engines like AoE2 keep shadows in their own layer.

Config keys: glb, out_dir, canvas [w, h] or n, length_px, forward_yaw_deg (rotation that points the
model's nose along +X), camera {type: ortho|persp, elevation_deg, headings, start_deg, clockwise,
fov_deg, distance}, light {sun, sun_elev_deg, sun_azim_deg, ambient}, samples, engine (CYCLES|EEVEE),
shadows (bool), anims {name: {frames, motion: {kind: bob|lunge|die|wreck|spin, ...}}}.
"""
import json
import math
import sys

import bpy
from mathutils import Euler, Vector

cfg = json.load(open(sys.argv[sys.argv.index("--") + 1]))
canvas = cfg.get("canvas", 200)
CW, CH = (canvas, canvas) if isinstance(canvas, int) else canvas
cam_cfg = cfg.get("camera", {})
light = cfg.get("light", {})

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---- model: centre on its ground point, longest horizontal side = length_px units (1 unit = 1 px at 1x)
bpy.ops.import_scene.gltf(filepath=cfg["glb"])
parts = [o for o in scene.objects if o.type == "MESH"]
root = bpy.data.objects.new("unit", None)
scene.collection.objects.link(root)
for o in list(scene.objects):
    if o.parent is None and o is not root:
        o.parent = root
bpy.context.view_layer.update()
pts = [o.matrix_world @ Vector(c) for o in parts for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
size = max(hi.x - lo.x, hi.y - lo.y) if cfg.get("measure", "length") == "length" else (hi.z - lo.z)
s = cfg["length_px"] / max(size, 1e-6)
pivot = bpy.data.objects.new("pivot", None)          # heading + animation transform
scene.collection.objects.link(pivot)
fwd = bpy.data.objects.new("fwd", None)              # points the model's nose along +X
scene.collection.objects.link(fwd)
fwd.parent = pivot
root.parent = fwd
root.scale = (s, s, s)
root.location = (-(lo.x + hi.x) / 2 * s, -(lo.y + hi.y) / 2 * s, -lo.z * s)
fwd.rotation_euler = Euler((0, 0, math.radians(cfg.get("forward_yaw_deg", 0))))
height = (hi.z - lo.z) * s

# ---- ground (shadow catcher), camera, light
bpy.ops.mesh.primitive_plane_add(size=8000)
ground = bpy.context.active_object
ground.is_shadow_catcher = True

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
elev = math.radians(cam_cfg.get("elevation_deg", 30))
dist = cam_cfg.get("distance", 2000)
if cam_cfg.get("type", "ortho") == "ortho":
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(CW, CH)               # 1 blender unit = 1 px across the canvas
else:
    # perspective (turntables, promo shots): frame the model and aim at its middle
    cam.data.type = "PERSP"
    fov = math.radians(cam_cfg.get("fov_deg", 35))
    cam.data.angle = fov
    dist = cam_cfg.get("distance") or max(cfg["length_px"], height) * cam_cfg.get("margin", 1.3) / (2 * math.tan(fov / 2))
cam.location = (0, -dist * math.cos(elev), dist * math.sin(elev))
cam.rotation_euler = Euler((math.pi / 2 - elev, 0, 0))
cam.data.clip_end = dist * 10
if cam.data.type == "PERSP":
    target = bpy.data.objects.new("target", None)
    scene.collection.objects.link(target)
    target.location = (0, 0, height / 2)
    cam.location.z += height / 2
    track = cam.constraints.new("TRACK_TO")
    track.target, track.track_axis, track.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
# ground point offset: shift the camera so the hotspot lands at ground_y (px from top) instead of the centre
if "ground_y" in cfg and cam.data.type == "ORTHO":
    cam.data.shift_y = (cfg["ground_y"] - CH / 2) / max(CW, CH)

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
scene.collection.objects.link(sun)
sun.data.energy = light.get("sun", 4.0)
sun.data.angle = math.radians(light.get("softness_deg", 8))
sun.rotation_euler = Euler((math.radians(90 - light.get("sun_elev_deg", 40)), 0, math.radians(light.get("sun_azim_deg", 40))))
world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = light.get("ambient", 0.9)

engine = cfg.get("engine", "CYCLES").upper()
if engine == "EEVEE":
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):   # the id changed between Blender 4.2 and 5.x
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
else:
    scene.render.engine = "CYCLES"
    scene.cycles.samples = cfg.get("samples", 48)
    scene.cycles.use_denoising = True
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = dev
            prefs.get_devices()
            if any(d.type == dev for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == dev
                scene.cycles.device = "GPU"
                break
        except TypeError:
            continue
scene.render.resolution_x, scene.render.resolution_y = CW, CH
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"


def set_visibility(unit_visible):
    for o in parts:
        o.visible_camera = unit_visible
    ground.hide_render = unit_visible  # shadow pass: ground + invisible (but shadow-casting) model


def pose(motion, t, heading):
    """Per-animation transform for t in [0, 1)."""
    m = motion or {}
    kind = m.get("kind")
    loc = Vector((0, 0, m.get("hover", 0)))
    rot = [0.0, 0.0, heading]
    if kind == "bob":
        loc.z += m.get("amp", 1.5) * math.sin(2 * math.pi * t * m.get("cycles", 1))
        rot[1] += math.radians(m.get("pitch", 0)) * math.sin(2 * math.pi * t * m.get("cycles", 1) + 1)
    elif kind == "lunge":
        u = math.sin(math.pi * t) ** 2
        loc += Vector((math.cos(heading), math.sin(heading), 0)) * m.get("dist", 12) * u
        rot[1] += math.radians(m.get("pitch", -4)) * u
        loc.z += m.get("hop", 0) * u
    elif kind == "die":
        u = min(1.0, t * m.get("speed", 1.4))
        rot[0] += math.radians(m.get("roll", 70)) * u
        loc.z -= m.get("hover", 0) * u + m.get("sink", 2) * u
    elif kind == "wreck":
        rot[0] += math.radians(m.get("roll", 70))
        loc.z = -m.get("sink", 2)
    elif kind == "spin":
        rot[2] += 2 * math.pi * t * m.get("turns", 1)
    return loc, rot


out = cfg["out_dir"]
headings = cam_cfg.get("headings", 16)
start = math.radians(cam_cfg.get("start_deg", 0))
sign = -1 if cam_cfg.get("clockwise", True) else 1
n_done = 0
for name, anim in cfg.get("anims", {"idle": {"frames": 1}}).items():
    n = anim.get("frames", 1)
    for k in range(headings):
        heading = start + sign * 2 * math.pi * k / headings
        for f in range(n):
            loc, rot = pose(anim.get("motion"), f / n, heading)
            pivot.location = loc
            pivot.rotation_euler = Euler(rot)
            for shadow in (False, True):
                if shadow and not cfg.get("shadows", False):
                    continue
                set_visibility(not shadow)
                scene.render.filepath = f"{out}/{name}_{k:02d}_{f:03d}{'_s' if shadow else ''}.png"
                bpy.ops.render.render(write_still=True)
                n_done += 1
print(f"FSGC_RENDER_DONE {n_done} images -> {out}")
