"""Layout stage: constraints, placer, and the place-route-check runner.

fixtures/layout/ldo.net is the KiCad netlist ldo_skidl.py writes: an AP2112K 3.3 V LDO with input and
output capacitors, a power LED, and two headers. The end-to-end tests need KiCad's pcbnew Python and
Freerouting, and skip without them.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "skills" / "layout"
sys.path.insert(0, str(LAYOUT))

from layout import kicad_python, netclasses_for, routed_checks, strip_outlines  # noqa: E402
from place import (  # noqa: E402
    DEFAULT_RULES,
    Problem,
    box_gap,
    parse_netlist,
    parse_sexpr,
    place,
    rotate,
    semantic_errors,
)
from rules import apply_general_rules, copper_width_mm  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "layout" / "ldo.net"
SCHEMA = json.loads((LAYOUT / "schemas" / "constraints.schema.json").read_text())

LDO_CONSTRAINTS = {
    "constraints": [
        {"type": "proximity", "components": ["U1", "C1"], "max_distance_mm": 1.5, "weight": 3, "hard": True},
        {"type": "proximity", "components": ["U1", "C2"], "max_distance_mm": 1.5, "weight": 3, "hard": True},
        {"type": "board_edge", "component": "J1", "preferred_edge": "left", "hard": True},
        {"type": "board_edge", "component": "J2", "preferred_edge": "right", "hard": True},
        {"type": "group", "components": ["R1", "D1"], "max_distance_mm": 2},
        {"type": "high_current", "nets": ["VIN", "VOUT"], "track_width_mm": 0.5},
        {"type": "orientation", "component": "J1", "rotation_deg": 0},
    ]
}


def chip(width, height):
    return {"courtyard": [-width / 2, -height / 2, width / 2, height / 2], "pads": {"1": [-width / 4, 0.0], "2": [width / 4, 0.0]}}


GEOMETRY = {"Chip:Small": chip(2.0, 1.2), "Chip:Big": chip(5.0, 4.0)}


def synthetic_netlist():
    components = [{"ref": "U1", "value": "", "footprint": "Chip:Big"}]
    components += [{"ref": f"C{i}", "value": "", "footprint": "Chip:Small"} for i in range(1, 5)]
    components += [{"ref": "J1", "value": "", "footprint": "Chip:Big"}]
    nets = {
        "VIN": [("J1", "1"), ("U1", "1"), ("C1", "1"), ("C2", "1")],
        "VOUT": [("U1", "2"), ("C3", "1"), ("C4", "1")],
        "GND": [("J1", "2"), ("C1", "2"), ("C2", "2"), ("C3", "2"), ("C4", "2")],
    }
    return {"components": components, "nets": nets}


def solve(constraints, board_max=None, seed=1, extra_gap=0.0):
    problem = Problem(synthetic_netlist(), GEOMETRY, constraints, board_max, extra_gap_mm=extra_gap)
    return problem, place(problem, seed=seed, steps=6000)


def courtyards(problem, result):
    return {ref: problem.courtyard(ref, spot) for ref, spot in result["parts"].items()}


# Netlist


def test_parse_sexpr_keeps_quoted_spaces_and_escapes():
    assert parse_sexpr('(a "b c" (d "e \\"f\\""))') == [["a", "b c", ["d", 'e "f"']]]


def test_parse_netlist_reads_skidl_kicad_netlist():
    netlist = parse_netlist(FIXTURE.read_text())
    refs = {c["ref"]: c for c in netlist["components"]}
    assert set(refs) == {"C1", "C2", "D1", "J1", "J2", "R1", "U1"}
    assert refs["U1"]["footprint"] == "Package_TO_SOT_SMD:SOT-23-5"
    assert refs["D1"]["part"] == "LED"
    assert refs["D1"]["description"] == "Light emitting diode"
    assert sorted(netlist["nets"]["VIN"]) == [("C1", "1"), ("J1", "1"), ("U1", "1"), ("U1", "3")]


# Constraints


def test_ldo_constraints_match_schema():
    jsonschema.validate(LDO_CONSTRAINTS, SCHEMA)


@pytest.mark.parametrize("bad", [
    {"type": "proximity", "components": ["U1", "C1"]},
    {"type": "proximity", "components": ["U1"], "max_distance_mm": 1},
    {"type": "differential_pair", "nets": ["A", "B", "C"]},
    {"type": "high_current", "nets": ["VIN"]},
    {"type": "keepout", "edge": "top"},
    {"type": "orientation", "component": "J1", "rotation_deg": 45},
    {"type": "board_edge", "component": "J1", "preferred_edge": "left", "x_mm": 3},
])
def test_schema_rejects_incomplete_or_coordinate_constraints(bad):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"constraints": [bad]}, SCHEMA)


def test_semantic_errors_name_unknown_parts_and_nets():
    netlist = parse_netlist(FIXTURE.read_text())
    errors = semantic_errors({"constraints": [
        {"type": "proximity", "components": ["U1", "C9"], "max_distance_mm": 1},
        {"type": "high_current", "nets": ["VBAT"], "track_width_mm": 1},
    ]}, netlist)
    assert any("C9" in e for e in errors)
    assert any("VBAT" in e for e in errors)


def test_semantic_errors_catch_conflicting_hard_rotations():
    netlist = parse_netlist(FIXTURE.read_text())
    errors = semantic_errors({"constraints": [
        {"type": "orientation", "component": "J1", "rotation_deg": 0, "hard": True},
        {"type": "orientation", "component": "J1", "rotation_deg": 90, "hard": True},
    ]}, netlist)
    assert len(errors) == 1 and "J1" in errors[0]


def test_semantic_errors_check_rules():
    netlist = parse_netlist(FIXTURE.read_text())
    errors = semantic_errors({"rules": {"track_width_mm": 0.2, "min_track_width_mm": 0.3}, "constraints": []}, netlist)
    assert errors == ["rules: min_track_width_mm is larger than track_width_mm"]


def test_copper_width_follows_ipc2221():
    assert copper_width_mm(0.1) is None
    assert copper_width_mm(1) == 0.3
    assert copper_width_mm(2) == 0.8
    assert copper_width_mm(3) == 1.3


def test_general_rules_cover_io_decoupling_and_supply_width():
    netlist = parse_netlist(FIXTURE.read_text())
    merged, added = apply_general_rules({"constraints": []}, netlist, {"output_current_a": 2})
    jsonschema.validate(merged, SCHEMA)
    edges = {c["component"]: c["preferred_edge"] for c in merged["constraints"] if c["type"] == "board_edge"}
    assert edges == {"J1": "left", "J2": "right", "D1": "top"}
    assert all(c["hard"] for c in merged["constraints"] if c["type"] == "board_edge")
    proximity = next(c for c in merged["constraints"] if c["type"] == "proximity")
    assert proximity["components"][0] == "U1"
    assert set(proximity["components"]) == {"U1", "C1", "C2"}
    assert proximity["hard"] is True and proximity["max_distance_mm"] == 2
    high = next(c for c in merged["constraints"] if c["type"] == "high_current")
    assert high["track_width_mm"] == 0.8
    assert set(high["nets"]) == {"VIN", "VOUT", "GND"}
    assert added == merged["constraints"]


def test_general_rules_keep_constraints_the_model_wrote():
    netlist = parse_netlist(FIXTURE.read_text())
    merged, added = apply_general_rules(LDO_CONSTRAINTS, netlist, {})
    edges = [c for c in merged["constraints"] if c["type"] == "board_edge" and c.get("component") == "J1"]
    assert edges == [{"type": "board_edge", "component": "J1", "preferred_edge": "left", "hard": True}]
    proximity = [c for c in merged["constraints"] if c["type"] == "proximity" and "C1" in c["components"]]
    assert len(proximity) == 1 and proximity[0]["max_distance_mm"] == 1.5
    assert any(c["type"] == "board_edge" and c.get("component") == "D1" for c in added)
    assert not any(c["type"] == "high_current" for c in added)
    jsonschema.validate(merged, SCHEMA)


def test_general_rules_are_idempotent():
    netlist = parse_netlist(FIXTURE.read_text())
    once, _ = apply_general_rules({"constraints": []}, netlist, {"output_current_a": 2})
    twice, added = apply_general_rules(once, netlist, {"output_current_a": 2})
    assert added == []
    assert twice["constraints"] == once["constraints"]


def _part(ref, value, description, part):
    return {"ref": ref, "value": value, "description": description, "footprint": "Chip:Small", "lib": "Device", "part": part}


def test_general_rules_add_a_switch_loop_a_pair_and_leave_a_power_diode_inside():
    netlist = {
        "components": [
            _part("U1", "buck", "buck regulator", "U"),
            _part("L1", "10uH", "Inductor", "L"),
            _part("D1", "SS34", "Schottky diode", "D"),
            _part("C1", "10uF", "Unpolarized capacitor", "C"),
            _part("C2", "22uF", "Unpolarized capacitor", "C"),
            _part("U2", "opamp", "operational amplifier", "U"),
            _part("J1", "USB", "USB connector", "Conn"),
        ],
        "nets": {
            "VIN": [("U1", "1"), ("C1", "1"), ("J1", "1")],
            "GND": [("U1", "2"), ("C1", "2"), ("C2", "2"), ("D1", "2"), ("J1", "2")],
            "SW": [("U1", "3"), ("L1", "1"), ("D1", "1")],
            "VOUT": [("L1", "2"), ("C2", "1"), ("U1", "4")],
            "USB_D_P": [("J1", "3"), ("U2", "1")],
            "USB_D_N": [("J1", "4"), ("U2", "2")],
        },
    }
    merged, _ = apply_general_rules({"constraints": []}, netlist, {"output_current_a": 1})
    jsonschema.validate(merged, SCHEMA)
    assert all(c.get("component") != "D1" for c in merged["constraints"] if c["type"] == "board_edge")
    loop = next(c for c in merged["constraints"] if c["type"] == "loop_area")
    assert loop["components"] == ["C1", "U1", "D1"]
    pair = next(c for c in merged["constraints"] if c["type"] == "differential_pair")
    assert pair["nets"] == ["USB_D_P", "USB_D_N"] and pair["max_skew_mm"] == 5
    apart = next(c for c in merged["constraints"] if c["type"] == "separation")
    assert apart["components"] == ["L1"] and "U2" in apart["from"] and apart["min_distance_mm"] == 5
    high = next(c for c in merged["constraints"] if c["type"] == "high_current")
    assert high["track_width_mm"] == 0.3
    assert "SW" in high["nets"] and "USB_D_P" not in high["nets"]


def test_generated_rules_place_without_a_hard_miss():
    netlist = synthetic_netlist()
    for comp in netlist["components"]:
        comp.setdefault("value", "")
        comp.setdefault("description", "")
    merged, _ = apply_general_rules({"constraints": []}, netlist, {"output_current_a": 0.1})
    problem = Problem(netlist, GEOMETRY, merged, None)
    result = place(problem, seed=1, steps=6000)
    assert result["legal"], result["violations"]


# Placer


def test_rotation_matches_kicad():
    x, y = rotate(-1.1375, -0.95, 90)
    assert (round(x, 4), round(y, 4)) == (-0.95, 1.1375)


def test_placement_has_no_overlap_and_is_legal():
    problem, result = solve({"constraints": []})
    assert result["legal"], result["violations"]
    boxes = courtyards(problem, result)
    refs = sorted(boxes)
    gap = DEFAULT_RULES["part_gap_mm"]
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            ba, bb = boxes[a], boxes[b]
            apart_x = ba[2] + gap <= bb[0] + 1e-6 or bb[2] + gap <= ba[0] + 1e-6
            apart_y = ba[3] + gap <= bb[1] + 1e-6 or bb[3] + gap <= ba[1] + 1e-6
            assert apart_x or apart_y, (a, b)


def test_outline_wraps_parts_with_edge_clearance():
    problem, result = solve({"constraints": []})
    boxes = courtyards(problem, result).values()
    x0, y0, x1, y1 = result["outline_mm"]
    clearance = DEFAULT_RULES["edge_clearance_mm"]
    assert min(b[0] for b in boxes) == pytest.approx(x0 + clearance, abs=1e-3)
    assert max(b[3] for b in boxes) == pytest.approx(y1 - clearance, abs=1e-3)


def test_hard_proximity_holds():
    constraints = {"constraints": [{"type": "proximity", "components": ["U1", "C1", "C2"], "max_distance_mm": 1.0, "hard": True}]}
    problem, result = solve(constraints)
    assert result["legal"], result["violations"]
    boxes = courtyards(problem, result)
    assert box_gap(boxes["U1"], boxes["C1"]) <= 1.0 + 1e-6
    assert box_gap(boxes["U1"], boxes["C2"]) <= 1.0 + 1e-6


def test_hard_board_edge_holds():
    constraints = {"constraints": [{"type": "board_edge", "component": "J1", "preferred_edge": "left", "hard": True}]}
    problem, result = solve(constraints)
    assert result["legal"], result["violations"]
    j1 = courtyards(problem, result)["J1"]
    assert j1[0] - (result["outline_mm"][0] + DEFAULT_RULES["edge_clearance_mm"]) <= 0.5 + 1e-6


def test_hard_orientation_fixes_rotation():
    constraints = {"constraints": [{"type": "orientation", "components": ["C1", "C2"], "rotation_deg": 90, "hard": True}]}
    _, result = solve(constraints)
    assert result["parts"]["C1"]["rotation"] == 90
    assert result["parts"]["C2"]["rotation"] == 90


def test_hard_separation_holds():
    constraints = {"constraints": [{"type": "separation", "components": ["C3", "C4"], "from": ["J1"], "min_distance_mm": 4, "hard": True}]}
    problem, result = solve(constraints)
    assert result["legal"], result["violations"]
    boxes = courtyards(problem, result)
    assert min(box_gap(boxes[r], boxes["J1"]) for r in ("C3", "C4")) >= 4 - 1e-6


def test_keepout_widens_that_edge():
    constraints = {"constraints": [{"type": "keepout", "edge": "top", "depth_mm": 3}]}
    problem, result = solve(constraints)
    top = min(b[1] for b in courtyards(problem, result).values())
    assert top - result["outline_mm"][1] == pytest.approx(DEFAULT_RULES["edge_clearance_mm"] + 3, abs=1e-3)


def test_board_too_small_is_illegal():
    _, result = solve({"constraints": []}, board_max={"width": 5, "height": 5})
    assert not result["legal"]
    assert any(v["type"] == "board_size" for v in result["violations"])


def test_board_max_accepts_either_orientation():
    _, roomy = solve({"constraints": []})
    w, h = roomy["board_mm"]["width"], roomy["board_mm"]["height"]
    _, result = solve({"constraints": []}, board_max={"width": min(w, h) + 2, "height": max(w, h) + 2})
    assert result["legal"], result["violations"]


def test_soft_violation_is_reported_but_legal():
    constraints = {"constraints": [{"type": "proximity", "components": ["C3", "J1"], "max_distance_mm": 0.0}]}
    _, result = solve(constraints)
    assert result["legal"]
    soft = [v for v in result["violations"] if v["type"] == "proximity"]
    assert len(soft) == 1 and soft[0]["hard"] is False


def test_retry_gap_skips_proximity_pairs():
    constraints = {"constraints": [{"type": "proximity", "components": ["U1", "C1"], "max_distance_mm": 0.8, "hard": True}]}
    problem, result = solve(constraints, extra_gap=2.0)
    assert result["legal"], result["violations"]
    assert problem.gap("U1", "C1") == DEFAULT_RULES["part_gap_mm"]
    assert problem.gap("U1", "C3") == DEFAULT_RULES["part_gap_mm"] + 2.0


def test_same_seed_same_placement():
    _, first = solve({"constraints": []}, seed=7)
    _, second = solve({"constraints": []}, seed=7)
    assert first["parts"] == second["parts"]


# Runner helpers


def test_strip_outlines_keeps_boundary_and_pads():
    dsn = "(pcb (structure (boundary (path pcb 0 0 0 10 10))) (library (image R (outline (path signal 50 0 0 1 1)) (pin Rect 1 0 0))))"
    stripped = strip_outlines(dsn)
    assert "(outline" not in stripped
    assert "(boundary (path pcb 0 0 0 10 10))" in stripped
    assert "(pin Rect 1 0 0)" in stripped


def test_netclasses_group_high_current_nets_by_width():
    constraints = {"constraints": [
        {"type": "high_current", "nets": ["VIN", "VOUT"], "track_width_mm": 0.5},
        {"type": "high_current", "nets": ["VBUS"], "track_width_mm": 1.0},
        {"type": "high_current", "nets": ["VOUT"], "track_width_mm": 0.8},
    ]}
    classes = netclasses_for(constraints, DEFAULT_RULES)
    assert [(c["nets"], c["track_width_mm"]) for c in classes] == [(["VIN"], 0.5), (["VOUT"], 0.8), (["VBUS"], 1.0)]
    assert all(c["via_drill_mm"] < c["via_diameter_mm"] for c in classes)


def test_high_current_allows_neckdown_only_near_pads():
    constraints = {"constraints": [{"type": "high_current", "nets": ["VIN"], "track_width_mm": 0.5}]}
    necked = {"nets": {"VIN": {"body_min_width_mm": 0.5, "segments": [{"width_mm": 0.375, "length_mm": 0.4, "near_pad": True}]}}}
    thin = {"nets": {"VIN": {"body_min_width_mm": 0.3, "segments": [{"width_mm": 0.3, "length_mm": 4.0, "near_pad": False}]}}}
    assert routed_checks(constraints, necked)[0]["status"] == "pass"
    assert routed_checks(constraints, thin)[0]["status"] == "fail"


def test_differential_pair_skew():
    constraints = {"constraints": [{"type": "differential_pair", "nets": ["D+", "D-"], "max_skew_mm": 0.5}]}
    stats = {"nets": {"D+": {"length_mm": 10.0}, "D-": {"length_mm": 10.8}}}
    assert routed_checks(constraints, stats)[0]["status"] == "fail"


# End to end


def have_kicad():
    try:
        kicad_python()
    except Exception:
        return False
    return shutil.which("kicad-cli") is not None and (ROOT / ".tools" / "freerouting" / "freerouting-cli").is_file()


needs_kicad = pytest.mark.skipif(not have_kicad(), reason="needs KiCad pcbnew, kicad-cli, and Freerouting")


def make_design(tmp_path, constraints, board_max):
    root = tmp_path / "ldo"
    for folder in ("design", "parts", "layout"):
        (root / folder).mkdir(parents=True)
    spec = {"prompt": "5 V to 3.3 V LDO with power LED", "supply_voltage_v": 5, "output_voltage_v": 3.3}
    if board_max:
        spec["board_max_mm"] = board_max
    (root / "design" / "circuit-spec.json").write_text(json.dumps(spec))
    shutil.copy(FIXTURE, root / "parts" / "board.net")
    (root / "layout" / "constraints.json").write_text(json.dumps(constraints))
    return root


def run_layout(root):
    return subprocess.run(
        [sys.executable, str(LAYOUT / "layout.py"), str(root)],
        capture_output=True,
        text=True,
        timeout=1200,
    )


@needs_kicad
def test_ldo_board_places_routes_and_passes(tmp_path):
    root = make_design(tmp_path, LDO_CONSTRAINTS, {"width": 25, "height": 20})
    proc = run_layout(root)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    layout = root / "layout"
    for name in ("placement.json", "placed.kicad_pcb", "placement.png", "board.dsn", "board.ses", "board.kicad_pcb", "board.kicad_pro", "board.png", "drc.json", "report.json"):
        assert (layout / name).is_file(), name
    report = json.loads((layout / "report.json").read_text())
    assert report["status"] == "pass"
    assert report["return_to"] is None
    assert report["routing"]["unrouted"] == 0
    assert report["drc"]["errors"] == []
    assert max(report["board_mm"].values()) <= 25 and min(report["board_mm"].values()) <= 20
    assert all(check["status"] == "pass" for check in report["checks"])
    assert not any(v["hard"] for v in report["placement"]["violations"])
    drc = json.loads((layout / "drc.json").read_text())
    assert not [v for v in drc["violations"] if v["severity"] == "error"]
    assert drc["unconnected_items"] == []
    assert '"min_track_width": 0.15' in (layout / "board.kicad_pro").read_text()


@needs_kicad
def test_board_that_cannot_fit_goes_back_to_constraints(tmp_path):
    root = make_design(tmp_path, LDO_CONSTRAINTS, {"width": 8, "height": 6})
    proc = run_layout(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    report = json.loads((root / "layout" / "report.json").read_text())
    assert report["status"] == "fail"
    assert report["return_to"] == "constraints"
    assert all(a["stage"] == "placement" for a in report["attempts"])
    assert any("larger than" in reason for reason in report["reasons"])
    assert not (root / "layout" / "board.kicad_pcb").exists()


@needs_kicad
def test_unknown_part_in_constraints_is_no_board(tmp_path):
    constraints = {"constraints": [{"type": "proximity", "components": ["U1", "C7"], "max_distance_mm": 1}]}
    root = make_design(tmp_path, constraints, None)
    proc = run_layout(root)
    assert proc.returncode == 2
    assert "C7 is not a component in board.net" in proc.stderr
    assert not (root / "layout" / "report.json").exists()


def test_missing_netlist_is_no_board(tmp_path):
    root = tmp_path / "empty"
    (root / "layout").mkdir(parents=True)
    (root / "layout" / "constraints.json").write_text(json.dumps({"constraints": []}))
    proc = run_layout(root)
    assert proc.returncode == 2
    assert "board.net does not exist" in proc.stderr
