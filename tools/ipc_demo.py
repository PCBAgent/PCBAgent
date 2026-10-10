"""Animate the BLDC board through KiCad's supported IPC API."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from kipy import KiCad
from kipy.board_types import Net, Track, Via
from kipy.geometry import Angle, Vector2
from kipy.util.units import from_mm


ROOT = Path(__file__).resolve().parents[1]
TARGET_BOARD = ROOT / "astra-bldc.kicad_pcb"
STATUS_FILE = ROOT / ".astra-demo-status"
ERROR_FILE = ROOT / ".astra-demo-error"

sys.path.insert(0, str(ROOT / "tools"))
import generate_project as design  # noqa: E402


def status(value: str) -> None:
    STATUS_FILE.write_text(value + "\n", encoding="utf-8")
    print(f"Playback stage: {value}", flush=True)


def reference_of(footprint) -> str:
    field = footprint.reference_field
    text = field.text
    return text.value


def parse_routes() -> tuple[list[dict], list[dict]]:
    text = TARGET_BOARD.read_text(encoding="utf-8")
    net_names = {
        int(number): name
        for number, name in re.findall(r'^\s*\(net (\d+) "([^"]*)"\)', text, re.MULTILINE)
    }
    segment_pattern = re.compile(
        r'\(segment \(start ([-\d.]+) ([-\d.]+)\) '
        r'\(end ([-\d.]+) ([-\d.]+)\) \(width ([-\d.]+)\)\s*'
        r'\(layer "([^"]+)"\) \(net (\d+)\)',
        re.MULTILINE,
    )
    via_pattern = re.compile(
        r'\(via \(at ([-\d.]+) ([-\d.]+)\) \(size ([-\d.]+)\) '
        r'\(drill ([-\d.]+)\) \(layers "F.Cu" "B.Cu"\)\s*'
        r'\(net (\d+)\)',
        re.MULTILINE,
    )
    segments = [
        {
            "start": (float(x1), float(y1)),
            "end": (float(x2), float(y2)),
            "width": float(width),
            "layer": layer,
            "net": net_names[int(net_id)],
        }
        for x1, y1, x2, y2, width, layer, net_id in segment_pattern.findall(text)
    ]
    vias = [
        {
            "position": (float(x), float(y)),
            "diameter": float(diameter),
            "drill": float(drill),
            "net": net_names[int(net_id)],
        }
        for x, y, diameter, drill, net_id in via_pattern.findall(text)
    ]
    return segments, vias


def connect(timeout: float = 20.0) -> tuple[KiCad, object]:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            client = KiCad(client_name="Astra BLDC Playback", timeout_ms=2000)
            return client, client.get_board()
        except Exception as error:  # KiCad may still be starting its API server.
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(f"Could not connect to KiCad IPC API: {last_error}")


def main() -> None:
    ERROR_FILE.unlink(missing_ok=True)
    client, board = connect()
    del client  # The board proxy retains its client.

    footprints = {reference_of(fp): fp for fp in board.get_footprints()}
    status("placement")
    for reference, (target_x, target_y, target_angle) in design.PLACEMENT.items():
        footprint = footprints.get(reference)
        if footprint is None:
            continue
        source_x = footprint.position.x / 1_000_000.0
        source_y = footprint.position.y / 1_000_000.0
        for step in range(1, 5):
            amount = step / 4.0
            footprint.position = Vector2.from_xy_mm(
                source_x + (target_x - source_x) * amount,
                source_y + (target_y - source_y) * amount,
            )
            if step == 4:
                footprint.orientation = Angle.from_degrees(target_angle)
            board.update_items(footprint)
            time.sleep(0.075)

    nets = {net.name: net for net in board.get_nets()}
    segments, vias = parse_routes()
    status("routing")
    batch = []
    for route in segments:
        item = Track()
        item.start = Vector2.from_xy_mm(*route["start"])
        item.end = Vector2.from_xy_mm(*route["end"])
        item.width = from_mm(route["width"])
        item.layer = board.get_layer_by_name(route["layer"])
        item.net = nets.get(route["net"], Net(name=route["net"]))
        batch.append(item)
        if len(batch) == 4:
            board.create_items(batch)
            batch.clear()
            time.sleep(0.08)
    if batch:
        board.create_items(batch)

    for route in vias:
        item = Via()
        item.position = Vector2.from_xy_mm(*route["position"])
        item.diameter = from_mm(route["diameter"])
        item.drill_diameter = from_mm(route["drill"])
        item.net = nets.get(route["net"], Net(name=route["net"]))
        board.create_items(item)
        time.sleep(0.06)

    status("copper-fill")
    board.refill_zones()
    board.save()
    status("complete")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        message = traceback.format_exc()
        ERROR_FILE.write_text(message, encoding="utf-8")
        print(message, file=sys.stderr)
        raise
