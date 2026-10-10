#!/usr/bin/env python3
"""Download the JLCPCB economic-parts cache once. Lookups read the file and do not use the network."""

import sys
import urllib.request
from pathlib import Path

from catalog import CATALOG_URL, default_catalog


def fetch(destination=None, refresh=False):
    destination = Path(destination) if destination else default_catalog()
    if destination.is_file() and not refresh:
        print(destination)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(CATALOG_URL, destination)
    print(destination)
    return destination


def main():
    refresh = "--refresh" in sys.argv[1:]
    try:
        fetch(refresh=refresh)
    except OSError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
