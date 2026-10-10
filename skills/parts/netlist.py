#!/usr/bin/env python3
"""Run designs/<slug>/parts/skidl_kicad.py. Abort when a board part has no footprint."""

import json
import os
import subprocess
import sys
from pathlib import Path


def design_root(path):
    path = Path(path).resolve()
    if path.name in {"design", "parts"} and (path.parent / "design" / "circuit-spec.json").is_file():
        return path.parent
    return path


def main():
    if len(sys.argv) != 2:
        print("usage: netlist.py designs/<slug>", file=sys.stderr)
        return 2
    root = design_root(sys.argv[1])
    parts_path = root / "parts" / "parts.json"
    script = root / "parts" / "skidl_kicad.py"
    if not parts_path.is_file():
        print(f"{parts_path} does not exist. Run lookup.py first.", file=sys.stderr)
        return 2
    parts = json.loads(parts_path.read_text(encoding="utf-8"))["parts"]
    missing = [part for part in parts if part.get("on_board") and not part.get("footprint")]
    if missing:
        for part in missing:
            print(
                f"{part.get('ref') or part['kind']} has no KiCad footprint. Netlist aborted.",
                file=sys.stderr,
            )
        return 2
    if not script.is_file():
        print(f"{script} does not exist. Write it from parts.json.", file=sys.stderr)
        return 2
    env = os.environ.copy()
    symbol_dir = env.get("KICAD10_SYMBOL_DIR") or env.get("KICAD_SYMBOL_DIR") or "/usr/share/kicad/symbols"
    env["KICAD_SYMBOL_DIR"] = symbol_dir
    env["KICAD10_SYMBOL_DIR"] = symbol_dir
    proc = subprocess.run([sys.executable, str(script)], cwd=script.parent, env=env, text=True)
    netlist = root / "parts" / "board.net"
    if proc.returncode != 0 or not netlist.is_file():
        print("skidl_kicad.py did not write parts/board.net", file=sys.stderr)
        return 2
    print(netlist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
