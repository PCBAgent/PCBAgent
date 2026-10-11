#!/usr/bin/env python3
"""Choose the regulator from the spec and write designs/<slug>/design/ic.json.

Runs before skidl_sim.py. Does not use the network.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lookup import choose_ic  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("usage: choose_ic.py designs/<slug>", file=sys.stderr)
        return 2
    try:
        chosen = choose_ic(sys.argv[1], os.environ.get("PCB_JLCPCB_CSV"))
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 2
    except LookupError as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps({"ic": chosen}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
