"""One take: start recording, run the director's sequence, stop, and write the take's event log.

    python take.py <take name> <director config> [window exe]

From WSL. The director (director.py next to this) runs with Windows Python (PASSTHROUGH_PY); the take goes to
<PASSTHROUGH_WIN_DIR>\\takes\\<take name>.mkv, .gta.raw, .mc.raw, .json and .events.json.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import record  # noqa: E402


def take(name, cfg, window_exe="GTA5.exe"):
    pids = {"mc": record.minecraft_pid()}
    game = record.pid_of(window_exe.rsplit(".", 1)[0])
    if window_exe.lower() == "gta5.exe" and game:
        pids["gta"] = game
    assert pids["mc"], "Minecraft isn't running"
    base = record.TAKES + "\\" + name
    rec = record.Recorder(base, pids, window_exe=window_exe)
    rec.start()
    t_rec = time.time()
    time.sleep(1.0)
    out = subprocess.run([record.PY_WIN, record.win(record.HERE / "director.py"), "shoot", record.win(cfg)],
                         capture_output=True, text=True, timeout=300, env=record.win_env())
    t_dir = time.time()
    time.sleep(0.5)
    meta = rec.stop()
    events = json.loads(out.stdout.strip().splitlines()[-1])["events"] if out.returncode == 0 else []
    if out.returncode != 0:
        print(out.stdout[-2000:], out.stderr[-2000:])
    # director times are from its own start; put them on the recording's clock
    start_offset = (t_dir - t_rec) - (events[-1][0] if events else 0)
    log = {"events": [[round(t + start_offset, 3), n] for t, n in events], "meta": meta}
    Path(record.wsl(base) + ".events.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log["events"]))
    return log


if __name__ == "__main__":
    take(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "GTA5.exe")
