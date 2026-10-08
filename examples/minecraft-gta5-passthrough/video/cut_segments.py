"""Hard-cut segments of one take into a video: python cut_segments.py <take> <out> "a0-a1,b0-b1,..." [titles json]
titles json: [[t0, t1, "text"], ...] in seconds of the output."""
import json, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import record, titles as T

def cut(take, out, segments, title_list, fade=0.8, volumes=None):
    base = record.TAKES + "\\" + take
    scratch = tempfile.mkdtemp(prefix="passthrough_titles_")
    meta = json.load(open(record.wsl(base) + ".json"))
    names = list(meta["audio"])
    inputs = ["-i", record.wsl(base) + ".mkv"]
    for n in names:
        inputs += ["-f", "f32le", "-ar", "48000", "-ac", "2", "-i", record.wsl(base) + f".{n}.raw"]
    vols = volumes or {"gta": 1.0, "mc": 1.1}
    parts, labels = [], ""
    for k, (a, b) in enumerate(segments):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos,setsar=1[v{k}]")
        for i, n in enumerate(names):
            off = meta["audio"][n]["offset_s"]
            parts.append(f"[{1 + i}:a]atrim={a + off:.3f}:{b + off:.3f},asetpts=PTS-STARTPTS,volume={vols.get(n, 1.0)}[a{k}_{i}]")
        parts.append("".join(f"[a{k}_{i}]" for i in range(len(names))) + f"amix=inputs={len(names)}:normalize=0[a{k}]")
        labels += f"[v{k}][a{k}]"
    total = sum(b - a for a, b in segments)
    parts.append(f"{labels}concat=n={len(segments)}:v=1:a=1[vc][ac]")
    last = "vc"
    for k, (t0, t1, text) in enumerate(title_list):
        png = T.title_png(text, f"{scratch}/seg{k}.png")
        inputs += ["-loop", "1", "-t", f"{total:.3f}", "-i", png]
        parts.append(f"[{last}][{1 + len(names) + k}:v]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[t{k}]")
        last = f"t{k}"
    parts.append(f"[{last}]fade=t=out:st={total - fade:.3f}:d={fade}[v]")
    parts.append(f"[ac]alimiter=limit=0.95,afade=t=in:d=0.15,afade=t=out:st={total - fade:.3f}:d={fade}[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
                    "-r", "60", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True)
    print(f"wrote {out} ({total:.1f}s)")

if __name__ == "__main__":
    segs = [tuple(float(x) for x in s.split("-")) for s in sys.argv[3].split(",")]
    cut(sys.argv[1], sys.argv[2], segs, json.loads(sys.argv[4]) if len(sys.argv) > 4 else [])
