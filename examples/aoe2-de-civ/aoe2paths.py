"""Where things are: the AoE2 DE install, the player's profile folder, this example's build and art.

    game = find_game(args.game)           # ...\\steamapps\\common\\AoE2DE
    profile = find_profile(args.profile)  # %USERPROFILE%\\Games\\Age of Empires 2 DE\\<steam id>

An explicit path wins, then the AOE2DE_GAME / AOE2DE_PROFILE environment variables, then a search:
Steam libraries (libraryfolders.vdf) on Windows, from WSL (/mnt/c/...) and on Linux (Proton prefix).
Local mods live in <profile>\\mods\\local\\<ModName>, scenarios in <profile>\\resources\\_common\\scenario.
"""
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BUILD = HERE / "build"      # graphics/ (sprites in), <ModName>/ + ids.json (out)
ASSETS = HERE / "assets" / "gen"    # generated art: concepts, GLBs, icons, emblem, wonder
APPID = 813780                      # AoE2 DE on Steam
DAT = "resources/_common/dat/empires2_x2_p1.dat"


def is_wsl():
    return sys.platform == "linux" and "microsoft" in platform.release().lower()


def to_posix(p):
    """C:\\Users\\x -> /mnt/c/Users/x under WSL; anything else unchanged."""
    p = str(p).strip()
    if is_wsl() and re.match(r"^[A-Za-z]:[\\/]", p):
        return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    return p


def asset(name):
    """assets/gen/<name>.png|.jpg|.jpeg|.webp, the newest if there are several (models return JPEG or PNG
    depending on the model, so a regenerated file may come back with another extension)."""
    found = [p for ext in (".png", ".jpg", ".jpeg", ".webp") for p in [ASSETS / (name + ext)] if p.exists()]
    if not found:
        sys.exit(f"missing art: {ASSETS / name}.png/.jpg (assets/gen.sh makes it, or add your own)")
    return max(found, key=lambda p: p.stat().st_mtime)


# ----------------------------------------------------------------------------- the game


def steam_libraries():
    """Every Steam library folder: the default install plus the extra ones in libraryfolders.vdf."""
    home = Path.home()
    if os.name == "nt":
        roots = [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam", Path(r"C:\Program Files\Steam")]
    elif is_wsl():
        roots = [Path("/mnt/c/Program Files (x86)/Steam"), Path("/mnt/c/Program Files/Steam")]
    else:
        roots = []
    roots += [home / ".steam/steam", home / ".local/share/Steam", home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    libs = []
    for root in roots:
        if not (root / "steamapps").is_dir():
            continue
        libs.append(root)
        vdf = root / "steamapps/libraryfolders.vdf"
        if vdf.exists():
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace")):
                libs.append(Path(to_posix(m.group(1).replace("\\\\", "\\"))))
    return list(dict.fromkeys(libs))


def find_game(explicit=None):
    """The AoE2DE folder (the one with AoE2DE_s.exe and resources/)."""
    given = explicit or os.environ.get("AOE2DE_GAME")
    cands = [Path(to_posix(given))] if given else [lib / "steamapps/common/AoE2DE" for lib in steam_libraries()]
    for c in cands:
        if (c / DAT).exists():
            return c
        if (c.parent / DAT).exists():        # the resources folder was given
            return c.parent
    if given:
        sys.exit(f"not an AoE2 DE install (no {DAT}): {given}")
    sys.exit("AoE2 DE not found in the Steam libraries: pass --game <...\\steamapps\\common\\AoE2DE> or set AOE2DE_GAME")


# ----------------------------------------------------------------------------- the profile


def windows_home():
    """%USERPROFILE% as a path this Python can open (from WSL: ask cmd.exe, then map C:\\ to /mnt/c)."""
    if os.name == "nt":
        return Path(os.environ["USERPROFILE"])
    if not is_wsl():
        return None
    for exe in ("cmd.exe", "/mnt/c/Windows/System32/cmd.exe"):
        try:
            out = subprocess.run([exe, "/c", "echo %USERPROFILE%"], capture_output=True, text=True, timeout=30,
                                 cwd="/mnt/c").stdout.strip()   # cwd: cmd.exe can't start in a \\wsl$ folder
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out and "%" not in out:
            return Path(to_posix(out))
    return None


def find_profile(explicit=None):
    """<USERPROFILE>/Games/Age of Empires 2 DE/<steam id>: the game keeps one folder per signed-in account."""
    given = explicit or os.environ.get("AOE2DE_PROFILE")
    if given:
        p = Path(to_posix(given))
        if not p.is_dir():
            sys.exit(f"profile folder not found: {given}")
        return p
    homes = [windows_home()] + [lib / f"steamapps/compatdata/{APPID}/pfx/drive_c/users/steamuser" for lib in steam_libraries()]
    found = []
    for home in filter(None, homes):
        base = home / "Games" / "Age of Empires 2 DE"
        if base.is_dir():
            found += [d for d in sorted(base.iterdir()) if d.is_dir() and d.name.isdigit()]
    # the game also keeps a "0" folder next to the account's: a real account id wins over it
    real = [d for d in found if d.name != "0"] or found
    if len(real) == 1:
        return real[0]
    if not real:
        sys.exit("no AoE2 DE profile found (start the game once), or pass --profile / set AOE2DE_PROFILE")
    sys.exit("several AoE2 DE profiles - pass --profile (or set AOE2DE_PROFILE) to one of:\n  " + "\n  ".join(map(str, real)))
