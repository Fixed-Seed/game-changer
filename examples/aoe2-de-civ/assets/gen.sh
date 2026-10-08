#!/usr/bin/env bash
# The San Franciscans' art, regenerated with the repo's FixedSeed CLI (needs FIXEDSEED_KEY). The files in gen/
# are the ones the mod shipped with; a rerun makes new, different art (and spends FixedSeed API balance).
#
#   assets/gen.sh concepts     # unit concept art (FLUX.1 [dev]), only the input to image-to-3D
#   assets/gen.sh meshes       # concept -> textured GLB (Hunyuan3D 3.1)
#   assets/gen.sh images       # 2D art: wonder, emblem, unit portraits
#   assets/gen.sh all
#
# Units are rendered from 3D so every one of AoE2's 16 facing angles is consistent; the concept
# images are only the input to image-to-3D. Accents meant to take the player's colour are asked for
# in saturated blue and masked by hue when the sprites are packed (make_sprites.py).
#
# The shipped art came from FLUX.1 [dev] (40 steps, guidance 4; JPEG output) and TRELLIS (texture 2048,
# mesh simplify 0.9). `fsgc fixedseed run black-forest-labs/flux-1-dev` repeats those FLUX settings
# (`fsgc fixedseed image` targets a newer default model). Meshes are made with Hunyuan3D 3.1 (tencent/hunyuan3d-3.1),
# so a new mesh may face another way or have other proportions: check the preview sheet after
# `make_sprites.py all <unit>` and adjust render.forward_yaw / length in civ.py.
set -euo pipefail
cd "$(dirname "$0")"
FSGC=${FSGC:-$(command -v fsgc || echo ../../../bin/fsgc)}
OUT=gen

flux() {  # name aspect_ratio prompt
  "$FSGC" fixedseed run black-forest-labs/flux-1-dev prompt="$3" aspect_ratio="$2" num_inference_steps:=40 guidance:=4 --out "$OUT" --name "$1"
}

CONCEPT_STYLE="clean studio product render, three-quarter front view from slightly above, soft even lighting, whole object in frame, isolated on a plain white background, no text, no logos"
# 2D art: the wonder is a single frame, so it can be painted directly in AoE2's projection
AOE_STYLE="in the style of Age of Empires II Definitive Edition building sprites: detailed pre-rendered 3D, warm sunlight from the upper left, isometric three-quarter view from above at 30 degrees, on a plain white background, no text"

concepts() {
  flux robotaxi_concept 1:1 "a white compact electric SUV robotaxi, a black spinning lidar sensor dome on the roof, small black sensor pods on the front fenders and mirrors, tinted windows, bright saturated blue accent stripes along the sides and blue wheel rims. $CONCEPT_STYLE"
  flux drone_concept 1:1 "a white quadcopter delivery drone with four rotors on arms, carrying a small brown cardboard parcel underneath, bright saturated blue accent panels on the body and the rotor guards. $CONCEPT_STYLE"
}

meshes() {
  for name in robotaxi drone; do
    concept=$(ls -t "$OUT/${name}_concept".* | head -1)
    "$FSGC" fixedseed model3d "$concept" --faces 50000 --out "$OUT" --name "$name"
    glb=$(ls -t "$OUT/$name"*.glb | head -1)   # the result can hold more files; civ.py wants gen/<name>.glb
    [ "$glb" = "$OUT/$name.glb" ] || mv "$glb" "$OUT/$name.glb"
  done
}

images() {
  flux wonder 3:4 "the Transamerica Pyramid skyscraper in San Francisco as a game wonder building: a tall white four-sided pyramid tower with narrow vertical windows and two wings near the top, standing on a square grey stone plaza with small palm trees and bright blue banners at the corners, $AOE_STYLE"
  flux emblem 1:1 "a heraldic civilization emblem for a game: the Golden Gate Bridge's red-orange tower over blue bay waves on a round golden-bordered shield, flat painted game icon, centered, plain white background, no text"
  flux icon_robotaxi 1:1 "a square game unit portrait icon in the painted style of Age of Empires II: a modern white electric self-driving robotaxi crossover with a black lidar sensor dome on its roof and blue trim, three-quarter front view, parked on a medieval cobblestone street between timber houses, dramatic warm lighting, detailed oil painting, no text, no logos"
  flux icon_drone 1:1 "a square game unit portrait icon in the painted style of Age of Empires II: a white quadcopter delivery drone carrying a parcel over a medieval town at dusk, dramatic lighting, detailed painting, no text"
}

case "${1:-}" in
  concepts) concepts ;;
  meshes) meshes ;;
  images) images ;;
  all) concepts; meshes; images ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
