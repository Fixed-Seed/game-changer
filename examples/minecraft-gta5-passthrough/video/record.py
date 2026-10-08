"""Record the passthrough demo from WSL: the GTA V window (ffmpeg gfxcapture, this window's GPU frames only) plus the
audio of GTA and of Minecraft, each from its own process (WASAPI process loopback: the repo's game_changer/ps1/ProcLoopback).

    rec = Recorder(TAKES + r"\\take1", {"gta": gta_pid, "mc": mc_pid}); rec.start(); ...; rec.stop()

post() cuts a take: trim, one-line titles, both audio tracks mixed, fade out, 1080p H.264 (with a Linux ffmpeg).
Capturing needs a Windows ffmpeg with gfxcapture: `fsgc win setup` fetches one (or set FSGC_FFMPEG_WIN).
PASSTHROUGH_WIN_DIR  the Windows working folder (default C:\\dev\\passthrough): takes go to its takes\\
PASSTHROUGH_PY       the Windows Python the director runs with (default <PASSTHROUGH_WIN_DIR>\\pyenv\\Scripts\\python.exe)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]   # game-changer: its game_changer.win finds the capture tools
sys.path.append(str(REPO))
WIN_DIR = os.environ.get("PASSTHROUGH_WIN_DIR", r"C:\dev\passthrough")
TAKES = WIN_DIR + r"\takes"
FFMPEG_STARTUP = 0.3   # spawn + gfxcapture + NVENC init before the first frame (WSL-launched)


def wsl(p):
    """C:\\x\\y -> /mnt/c/x/y (on Windows itself, and for anything else, p as it is)."""
    return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/") if p[1:2] == ":" and os.name != "nt" else p


PY_WIN = wsl(os.environ.get("PASSTHROUGH_PY", WIN_DIR + r"\pyenv\Scripts\python.exe"))


def win(p):
    """A path Windows programs can open: C:\\... as it is, anything else through wslpath (\\\\wsl.localhost\\... too)."""
    p = str(p)
    return p if p[1:2] == ":" else subprocess.run(["wslpath", "-w", str(Path(p).resolve())], capture_output=True, text=True).stdout.strip()


def win_env():
    """This environment for a Windows program, passing PASSTHROUGH_WIN_DIR and FSGC_FFMPEG_WIN on (WSLENV)."""
    names = [os.environ.get("WSLENV", "")] + [n for n in ("PASSTHROUGH_WIN_DIR", "FSGC_FFMPEG_WIN") if n in os.environ]
    return dict(os.environ, WSLENV=":".join(filter(None, names)))


def pid_of(name):
    """PID of a running process by image name (e.g. GTA5), or None."""
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"(Get-Process {name} -ErrorAction SilentlyContinue | Select-Object -First 1).Id"],
                         capture_output=True, text=True, timeout=30).stdout.strip()
    return int(out) if out.isdigit() else None


def minecraft_pid():
    """The Minecraft client's java.exe (the one running Fabric's Knot launcher)."""
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                          "(Get-CimInstance Win32_Process -Filter \"Name='java.exe' or Name='javaw.exe'\" | "
                          "Where-Object { $_.CommandLine -match 'fabric.dli.env=client|KnotClient|fabric-loader' } | Select-Object -First 1).ProcessId"],
                         capture_output=True, text=True, timeout=30).stdout.strip()
    return int(out) if out.isdigit() else None


class Recorder:
    def __init__(self, base_win, audio_pids, window_exe="GTA5.exe", fps=60):
        self.base = base_win                # e.g. <TAKES>\take1  (-> .mkv, .<name>.raw, .json)
        self.audio_pids = audio_pids        # {"gta": pid, "mc": pid}
        self.window_exe = window_exe
        self.fps = fps

    def start(self):
        from game_changer.win import ffmpeg_win, tool_path  # the repo's toolkit: gfxcapture ffmpeg, ProcLoopback.ps1 on a Windows path
        Path(wsl(self.base)).parent.mkdir(parents=True, exist_ok=True)
        loopback = tool_path("ProcLoopback.ps1")
        self.audio = {}
        for name, pid in self.audio_pids.items():
            p = subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", loopback, "-TargetPid", str(pid),
                                  "-Out", f"{self.base}.{name}.raw"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd="/mnt/c")
            header = json.loads(p.stdout.readline())
            self.audio[name] = (p, header, time.time())
        self.t_video = time.time()
        self.video = subprocess.Popen([ffmpeg_win(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                                       f"gfxcapture=window_exe={self.window_exe}:max_framerate={self.fps}:capture_cursor=0,hwdownload,format=bgra",
                                       "-vf", f"fps={self.fps}", "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "18", "-pix_fmt", "yuv420p",
                                       "-flush_packets", "1", self.base + ".mkv"], stdin=subprocess.PIPE)

    def stop(self):
        self.video.stdin.write(b"q")
        self.video.stdin.flush()
        self.video.wait(30)
        meta = {"audio": {}}
        for name, (p, header, t) in self.audio.items():
            try:
                p.stdin.write("\n")
                p.stdin.flush()
                p.wait(10)
            except (BrokenPipeError, OSError):
                pass  # its process went away first (the game closed): what it wrote is kept
            meta["audio"][name] = dict(header, offset_s=round(self.t_video - t + FFMPEG_STARTUP, 3))
        Path(wsl(self.base) + ".json").write_text(json.dumps(meta))
        return meta


def duration(path):
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-", "-progress", "-"], capture_output=True, text=True).stdout
    import re
    return float(re.findall(r"out_time_us=(\d+)", out)[-1]) / 1e6


def post(base_win, out, head, length, titles=(), volumes=None, fade=0.8, scratch=None):
    """titles: [(t0, t1, text)] in seconds of the output. volumes: {"gta": 1.0, "mc": 1.2}."""
    import titles as T
    mkv = wsl(base_win) + ".mkv"
    meta = json.load(open(wsl(base_win) + ".json"))
    scratch = scratch or tempfile.mkdtemp(prefix="passthrough_titles_")
    Path(scratch).mkdir(parents=True, exist_ok=True)
    inputs = ["-ss", f"{head:.3f}", "-i", mkv]
    names = list(meta["audio"])
    for name in names:
        inputs += ["-f", "f32le", "-ar", "48000", "-ac", "2", "-ss", f"{head + meta['audio'][name]['offset_s']:.3f}", "-i", wsl(base_win) + f".{name}.raw"]
    filt = "[0:v]scale=1920:1080:flags=lanczos,setsar=1[v0]"
    last = "v0"
    for k, (t0, t1, text) in enumerate(titles):
        png = T.title_png(text, f"{scratch}/title{k}.png")
        inputs += ["-loop", "1", "-t", f"{length:.3f}", "-i", png]
        idx = 1 + len(names) + k
        filt += f";[{last}][{idx}:v]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[v{k + 1}]"
        last = f"v{k + 1}"
    filt += f";[{last}]fade=t=out:st={length - fade:.3f}:d={fade}[v]"
    vols = volumes or {}
    mix = "".join(f"[{1 + i}:a]volume={vols.get(n, 1.0)}[a{i}];" for i, n in enumerate(names))
    mix += "".join(f"[a{i}]" for i in range(len(names))) + f"amix=inputs={len(names)}:normalize=0,alimiter=limit=0.95,afade=t=in:d=0.2,afade=t=out:st={length - fade:.3f}:d={fade}[a]"
    filt += ";" + mix
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[v]", "-map", "[a]",
                    "-t", f"{length:.3f}", "-r", "60", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True)
    print(f"wrote {out} ({length:.1f}s)")
