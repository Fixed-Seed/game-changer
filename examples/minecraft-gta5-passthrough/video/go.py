"""After the one-time Rockstar sign-in: get GTA into free roam with the passthrough attached.

    python go.py wait            # wait for GTA + the plugin's link (prints the player's position)
    python go.py save            # new profile in the prologue: install a save and restart GTA so it loads it
    python go.py scout [x y z]   # screenshots all round a spot, or where the player stands (director.py scout)

From WSL. `save` copies SGTA50000 and SGTA50015 from GTA_SAVE_DIR (default <PASSTHROUGH_WIN_DIR>\\gta_save; bring
your own, e.g. a 100% save) into each GTA V profile folder, keeping what was there as SGTA50000.bak etc. first.
Kills only GTA5.exe by its exact PID; relaunches through Steam. It never clicks: pick Story Mode yourself.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import record  # noqa: E402

DIRECTOR = record.win(record.HERE / "director.py")
SAVE = Path(record.wsl(os.environ.get("GTA_SAVE_DIR", record.WIN_DIR + r"\gta_save")))
GTA_APPID = 271590  # GTA V Legacy on Steam


def state(timeout=6):
    """The plugin's latest gtastate (via the director's 'op state'), or None if GTA's script isn't linked."""
    out = subprocess.run([record.PY_WIN, DIRECTOR, "op", "state"], capture_output=True, text=True, timeout=60, env=record.win_env()).stdout
    for line in out.splitlines():
        if line.startswith("{") and "gtastate" in line:
            return json.loads(line)
    return None


def wait(minutes=30):
    t = time.time()
    while time.time() - t < minutes * 60:
        pid = record.pid_of("GTA5")
        if pid:
            s = state()
            if s:
                print("linked:", pid, s.get("pos"))
                return pid, s
        time.sleep(10)
    return None, None


def in_prologue(s):
    return s is not None and s["pos"][1] < -4000  # North Yankton is far south of Los Santos


def profiles():
    """<Documents>\\Rockstar Games\\GTA V\\Profiles\\*, one folder per Rockstar account (Documents may be OneDrive's)."""
    docs = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "[Environment]::GetFolderPath('MyDocuments')"],
                          capture_output=True, text=True, timeout=30).stdout.strip()
    return [p for p in glob.glob(record.wsl(docs) + "/Rockstar Games/GTA V/Profiles/*") if Path(p).is_dir()]


def install_save():
    found = profiles()
    assert found, "no GTA profile folder yet (the game creates it on first start)"
    for prof in found:
        for f in ("SGTA50000", "SGTA50015"):
            dst, bak = Path(prof) / f, Path(prof) / (f + ".bak")
            if dst.exists() and not bak.exists():  # the first backup is the player's own save: never overwrite it
                shutil.copy2(dst, bak)
            shutil.copy2(SAVE / f, dst)
        print("save installed in", prof)


def restart():
    pid = record.pid_of("GTA5")
    if pid:
        subprocess.run(["taskkill.exe", "/PID", str(pid), "/F"], capture_output=True)
        time.sleep(8)
    subprocess.run(["cmd.exe", "/c", "start", "", f"steam://rungameid/{GTA_APPID}"], cwd="/mnt/c/", capture_output=True)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "wait"
    if what == "wait":
        print(wait())
    elif what == "save":
        install_save()
        restart()
        print(wait())
    elif what == "scout":
        subprocess.run([record.PY_WIN, DIRECTOR, "scout"] + sys.argv[2:], timeout=300, env=record.win_env())
