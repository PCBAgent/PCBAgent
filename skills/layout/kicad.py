#!/usr/bin/env python3
"""KiCad board steps for layout. Runs under the Python that ships pcbnew, not .venv.

    kicad.py footprints <job.json> <out.json>   courtyard and pad positions per footprint
    kicad.py build <job.json>                   placed board with nets and outline
    kicad.py rules <job.json>                   design rules and netclasses, then Specctra .dsn
    kicad.py import <board> <session> <out> <stats.json>   routed board from a Freerouting .ses
    kicad.py scene <board> <out.json>         exact geometry for demo playback
    kicad.py demo-prepare <board> <out>       disposable board with staged components

build and rules are separate processes. pcbnew only writes a board's .kicad_pro, where KiCad keeps design
rules, when the board was loaded from disk in a process that has not built a board in memory.
"""

import json
import math
import os
import sys

import pcbnew


NECK_RADIUS_MM = 1.0

FOOTPRINT_DIRS = (
    "/usr/share/kicad/footprints",
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",
)


def mm(value):
    return pcbnew.FromMM(float(value))


def footprint_dir(job):
    candidates = [job.get("footprint_dir"), os.environ.get("KICAD10_FOOTPRINT_DIR"), os.environ.get("KICAD_FOOTPRINT_DIR")]
    candidates.extend(FOOTPRINT_DIRS)
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    raise SystemExit("no KiCad footprint library directory found")


def load_footprint(root, fpid):
    if ":" not in fpid:
        raise SystemExit(f"footprint {fpid!r} is not Library:Name")
    library, name = fpid.split(":", 1)
    path = os.path.join(root, library + ".pretty")
    footprint = pcbnew.FootprintLoad(path, name) if os.path.isdir(path) else None
    if footprint is None:
        raise SystemExit(f"footprint {fpid} not found in {root}")
    return footprint


def footprints(job_path, out_path):
    with open(job_path, encoding="utf-8") as handle:
        job = json.load(handle)
    root = footprint_dir(job)
    geometry = {}
    for fpid in job["footprints"]:
        footprint = load_footprint(root, fpid)
        courtyard = footprint.GetCourtyard(pcbnew.F_CrtYd)
        if courtyard.OutlineCount() > 0:
            box = courtyard.BBox()
        else:
            box = footprint.GetBoundingBox(False)
        pads = {}
        for pad in footprint.Pads():
            number = pad.GetNumber()
            if not number:
                continue
            pads.setdefault(number, []).append((pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)))
        geometry[fpid] = {
            "courtyard": [
                pcbnew.ToMM(box.GetX()),
                pcbnew.ToMM(box.GetY()),
                pcbnew.ToMM(box.GetX() + box.GetWidth()),
                pcbnew.ToMM(box.GetY() + box.GetHeight()),
            ],
            "pads": {
                number: [sum(p[0] for p in spots) / len(spots), sum(p[1] for p in spots) / len(spots)]
                for number, spots in pads.items()
            },
        }
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(geometry, handle, indent=2)


def apply_rules(board, rules, netclasses):
    settings = board.GetDesignSettings()
    settings.m_TrackMinWidth = mm(rules["min_track_width_mm"])
    settings.m_MinClearance = mm(rules["clearance_mm"])
    settings.m_CopperEdgeClearance = mm(rules["edge_clearance_mm"])
    settings.m_ViasMinSize = mm(min([rules["via_diameter_mm"]] + [c["via_diameter_mm"] for c in netclasses]))
    settings.m_MinThroughDrill = mm(min([rules["via_drill_mm"]] + [c["via_drill_mm"] for c in netclasses]))
    net_settings = settings.m_NetSettings
    default = net_settings.GetDefaultNetclass()
    default.SetTrackWidth(mm(rules["track_width_mm"]))
    default.SetClearance(mm(rules["clearance_mm"]))
    default.SetViaDiameter(mm(rules["via_diameter_mm"]))
    default.SetViaDrill(mm(rules["via_drill_mm"]))
    for spec in netclasses:
        netclass = pcbnew.NETCLASS(spec["name"])
        netclass.SetTrackWidth(mm(spec["track_width_mm"]))
        netclass.SetClearance(mm(spec["clearance_mm"]))
        netclass.SetViaDiameter(mm(spec["via_diameter_mm"]))
        netclass.SetViaDrill(mm(spec["via_drill_mm"]))
        net_settings.SetNetclass(spec["name"], netclass)
        for net in spec["nets"]:
            net_settings.SetNetclassPatternAssignment(net, spec["name"])
    net_settings.RecomputeEffectiveNetclasses()
    board.SynchronizeNetsAndNetClasses(True)


def add_outline(board, outline):
    x0, y0, x1, y1 = outline
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i, start in enumerate(corners):
        end = corners[(i + 1) % 4]
        segment = pcbnew.PCB_SHAPE(board)
        segment.SetShape(pcbnew.SHAPE_T_SEGMENT)
        segment.SetLayer(pcbnew.Edge_Cuts)
        segment.SetWidth(mm(0.1))
        segment.SetStart(pcbnew.VECTOR2I(mm(start[0]), mm(start[1])))
        segment.SetEnd(pcbnew.VECTOR2I(mm(end[0]), mm(end[1])))
        board.Add(segment)


def build(job_path):
    with open(job_path, encoding="utf-8") as handle:
        job = json.load(handle)
    root = footprint_dir(job)
    board = pcbnew.BOARD()
    nets = {}
    for component in job["components"]:
        for name in component["pads"].values():
            if name not in nets:
                net = pcbnew.NETINFO_ITEM(board, name)
                board.Add(net)
                nets[name] = net
    for component in job["components"]:
        footprint = load_footprint(root, component["footprint"])
        footprint.SetReference(component["ref"])
        footprint.SetValue(component.get("value") or "")
        board.Add(footprint)
        footprint.SetPosition(pcbnew.VECTOR2I(mm(component["x"]), mm(component["y"])))
        footprint.SetOrientationDegrees(float(component["rotation"]))
        for pad in footprint.Pads():
            name = component["pads"].get(pad.GetNumber())
            if name:
                pad.SetNet(nets[name])
    add_outline(board, job["outline_mm"])
    pcbnew.SaveBoard(job["board"], board)


def rules(job_path):
    with open(job_path, encoding="utf-8") as handle:
        job = json.load(handle)
    board = pcbnew.LoadBoard(job["board"])
    apply_rules(board, job["rules"], job.get("netclasses", []))
    board.BuildConnectivity()
    pcbnew.SaveBoard(job["board"], board)
    if not pcbnew.ExportSpecctraDSN(board, job["dsn"]):
        raise SystemExit("KiCad could not export the Specctra .dsn")


def near(pad, point):
    """True when point is within NECK_RADIUS_MM of the pad's bounding box."""
    box = pad.GetBoundingBox()
    x, y = pcbnew.ToMM(point.x), pcbnew.ToMM(point.y)
    x0, y0 = pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY())
    x1, y1 = x0 + pcbnew.ToMM(box.GetWidth()), y0 + pcbnew.ToMM(box.GetHeight())
    dx = max(0.0, x0 - x, x - x1)
    dy = max(0.0, y0 - y, y - y1)
    return (dx * dx + dy * dy) ** 0.5 <= NECK_RADIUS_MM


def import_session(board_path, session_path, out_path, stats_path):
    board = pcbnew.LoadBoard(board_path)
    if not pcbnew.ImportSpecctraSES(board, session_path):
        raise SystemExit(f"KiCad could not import {session_path}")
    pcbnew.SaveBoard(out_path, board)
    pads_by_net = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            pads_by_net.setdefault(pad.GetNetname(), []).append(pad)
    stats = {}
    vias = 0
    for track in board.GetTracks():
        if track.GetClass() == "PCB_VIA":
            vias += 1
            continue
        name = track.GetNetname()
        entry = stats.setdefault(name, {"length_mm": 0.0, "min_width_mm": None, "body_min_width_mm": None, "segments": []})
        width = pcbnew.ToMM(track.GetWidth())
        length = pcbnew.ToMM(track.GetLength())
        entry["length_mm"] += length
        if entry["min_width_mm"] is None or width < entry["min_width_mm"]:
            entry["min_width_mm"] = width
        near_pad = any(
            near(pad, track.GetStart()) and near(pad, track.GetEnd()) for pad in pads_by_net.get(name, [])
        )
        if not near_pad and (entry["body_min_width_mm"] is None or width < entry["body_min_width_mm"]):
            entry["body_min_width_mm"] = width
        entry["segments"].append({"width_mm": round(width, 4), "length_mm": round(length, 4), "near_pad": near_pad})
    with open(stats_path, "w", encoding="utf-8") as handle:
        json.dump({"nets": stats, "vias": vias}, handle, indent=2)


def scene(board_path, out_path):
    """Export exact integer-nanometer geometry for presentation, never rounded stats."""
    board = pcbnew.LoadBoard(board_path)
    point = lambda p: [int(p.x), int(p.y)]
    parts = {}
    for fp in board.GetFootprints():
        parts[fp.GetReference()] = {"position": point(fp.GetPosition()),
                                   "rotation": fp.GetOrientationDegrees(),
                                   "pads": sorted([{"number": p.GetNumber(), "net": p.GetNetname(),
                                                    "position": point(p.GetPosition())} for p in fp.Pads()],
                                                  key=lambda p: (p["number"], p["position"]))}
    outline = [{"start": point(s.GetStart()), "end": point(s.GetEnd()), "width": s.GetWidth()}
               for s in board.GetDrawings() if s.GetLayer() == pcbnew.Edge_Cuts]
    tracks = []
    for track in board.GetTracks():
        kind = track.GetClass()
        item = {"kind": kind, "net": track.GetNetname(),
                "width": track.GetWidth(track.TopLayer()) if kind == "PCB_VIA" else track.GetWidth()}
        if item["kind"] == "PCB_VIA":
            item.update(position=point(track.GetPosition()), drill=track.GetDrillValue(),
                        layers=[board.GetLayerName(track.TopLayer()), board.GetLayerName(track.BottomLayer())],
                        via_type="THROUGH" if track.GetViaType() == pcbnew.VIATYPE_THROUGH else
                                 "MICRO" if track.GetViaType() == pcbnew.VIATYPE_MICROVIA else "BLIND_BURIED")
        else:
            item.update(start=point(track.GetStart()), end=point(track.GetEnd()), layer=board.GetLayerName(track.GetLayer()))
            if item["kind"] == "PCB_ARC":
                item["mid"] = point(track.GetMid())
        tracks.append(item)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "units": "nm", "parts": parts, "outline": outline, "tracks": tracks}, handle)


def demo_prepare(board_path, out_path):
    """Create a disposable staged board. The source board is read-only."""
    board = pcbnew.LoadBoard(board_path)
    for track in list(board.GetTracks()):
        board.Remove(track)
    footprints = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    box = board.GetBoardEdgesBoundingBox()
    # One square grid alongside the board; cell size accommodates the largest part.
    cell = max([mm(5)] + [max(fp.GetBoundingBox(False).GetWidth(), fp.GetBoundingBox(False).GetHeight()) + mm(3)
                          for fp in footprints])
    columns = max(1, math.ceil(math.sqrt(len(footprints))))
    for index, fp in enumerate(footprints):
        fp.SetOrientationDegrees(0)
        fp.SetPosition(pcbnew.VECTOR2I(box.GetX() - (columns - index % columns) * cell,
                                     box.GetY() + (index // columns) * cell))
    for offset, message in [(5, "PCBAgent demo - animated results"), (2, "Preparing placement...")]:
        text = pcbnew.PCB_TEXT(board)
        text.SetText(message)
        text.SetLayer(pcbnew.Dwgs_User)
        text.SetPosition(pcbnew.VECTOR2I(box.GetX(), box.GetY() - mm(offset)))
        text.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
        text.SetTextThickness(mm(0.12))
        text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        board.Add(text)
    pcbnew.SaveBoard(out_path, board)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "footprints" and len(sys.argv) == 4:
        footprints(sys.argv[2], sys.argv[3])
    elif command == "build" and len(sys.argv) == 3:
        build(sys.argv[2])
    elif command == "rules" and len(sys.argv) == 3:
        rules(sys.argv[2])
    elif command == "import" and len(sys.argv) == 6:
        import_session(*sys.argv[2:6])
    elif command == "scene" and len(sys.argv) == 4:
        scene(*sys.argv[2:4])
    elif command == "demo-prepare" and len(sys.argv) == 4:
        demo_prepare(*sys.argv[2:4])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
