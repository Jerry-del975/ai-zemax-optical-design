"""Smoke-test OpticStudio 2024 R1 ZOS-API connection."""

from __future__ import annotations

import argparse
from pathlib import Path

from zos_design_primitives import connect_zemax, resolve_zosapi_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zos-root", default=None)
    parser.add_argument("--standalone", action="store_true", help="Create a new OpticStudio instance instead of attaching to Interactive Extension.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = resolve_zosapi_root(args.zos_root)
    print(f"ZOSAPI root: {root}")
    app = connect_zemax(str(root), standalone=args.standalone)
    try:
        system = app.PrimarySystem
        print("Connected: yes")
        print(f"Primary system: {type(system).__name__}")
        print(f"Install root exists: {Path(root).is_dir()}")
    finally:
        if args.standalone:
            app.CloseApplication()


if __name__ == "__main__":
    main()
