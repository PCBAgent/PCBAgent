"""Demo recording contracts and playback without a desktop; real pipeline when installed."""

import argparse
import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/layout"))
import demo
import demo_record
import layout
from test_layout import LDO_CONSTRAINTS, make_design, needs_kicad


def track(net, start, end, layer="F.Cu"):
    return {"kind": "PCB_TRACK", "net": net, "start": start, "end": end, "layer": layer, "width": 250000}


def test_route_order_follows_via_and_preserves_every_item():
    first = track("A", [0, 0], [1, 0])
    via = {"kind": "PCB_VIA", "net": "A", "position": [1, 0], "layers": ["F.Cu", "B.Cu"]}
    last = track("A", [1, 0], [2, 0], "B.Cu")
    disconnected = track("Z", [8, 0], [9, 0])
    items = [last, disconnected, via, first]
    result = demo.route_order(items)
    assert result[-1] == disconnected
    assert sorted(map(str, result)) == sorted(map(str, items))
    assert result == demo.route_order(list(reversed(items)))
    assert result.index(via) in (0, 1)


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_invalid_speed(value):
    with pytest.raises(argparse.ArgumentTypeError):
        demo.positive_speed(value)


def test_artifact_rejects_escape(tmp_path):
    with pytest.raises(ValueError):
        demo.artifact(tmp_path, "../outside.json")


def test_recorder_publishes_complete_artifacts_and_replays_after_cleanup(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "placement.json").write_text('{"parts": {}}')
    recorder = demo_record.Recorder(tmp_path, sys.executable, launch=False)
    recorder.emit("attempt-result", 1, work, status="fail", reasons=["Does not fit"])
    (work / "placement.json").unlink()
    recorder.emit("finished", chosen_attempt=1, status="fail", reasons=["Does not fit"])
    data = json.loads(recorder.path.read_text())
    saved = demo.artifact(recorder.directory, data["events"][0]["artifacts"]["placement.json"])
    assert json.loads(saved.read_text()) == {"parts": {}}
    assert data["status"] == "complete"
    assert [e["kind"] for e in demo.events(recorder.path, True)] == ["attempt-result", "finished"]


def test_live_tail_observes_new_events(tmp_path):
    r = demo_record.Recorder(tmp_path, sys.executable, launch=False)
    r.emit("attempt-result", 1, status="fail")
    stream = demo.events(r.path)
    assert next(stream)["attempt"] == 1
    r.emit("finished", chosen_attempt=1, status="fail")
    assert next(stream)["kind"] == "finished"
    with pytest.raises(StopIteration):
        next(stream)


def test_live_player_catches_up_after_producer_exits(tmp_path, monkeypatch):
    r = demo_record.Recorder(tmp_path, sys.executable, launch=False)
    r.emit("placement-ready", 1)
    stream = demo.events(r.path)
    assert next(stream)["kind"] == "placement-ready"
    # Generation finishes while the consumer is still animating the first event.
    r.emit("routing-ready", 1)
    r.emit("finished", chosen_attempt=1, status="pass")
    monkeypatch.setattr(demo.os, "kill", Mock(side_effect=ProcessLookupError))
    assert [e["kind"] for e in stream] == ["routing-ready", "finished"]


def test_incomplete_recording_never_reports_success(tmp_path, monkeypatch):
    r = demo_record.Recorder(tmp_path, sys.executable, launch=False)
    monkeypatch.setattr(demo.os, "kill", Mock(side_effect=ProcessLookupError))
    assert list(demo.events(r.path))[-1]["kind"] == "aborted"
    assert list(demo.events(r.path, True))[-1]["kind"] == "aborted"


def test_recording_failure_does_not_raise_or_publish_partial_scene(tmp_path):
    r = demo_record.Recorder(tmp_path, sys.executable, launch=False)
    work = tmp_path / "work"
    work.mkdir()
    (work / "placed.kicad_pcb").write_text("invalid")
    r.emit("placement-ready", 1, work, "placed.kicad_pcb")
    data = json.loads(r.path.read_text())
    assert data["status"] == "recording_failed"
    assert not data["events"]


def test_disconnect_stops_player_with_actionable_message(tmp_path, monkeypatch, capsys):
    r = demo_record.Recorder(tmp_path, sys.executable, launch=False)
    r.emit("placement-ready", 1)
    monkeypatch.setattr(demo.Player, "consume", Mock(side_effect=ConnectionError("disconnected")))
    monkeypatch.setattr(sys, "argv", ["demo.py", "--manifest", str(r.path), "--replay"])
    assert demo.main() == 1
    assert "replay the recording later" in capsys.readouterr().err


def test_connect_matches_full_document_path(tmp_path, monkeypatch):
    kipy = pytest.importorskip("kipy")
    target = tmp_path / "demo.kicad_pcb"
    wrong = Mock(document=SimpleNamespace(board_filename="demo.kicad_pcb", project=SimpleNamespace(path="/other")))
    right = Mock(document=SimpleNamespace(board_filename="demo.kicad_pcb", project=SimpleNamespace(path=str(tmp_path))))
    clients = {"wrong": Mock(), "right": Mock()}
    clients["wrong"].get_board.return_value = wrong
    clients["right"].get_board.return_value = right
    clients["right"].get_version.return_value = SimpleNamespace(major=10)
    monkeypatch.setattr(demo, "socket_paths", lambda: iter(clients))
    monkeypatch.setattr(kipy, "KiCad", lambda socket_path, **kwargs: clients[socket_path])
    assert demo.connect(target) is right
    wrong.update_items.assert_not_called()


def test_selected_earlier_attempt_is_restored(tmp_path):
    player = demo.Player(tmp_path)
    player.board = Mock()
    player.attempt = 2
    player.scenes[1] = {"parts": {}, "tracks": []}
    player.show_placement = Mock()
    player.routing = Mock()
    player.caption = Mock()
    player.consume({"kind": "finished", "chosen_attempt": 1, "status": "fail", "reasons": ["Unrouted"]})
    player.show_placement.assert_called_once_with(player.scenes[1], 1, animate=False)
    player.routing.assert_called_once_with(player.scenes[1], animate=False)
    assert "FAIL" in player.caption.call_args.args[0]
    player.board.save.assert_called_once()


def test_playback_preserves_track_and_via_dimensions(tmp_path):
    pytest.importorskip("kipy")
    from kipy.board_types import Net
    from kipy.proto.board.board_types_pb2 import BoardLayer

    player = demo.Player(tmp_path)
    player.board = Mock()
    net = Net()
    net.name = "A"
    player.board.get_nets.return_value = [net]
    player.board.create_items.side_effect = lambda items: items
    player.caption = Mock()
    scene = {"tracks": [track("A", [1000000, 2000000], [3000000, 2000000]),
                        {"kind": "PCB_VIA", "net": "A", "position": [3000000, 2000000],
                         "width": 600000, "drill": 300000, "layers": ["F.Cu", "B.Cu"], "via_type": "THROUGH"}]}
    original = copy.deepcopy(scene)
    player.routing(scene, animate=False)
    items = player.board.create_items.call_args.args[0]
    via = next(i for i in items if hasattr(i, "drill_diameter"))
    assert via.diameter == 600000 and via.drill_diameter == 300000
    assert via.padstack.drill.end_layer == BoardLayer.BL_B_Cu
    copper = next(i for i in items if hasattr(i, "width"))
    assert copper.width == 250000 and copper.end.x == 3000000
    assert all(i.net.name == "A" for i in items)
    assert scene == original


def test_placement_moves_serialized_pads_with_footprint(tmp_path):
    pytest.importorskip("kipy")
    from kipy.board_types import FootprintInstance, Pad
    from kipy.geometry import Vector2

    footprint = FootprintInstance()
    footprint.position = Vector2.from_xy_mm(5, 5)
    pad = Pad()
    pad.position = Vector2.from_xy_mm(6, 5)
    footprint.definition.items = [pad]
    player = demo.Player(tmp_path)
    player.board = Mock()
    player.board.get_tracks.return_value = []
    player.board.get_vias.return_value = []
    player.board.get_shapes.return_value = []
    player.staged = {"U1": footprint}
    player.caption = Mock()
    player.show_placement({"outline": [], "parts": {"U1": {"position": [20000000, 20000000], "rotation": 90}}},
                          1, animate=False)
    moved = FootprintInstance(player.board.update_items.call_args.args[0].proto)
    assert moved.position == Vector2.from_xy_mm(20, 20)
    assert moved.definition.pads[0].position == Vector2.from_xy_mm(20, 19)
    assert footprint.definition.pads[0].position == Vector2.from_xy_mm(6, 5)


@needs_kicad
def test_ldo_demo_recording_matches_real_board_and_survives_cleanup(tmp_path):
    root = make_design(tmp_path, LDO_CONSTRAINTS, None)
    report = layout.run(root, demo=True, demo_launch=False)
    assert report["status"] == "pass"
    latest = json.loads((root / "layout/demo/latest.json").read_text())
    manifest = root / "layout/demo" / latest["manifest"]
    saved = list(demo.events(manifest, True))
    assert saved[-1]["kind"] == "finished"
    assert [e["kind"] for e in saved if e.get("attempt") == report["chosen_attempt"]] == [
        "placement-ready", "routing-ready", "check-result", "attempt-result"]
    assert not (root / "layout/.work").exists()
    routed = next(e for e in saved if e["kind"] == "routing-ready" and e["attempt"] == report["chosen_attempt"])
    assert demo.artifact(manifest.parent, routed["board"]).read_bytes() == (root / "layout/board.kicad_pcb").read_bytes()
    scene = json.loads(demo.artifact(manifest.parent, routed["scene"]).read_text())
    assert scene["units"] == "nm" and len(scene["parts"]) == 7 and scene["tracks"]
    vias = [t for t in scene["tracks"] if t["kind"] == "PCB_VIA"]
    assert all(t["width"] >= t["drill"] > 0 and t["via_type"] == "THROUGH" for t in vias)


@needs_kicad
def test_routing_failure_recording_and_retries(tmp_path, monkeypatch):
    root = make_design(tmp_path, LDO_CONSTRAINTS, None)
    monkeypatch.setattr(layout, "freerouting_cli", lambda: "/bin/true")
    monkeypatch.setattr(layout, "MAX_ATTEMPTS", 2)
    report = layout.run(root, demo=True, demo_launch=False)
    assert report["status"] == "fail"
    latest = json.loads((root / "layout/demo/latest.json").read_text())
    recorded = list(demo.events(root / "layout/demo" / latest["manifest"], True))
    assert len([e for e in recorded if e["kind"] == "placement-ready"]) == 2
    assert not any(e["kind"] == "routing-ready" for e in recorded)
    assert recorded[-1]["chosen_attempt"] == report["chosen_attempt"]
    assert recorded[-1]["status"] == "fail"


@pytest.mark.skipif(os.environ.get("PCBAGENT_TEST_GUI") != "1", reason="opt-in: opens a disposable KiCad window")
@needs_kicad
def test_real_editor_playback_matches_source(tmp_path):
    """Run from the KiCad desktop with the API enabled; leaves the demo open for inspection."""
    import hashlib
    import subprocess

    root = make_design(tmp_path, LDO_CONSTRAINTS, None)
    report = layout.run(root, demo=True, demo_launch=False)
    assert report["status"] == "pass"
    source = root / "layout/board.kicad_pcb"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    latest = json.loads((root / "layout/demo/latest.json").read_text())
    manifest = root / "layout/demo" / latest["manifest"]
    player = demo.Player(manifest.parent, speed=20)
    for event in demo.events(manifest, True):
        player.consume(event)
    output = Path(player.board.document.project.path) / player.board.name
    scene_paths = []
    for index, board in enumerate([source, output]):
        scene = tmp_path / f"scene-{index}.json"
        subprocess.run([layout.kicad_python(), str(layout.KICAD_SCRIPT), "scene", str(board), str(scene)],
                       check=True, capture_output=True)
        scene_paths.append(json.loads(scene.read_text()))
    expected, actual = scene_paths
    assert expected["parts"] == actual["parts"]
    assert demo.route_order(expected["tracks"]) == demo.route_order(actual["tracks"])
    assert sorted(expected["outline"], key=str) == sorted(actual["outline"], key=str)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
