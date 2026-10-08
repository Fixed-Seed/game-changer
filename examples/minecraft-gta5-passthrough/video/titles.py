"""One-line titles in Minecraft's own pixel font (its ascii.png glyph sheet), white with Minecraft's drop shadow.

The glyph sheet is Mojang's, so it isn't in this repo: it's read from your Minecraft client jar
(assets/minecraft/textures/font/ascii.png). MC_CLIENT_JAR names one; otherwise it's the jar Loom cached when
mc/ was built (in GRADLE_USER_HOME, ~/.gradle, or <PASSTHROUGH_WIN_DIR>\\gradle-home for gradle.sh builds).

    python titles.py "Minecraft x GTA V" title.png
"""
import io
import os
import sys
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from record import WIN_DIR, wsl  # noqa: E402

SHEET = "assets/minecraft/textures/font/ascii.png"


def client_jar():
    """$MC_CLIENT_JAR, or the newest Minecraft client jar in a Loom cache."""
    if os.environ.get("MC_CLIENT_JAR"):
        return Path(wsl(os.environ["MC_CLIENT_JAR"]))
    homes = [os.environ.get("GRADLE_USER_HOME"), Path.home() / ".gradle", wsl(WIN_DIR + r"\gradle-home")]
    jars = [j for h in homes if h for j in Path(h).glob("caches/fabric-loom/*/minecraft-client.jar")]
    if not jars:
        sys.exit("no Minecraft client jar for the title font: build mc/ once (Loom caches it) or set MC_CLIENT_JAR")
    return max(jars, key=lambda j: j.stat().st_mtime)


def _glyphs():
    with zipfile.ZipFile(client_jar()) as jar:
        sheet = Image.open(io.BytesIO(jar.read(SHEET))).convert("RGBA")
    cell = sheet.width // 16
    glyphs = {}
    for code in range(32, 127):
        g = sheet.crop(((code % 16) * cell, (code // 16) * cell, (code % 16 + 1) * cell, (code // 16 + 1) * cell))
        alpha = g.getchannel("A")
        cols = [x for x in range(cell) if any(alpha.getpixel((x, y)) > 0 for y in range(cell))]
        width = (max(cols) + 1) if cols else cell // 2   # Minecraft: rightmost filled column + 1, space = 4 of 8
        glyphs[chr(code)] = (g, width)
    return glyphs, cell


def title_png(text, path, scale=6, y_frac=0.80, size=(1920, 1080)):
    glyphs, cell = _glyphs()
    widths = [glyphs.get(c, glyphs["?"])[1] + 1 for c in text]
    w = sum(widths) * scale
    img = Image.new("RGBA", size)
    x0 = (size[0] - w) // 2
    y0 = int(size[1] * y_frac) - cell * scale // 2
    for shadow in (True, False):
        x = x0
        for c, adv in zip(text, widths):
            g, _ = glyphs.get(c, glyphs["?"])
            g = g.resize((cell * scale, cell * scale), Image.NEAREST)
            if shadow:  # Minecraft's shadow: the glyph at 25% brightness, one pixel down-right
                r, gg, b, a = g.split()
                dark = Image.merge("RGBA", (r.point(lambda v: v // 4), gg.point(lambda v: v // 4), b.point(lambda v: v // 4), a))
                img.alpha_composite(dark, (x + scale, y0 + scale))
            else:
                img.alpha_composite(g, (x, y0))
            x += adv * scale
    img.save(path)
    return path


if __name__ == "__main__":
    title_png(sys.argv[1] if len(sys.argv) > 1 else "Minecraft x GTA V", sys.argv[2] if len(sys.argv) > 2 else "title.png")
