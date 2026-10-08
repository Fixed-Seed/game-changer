"""`fsgc` command line: one entry point for every tool, so skills can say `fsgc <group> <cmd>`."""
from __future__ import annotations

import argparse
import importlib
import sys

from game_changer import __doc__ as DOC, __version__

GROUPS = ["scan", "passthrough", "fixedseed", "sprite", "render3d", "video", "win", "backup", "publish", "kb"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fsgc", description=DOC, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"game-changer {__version__}")
    sub = ap.add_subparsers(dest="group", metavar="<group>")
    for g in GROUPS:
        importlib.import_module(f"game_changer.{g}").register(sub)
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        # a group without a command: show that group's help
        if args.group:
            ap.parse_args([args.group, "--help"])
        ap.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
