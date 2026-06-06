"""Smoke-test OpticStudio ZOS-API connection via ZOSPy (v20.3+)."""

from __future__ import annotations

import argparse

from zos_design_primitives import connect_zemax


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zos-root", default=None, help="OpticStudio install directory (optional; ZOSPy auto-discovers by default).")
    parser.add_argument("--standalone", action="store_true", help="Create a new OpticStudio instance instead of attaching to Interactive Extension.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = connect_zemax(args.zos_root, standalone=args.standalone)
    try:
        system = app.PrimarySystem
        print("Connected: yes")
        print(f"Primary system: {type(system).__name__}")
    finally:
        if args.standalone:
            app.CloseApplication()


if __name__ == "__main__":
    main()
