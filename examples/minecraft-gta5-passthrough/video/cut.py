"""Cut a take into the final video: python cut.py <take> <out.mp4> [head] [length] [second title]
Titles come from the take's event log: "Minecraft x GTA V" at the start, the second title (if any) at "place".
Pass "" for head or length to keep their defaults (from the "approach" and "end" marks)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import record  # noqa: E402


def cut(name, out, head=None, length=None, volumes=None, title2=None):
    base = record.TAKES + "\\" + name
    log = json.load(open(record.wsl(base) + ".events.json"))
    ev = {}
    for t, n in log["events"]:
        ev.setdefault(n, t)
    head = head if head is not None else max(0.0, ev.get("approach", 0.0) - 0.3)
    end = ev.get("end", head + 30.0)
    length = length or (end - head)
    rel = lambda n, d=0.0: ev.get(n, head) - head + d
    titles = [(0.2, 2.9, "Minecraft x GTA V")]
    if title2:
        titles.append((rel("place", 0.3), rel("place", 3.0), title2))
    record.post(base, out, head, length, titles=titles, volumes=volumes or {"gta": 1.0, "mc": 1.1})


if __name__ == "__main__":
    arg = lambda i: sys.argv[i] if len(sys.argv) > i and sys.argv[i] else None
    cut(sys.argv[1], sys.argv[2], float(arg(3)) if arg(3) else None, float(arg(4)) if arg(4) else None, title2=arg(5))
