#!/usr/bin/env python3
"""Animate saved layout results in a disposable KiCad PCB Editor document."""

import argparse
from itertools import groupby
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4


def positive_speed(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("speed must be a finite positive number")
    return value


def route_order(tracks):
    """Walk connected endpoints per net and layer; vias bridge their copper layers."""
    def endpoints(item):
        if item["kind"] == "PCB_VIA":
            return {(layer, *item["position"]) for layer in item["layers"]}
        return {(item["layer"], *item[key]) for key in ("start", "end")}

    ordered = []
    for net in sorted({t["net"] for t in tracks}):
        remaining = sorted((t for t in tracks if t["net"] == net), key=lambda t: json.dumps(t, sort_keys=True))
        reached = set()
        while remaining:
            index = next((i for i, t in enumerate(remaining) if endpoints(t) & reached), 0)
            item = remaining.pop(index)
            reached.update(endpoints(item))
            ordered.append(item)
    return ordered


def artifact(directory, relative):
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("Demo artifact is outside its recording directory")
    return path


def events(path, replay=False):
    """Tail atomically published manifests, or consume a fixed replay snapshot."""
    index = 0
    while True:
        data = json.loads(path.read_text())
        if data.get("version") != 1:
            raise ValueError("Unsupported demo recording version")
        pending = data["events"][index:]
        for event in pending:
            yield event
            index += 1
        # Playback can outlast generation. Reload after consuming a batch before checking
        # producer liveness, so a finished run's remaining events are never lost.
        if pending and not replay:
            continue
        if data["status"] != "running" or replay:
            if data["status"] != "complete":
                yield {"kind": "aborted", "message": data.get("error", "Recording incomplete; checks not confirmed")}
            return
        try:
            os.kill(data["producer_pid"], 0)
        except ProcessLookupError:
            if json.loads(path.read_text()) != data:
                continue
            yield {"kind": "aborted", "message": "Layout process stopped; recording incomplete"}
            return
        time.sleep(0.25)


def socket_paths():
    explicit = os.environ.get("KICAD_API_SOCKET")
    if explicit:
        yield explicit if explicit.startswith("ipc://") else "ipc://" + explicit
    for directory in [Path("/tmp/kicad"), Path("/tmp/org.kicad.kicad"),
                      Path.home() / ".var/app/org.kicad.KiCad/cache/tmp/kicad"]:
        for path in sorted(directory.glob("api*.sock")):
            yield "ipc://" + str(path)


def connect(path, timeout=30):
    from kipy import KiCad

    deadline = time.monotonic() + timeout
    last_error = "No API socket found"
    while time.monotonic() < deadline:
        for socket in socket_paths():
            try:
                client = KiCad(socket_path=socket, client_name="pcbagent-demo", timeout_ms=2000)
                board = client.get_board()
                document = board.document
                filename = Path(document.board_filename)
                if not filename.is_absolute():
                    filename = Path(document.project.path) / filename
                if filename.resolve() == path.resolve():
                    if client.get_version().major < 10:
                        raise RuntimeError("Demo playback requires KiCad 10 or newer")
                    return board
            except Exception as error:
                last_error = str(error)
        time.sleep(0.25)
    raise RuntimeError(f"Could not connect to {path}. Enable Preferences > Plugins > Enable KiCad API, "
                       f"and close any startup dialogs. {last_error}")


class Player:
    def __init__(self, directory, speed=1):
        self.directory = directory
        self.speed = speed
        self.board = None
        self.attempt = None
        self.scenes = {}
        self.staged = {}

    def start(self, event):
        from layout import kicad_python

        if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise RuntimeError("No graphical desktop in this session. Replay from a desktop terminal on the KiCad machine.")
        executable = os.environ.get("KICAD_PCBNEW") or shutil.which("pcbnew")
        if not executable:
            mac = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/pcbnew")
            if mac.is_file():
                executable = str(mac)
        if not executable:
            raise RuntimeError("PCB Editor executable not found; set KICAD_PCBNEW")
        playback = self.directory / "playback" / uuid4().hex[:8]
        playback.mkdir(parents=True)
        path = playback / "demo.kicad_pcb"
        source = artifact(self.directory, event["board"])
        subprocess.run([kicad_python(), str(Path(__file__).with_name("kicad.py")),
                        "demo-prepare", str(source), str(path)],
                       check=True, capture_output=True, text=True, timeout=60)
        project = source.with_suffix(".kicad_pro")
        if project.is_file():
            shutil.copy2(project, path.with_suffix(".kicad_pro"))
        with (playback / "editor.log").open("w") as log:
            subprocess.Popen([executable, str(path)], stdout=log, stderr=log, start_new_session=True)
        print(f"Demo board: {path}", file=sys.stderr)
        self.board = connect(path)
        self.staged = {fp.reference_field.text.value: type(fp)(fp.proto) for fp in self.board.get_footprints()}
        self.caption_item = next(t for t in self.board.get_text() if t.value == "Preparing placement...")
        from kipy.proto.board.board_types_pb2 import BoardLayer
        self.board.set_visible_layers([
            BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu, BoardLayer.BL_F_SilkS,
            BoardLayer.BL_B_SilkS, BoardLayer.BL_Edge_Cuts, BoardLayer.BL_Dwgs_User,
        ])

    def caption(self, message):
        print(message, file=sys.stderr)
        if self.board:
            self.caption_item.value = message
            self.board.update_items(self.caption_item)

    def show_placement(self, scene, attempt, animate=True):
        from kipy.geometry import Angle, Vector2
        from kipy.board_types import BoardSegment
        from kipy.proto.board.board_types_pb2 import BoardLayer

        self.attempt = attempt
        board = self.board
        removable = list(board.get_tracks()) + list(board.get_vias())
        removable += [shape for shape in board.get_shapes() if shape.layer == BoardLayer.BL_Edge_Cuts]
        if removable:
            board.remove_items(removable)
        outline = []
        for edge in scene["outline"]:
            item = BoardSegment()
            item.start = Vector2.from_xy(*edge["start"])
            item.end = Vector2.from_xy(*edge["end"])
            item.layer = BoardLayer.BL_Edge_Cuts
            item.attributes.stroke.width = edge["width"]
            outline.append(item)
        board.create_items(outline)
        if set(scene["parts"]) != set(self.staged):
            raise ValueError("Footprint references changed between demo attempts")
        board.update_items(list(self.staged.values()))
        self.caption(f"Attempt {attempt}: placing components")
        duration = 15 / max(1, len(scene["parts"])) / self.speed if animate else 0
        frames = max(1, math.ceil(duration * 10))
        for ref, target in sorted(scene["parts"].items()):
            base = self.staged[ref]
            delta = (target["rotation"] - base.orientation.degrees + 180) % 360 - 180
            for frame in range(1, frames + 1):
                fraction = frame / frames
                # Reconstruct from protobuf: deepcopy breaks the wrapper's shared child references.
                item = type(base)(base.proto)
                item.orientation = Angle.from_degrees(base.orientation.degrees + delta * fraction)
                item.position = Vector2.from_xy(*[
                    round(start + (end - start) * fraction)
                    for start, end in zip([base.position.x, base.position.y], target["position"])
                ])
                board.update_items(item)
                if duration:
                    time.sleep(duration / frames)

    def routing(self, scene, animate=True):
        from kipy.board_types import Track, ArcTrack, Via
        from kipy.geometry import Vector2
        from kipy.proto.board.board_types_pb2 import BoardLayer, ViaType

        nets = {net.name: net for net in self.board.get_nets()}
        tracks = route_order(scene["tracks"])
        duration = 15 / self.speed if animate else 0
        batch_size = max(1, math.ceil(len(tracks) / max(1, duration * 10)))
        batches = []
        for _, group in groupby(tracks, key=lambda t: t["net"]):
            net_tracks = list(group)
            batches.extend(net_tracks[i:i + batch_size] for i in range(0, len(net_tracks), batch_size))
        drawn = 0
        for batch in batches:
            items = []
            for data in batch:
                if data["kind"] == "PCB_VIA":
                    item = Via()
                    item.position = Vector2.from_xy(*data["position"])
                    item.type = ViaType.Value("VT_" + data["via_type"])
                    item.diameter = data["width"]
                    item.drill_diameter = data["drill"]
                    item.padstack.drill.start_layer = BoardLayer.Value("BL_" + data["layers"][0].replace(".", "_"))
                    item.padstack.drill.end_layer = BoardLayer.Value("BL_" + data["layers"][1].replace(".", "_"))
                else:
                    item = ArcTrack() if data["kind"] == "PCB_ARC" else Track()
                    item.start = Vector2.from_xy(*data["start"])
                    item.end = Vector2.from_xy(*data["end"])
                    if data["kind"] == "PCB_ARC":
                        item.mid = Vector2.from_xy(*data["mid"])
                    item.width = data["width"]
                    item.layer = BoardLayer.Value("BL_" + data["layer"].replace(".", "_"))
                item.net = nets[data["net"]]
                items.append(item)
            drawn += len(batch)
            self.caption(f"Attempt {self.attempt}: drawing {batch[0]['net']} ({drawn}/{len(tracks)})")
            created = self.board.create_items(items)
            if len(created) != len(items):
                raise RuntimeError("KiCad did not create every routing item")
            if duration:
                time.sleep(duration / len(batches))

    def consume(self, event):
        kind, attempt = event["kind"], event.get("attempt")
        if kind == "placement-ready":
            if not self.board:
                self.start(event)
            scene = json.loads(artifact(self.directory, event["scene"]).read_text())
            self.scenes[attempt] = scene
            self.show_placement(scene, attempt)
            self.caption(f"Attempt {attempt}: calculating routes...")
        elif kind == "routing-ready":
            scene = json.loads(artifact(self.directory, event["scene"]).read_text())
            self.scenes[attempt] = scene
            self.routing(scene)
            self.caption(f"Attempt {attempt}: checking design rules...")
        elif kind in {"check-result", "attempt-result"}:
            reason = "; ".join(event.get("reasons", []))
            self.caption(f"Attempt {attempt}: {event['status'].upper()}" + (f" - {reason}" if reason else ""))
        elif kind == "finished":
            chosen = event["chosen_attempt"]
            if self.board and chosen in self.scenes and self.attempt != chosen:
                scene = self.scenes[chosen]
                self.show_placement(scene, chosen, animate=False)
                self.routing(scene, animate=False)
            self.caption(f"Selected attempt {chosen}: {event['status'].upper()}" +
                         (" - " + "; ".join(event["reasons"]) if event.get("reasons") else ""))
            if self.board:
                self.board.save()
        elif kind == "aborted":
            self.caption("Demo incomplete: " + event["message"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design", nargs="?")
    parser.add_argument("--manifest", type=Path, help="specific saved manifest (otherwise latest run)")
    parser.add_argument("--replay", action="store_true", help="play saved results without waiting for computation")
    parser.add_argument("--speed", type=positive_speed, default=1)
    args = parser.parse_args()
    try:
        path = args.manifest
        if path is None:
            if not args.design:
                parser.error("provide a design directory or --manifest")
            from layout import design_root
            directory = design_root(args.design) / "layout" / "demo"
            latest = json.loads((directory / "latest.json").read_text())
            path = artifact(directory, latest["manifest"])
        path = path.resolve()
        player = Player(path.parent, args.speed)
        for event in events(path, args.replay):
            player.consume(event)
        return 0
    except KeyboardInterrupt:
        print("Demo playback stopped; saved results remain available for replay.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Demo playback stopped: {error}. Layout generation is independent; replay the recording later.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
