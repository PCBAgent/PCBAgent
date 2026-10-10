"""Generate the Astra-inspired educational BLDC KiCad demo project.

The generator keeps UUIDs, component placement, and routing deterministic so
the project can be regenerated and mechanically checked without KiCad.
"""

from __future__ import annotations

import csv
import json
import math
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID("6bcfbf9c-9ad8-4e0d-a1e9-7a72eeae09c6")


def uid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


COMPONENTS = [
    ("J1", "POWER IN 12V", "TerminalBlock_2_P5.08mm", [("1", "VIN"), ("2", "GND")]),
    ("F1", "2A RESETTABLE", "Fuse_1206_3216Metric", [("1", "VIN"), ("2", "VBUS")]),
    ("D1", "SMBJ18A TVS", "D_SMA", [("1", "GND"), ("2", "VBUS")]),
    ("C1", "100uF 25V", "CP_Elec_8x10.2", [("1", "VBUS"), ("2", "GND")]),
    ("C2", "100nF", "C_0603_1608Metric", [("1", "VBUS"), ("2", "GND")]),
    ("U1", "R-78E3.3-0.5", "Converter_DCDC_RECOM_R-78E-0.5_THT", [("1", "VBUS"), ("2", "GND"), ("3", "+3V3")]),
    ("C3", "10uF", "C_0805_2012Metric", [("1", "+3V3"), ("2", "GND")]),
    (
        "U2",
        "STM32G031K8Tx",
        "LQFP-32_7x7mm_P0.8mm",
        [
            ("1", "BOOT0"), ("4", "NRST"), ("5", "+3V3"), ("6", "SPEED"),
            ("7", "HALL_A"), ("8", "HALL_B"), ("9", "HALL_C"),
            ("12", "PWM_A"), ("14", "PWM_B"), ("16", "GND"), ("17", "+3V3"),
            ("18", "PWM_C"), ("21", "NSLEEP"), ("22", "NFAULT"),
            ("23", "SWDIO"), ("24", "SWCLK"), ("29", "LED_STATUS"),
            ("31", "GND"), ("32", "+3V3"),
        ],
    ),
    (
        "U3",
        "DRV8313PWP",
        "HTSSOP-28-1EP_4.4x9.7mm_P0.65mm",
        [
            ("1", "NSLEEP"), ("2", "PWM_A"), ("3", "PWM_B"), ("4", "PWM_C"),
            ("5", "NFAULT"), ("6", "+3V3"), ("7", "GND"),
            ("9", "PHASE_A"), ("10", "PHASE_A"), ("11", "VBUS"),
            ("12", "VBUS"), ("13", "PHASE_B"), ("14", "PHASE_B"),
            ("15", "GND"), ("17", "PHASE_C"), ("18", "PHASE_C"),
            ("19", "VBUS"), ("20", "VBUS"), ("21", "GND"), ("29", "GND"),
        ],
    ),
    ("C4", "100nF", "C_0603_1608Metric", [("1", "VBUS"), ("2", "GND")]),
    ("C5", "10uF 25V", "C_0805_2012Metric", [("1", "VBUS"), ("2", "GND")]),
    ("R1", "10k", "R_0603_1608Metric", [("1", "+3V3"), ("2", "NFAULT")]),
    ("R2", "10k", "R_0603_1608Metric", [("1", "+3V3"), ("2", "NSLEEP")]),
    ("R3", "1k", "R_0603_1608Metric", [("1", "LED_STATUS"), ("2", "LED_A")]),
    ("D2", "GREEN", "LED_0603_1608Metric", [("1", "GND"), ("2", "LED_A")]),
    ("RV1", "10k SPEED", "Potentiometer_Alps_RK09K_Single_Horizontal", [("1", "GND"), ("2", "SPEED"), ("3", "+3V3")]),
    ("J2", "MOTOR A B C", "TerminalBlock_3_P5.08mm", [("1", "PHASE_A"), ("2", "PHASE_B"), ("3", "PHASE_C")]),
    ("J3", "HALL SENSORS", "PinHeader_1x05_P2.54mm_Vertical", [("1", "+3V3"), ("2", "GND"), ("3", "HALL_A"), ("4", "HALL_B"), ("5", "HALL_C")]),
    ("J4", "SWD", "PinHeader_1x05_P2.54mm_Vertical", [("1", "+3V3"), ("2", "SWDIO"), ("3", "SWCLK"), ("4", "NRST"), ("5", "GND")]),
    ("R4", "10k", "R_0603_1608Metric", [("1", "BOOT0"), ("2", "GND")]),
    ("R5", "10k", "R_0603_1608Metric", [("1", "NRST"), ("2", "+3V3")]),
    ("C6", "100nF", "C_0603_1608Metric", [("1", "NRST"), ("2", "GND")]),
]


def q(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def write_project() -> None:
    project = {
        "board": {},
        "boards": [],
        "cvpcb": {},
        "erc": {},
        "libraries": {},
        "meta": {"filename": "astra-bldc.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12,
                    "clearance": 0.2,
                    "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.2,
                    "line_style": 0,
                    "microvia_diameter": 0.3,
                    "microvia_drill": 0.1,
                    "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 0.3,
                    "via_diameter": 0.8,
                    "via_drill": 0.4,
                    "wire_width": 6,
                },
                {
                    "bus_width": 12,
                    "clearance": 0.3,
                    "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.2,
                    "line_style": 0,
                    "microvia_diameter": 0.3,
                    "microvia_drill": 0.1,
                    "name": "POWER",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 1.0,
                    "via_diameter": 1.2,
                    "via_drill": 0.6,
                    "wire_width": 6,
                },
            ],
            "netclass_assignments": {
                "/PHASE_A": "POWER", "/PHASE_B": "POWER", "/PHASE_C": "POWER",
                "/VBUS": "POWER", "/VIN": "POWER",
            },
        },
        "pcbnew": {},
        "schematic": {},
        "sheets": [],
        "text_variables": {},
    }
    (ROOT / "astra-bldc.kicad_pro").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")


def symbol_definition(name: str, ref_prefix: str, pins: list[tuple[str, str]]) -> str:
    height = max(15.24, (max(len(pins), 2) + 1) * 2.54 / 2)
    pin_defs = []
    left_count = math.ceil(len(pins) / 2)
    for idx, (number, pin_name) in enumerate(pins):
        if idx < left_count:
            y = (left_count - 1) * 1.27 - idx * 2.54
            at = f"-12.7 {y:.2f} 0"
        else:
            ridx = idx - left_count
            right_count = len(pins) - left_count
            y = (right_count - 1) * 1.27 - ridx * 2.54
            at = f"12.7 {y:.2f} 180"
        pin_defs.append(
            f'''      (pin passive line (at {at}) (length 2.54)
        (name "{q(pin_name)}" (effects (font (size 1.0 1.0))))
        (number "{q(number)}" (effects (font (size 1.0 1.0)))))'''
        )
    return f'''    (symbol "Astra:{name}"
      (pin_names (offset 0.8))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "{ref_prefix}" (at 0 {height / 2 + 2.54:.2f} 0)
        (effects (font (size 1.27 1.27))))
      (property "Value" "{name}" (at 0 {-height / 2 - 2.54:.2f} 0)
        (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Description" "Astra BLDC demo symbol" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "{name}_0_1"
        (rectangle (start -10.16 {height / 2:.2f}) (end 10.16 {-height / 2:.2f})
          (stroke (width 0) (type default)) (fill (type background))))
      (symbol "{name}_1_1"
{chr(10).join(pin_defs)})
    )'''


def write_schematic() -> None:
    defs = []
    seen_symbols = set()
    for ref, value, _footprint, pins in COMPONENTS:
        lib_name = value.replace(" ", "_").replace("+", "P").replace(".", "_")
        if lib_name not in seen_symbols:
            defs.append(symbol_definition(lib_name, ref[0], pins))
            seen_symbols.add(lib_name)

    # Place in functional columns: power, controller, driver/output, interfaces.
    positions = {
        "J1": (25, 35), "F1": (55, 35), "D1": (55, 58), "C1": (80, 58),
        "C2": (100, 58), "U1": (90, 35), "C3": (120, 35),
        "U2": (145, 85), "U3": (205, 85), "C4": (205, 120), "C5": (230, 120),
        "R1": (180, 125), "R2": (165, 125), "R3": (135, 135), "D2": (155, 135),
        "RV1": (90, 105), "J2": (260, 85), "J3": (90, 155), "J4": (145, 165),
        "R4": (120, 120), "R5": (125, 155), "C6": (155, 155),
    }
    instances = []
    wires = []
    labels = []
    for ref, value, footprint, pins in COMPONENTS:
        x, y = positions[ref]
        lib_name = value.replace(" ", "_").replace("+", "P").replace(".", "_")
        inst_pins = []
        left_count = math.ceil(len(pins) / 2)
        for idx, (number, net) in enumerate(pins):
            if idx < left_count:
                py = y + (left_count - 1) * 1.27 - idx * 2.54
                px = x - 12.7
                ex = px - 5.08
            else:
                ridx = idx - left_count
                right_count = len(pins) - left_count
                py = y + (right_count - 1) * 1.27 - ridx * 2.54
                px = x + 12.7
                ex = px + 5.08
            wires.append(
                f'''  (wire (pts (xy {px:.2f} {py:.2f}) (xy {ex:.2f} {py:.2f}))
    (stroke (width 0) (type default)) (uuid {uid(f"wire-{ref}-{number}")}))'''
            )
            justify = "right" if ex < x else "left"
            labels.append(
                f'''  (label "{net}" (at {ex:.2f} {py:.2f} 0)
    (effects (font (size 1.0 1.0)) (justify {justify} bottom))
    (uuid {uid(f"label-{ref}-{number}")}))'''
            )
            inst_pins.append(f'    (pin "{number}" (uuid {uid(f"schpin-{ref}-{number}")}))')
        instances.append(
            f'''  (symbol (lib_id "Astra:{lib_name}") (at {x} {y} 0) (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid {uid(f"symbol-{ref}")})
    (property "Reference" "{ref}" (at {x} {y - 12.7} 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "{q(value)}" (at {x} {y + 12.7} 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "Astra:{footprint}" (at {x} {y} 0)
      (effects (font (size 1.0 1.0)) hide))
    (property "Datasheet" "~" (at {x} {y} 0)
      (effects (font (size 1.0 1.0)) hide))
    (property "Description" "Educational BLDC demo component" (at {x} {y} 0)
      (effects (font (size 1.0 1.0)) hide))
{chr(10).join(inst_pins)}
    (instances
      (project "astra-bldc"
        (path "/{uid('schematic-root')}" (reference "{ref}") (unit 1)))))'''
        )

    notes = [
        (20, 18, "ASTRA BLDC — EDUCATIONAL 12 V / 2 A CONTROLLER", 2.4),
        (20, 24, "Hall-sensored six-step control • DRV8313 integrated 3-phase bridge", 1.3),
        (20, 190, "DEMO DESIGN — verify pin mapping, ERC/DRC and thermal limits before hardware use", 1.2),
    ]
    text_items = "\n".join(
        f'''  (text "{q(text)}" (exclude_from_sim no) (at {x} {y} 0)
    (effects (font (size {size} {size}) (bold yes)) (justify left bottom))
    (uuid {uid(f"text-{text}")}))'''
        for x, y, text, size in notes
    )
    content = f'''(kicad_sch (version 20231120) (generator eeschema)
  (uuid {uid("schematic-root")})
  (paper "A4")
  (lib_symbols
{chr(10).join(defs)}
  )
{chr(10).join(wires)}
{chr(10).join(labels)}
{text_items}
{chr(10).join(instances)}
  (sheet_instances (path "/" (page "1")))
)'''
    (ROOT / "astra-bldc.kicad_sch").write_text(content + "\n", encoding="utf-8")


# PCB helpers -----------------------------------------------------------------

NET_NAMES = sorted({net for _, _, _, pins in COMPONENTS for _, net in pins})
NET_ID = {"": 0, **{name: idx + 1 for idx, name in enumerate(NET_NAMES)}}

PLACEMENT = {
    "J1": (8, 28, 90), "F1": (18, 24, 0), "D1": (26, 34, 0), "C1": (24, 46, 0),
    "C2": (34, 43, 0), "U1": (38, 25, 0), "C3": (50, 25, 0),
    "U2": (52, 39, 0), "U3": (70, 39, 0), "C4": (64, 30, 0), "C5": (75, 29, 0),
    "R1": (61, 48, 0), "R2": (66, 49.5, 0), "R3": (47, 51, 0), "D2": (53, 51, 0),
    "RV1": (32, 57, 0), "J2": (84, 39, 90), "J3": (65, 57, 90), "J4": (46, 57, 90),
    "R4": (43, 32, 0), "R5": (43, 47, 0), "C6": (38, 48, 0),
}


def pad_line(number: str, x: float, y: float, net: str, smd: bool = True, size=(1.4, 1.4), drill=0.8) -> str:
    kind = "smd" if smd else "thru_hole"
    layers = '"F.Cu" "F.Paste" "F.Mask"' if smd else '"*.Cu" "*.Mask"'
    drill_part = "" if smd else f" (drill {drill})"
    shape = "roundrect" if smd else "circle"
    rr = " (roundrect_rratio 0.2)" if smd else ""
    return (
        f'    (pad "{number}" {kind} {shape} (at {x:.2f} {y:.2f}) '
        f'(size {size[0]} {size[1]}){drill_part} (layers {layers}){rr} '
        f'(net {NET_ID[net]} "{net}") (uuid {uid(f"pad-{CURRENT_REF}-{number}")}))'
    )


CURRENT_REF = ""


def footprint(ref: str, value: str, footprint_name: str, pins: list[tuple[str, str]]) -> str:
    global CURRENT_REF
    CURRENT_REF = ref
    x, y, rot = PLACEMENT[ref]
    pads = []
    pin_count = len(pins)
    through = ref.startswith("J") or ref == "RV1" or ref == "U1" or ref == "C1"

    if ref == "U2":
        pin_map = {n: net for n, net in pins}
        for n in range(1, 33):
            if n <= 8:
                px, py = -3.8, -2.8 + (n - 1) * 0.8
            elif n <= 16:
                px, py = -2.8 + (n - 9) * 0.8, 3.8
            elif n <= 24:
                px, py = 3.8, 2.8 - (n - 17) * 0.8
            else:
                px, py = 2.8 - (n - 25) * 0.8, -3.8
            pads.append(pad_line(str(n), px, py, pin_map.get(str(n), "")))
    elif ref == "U3":
        pin_map = {n: net for n, net in pins}
        for n in range(1, 29):
            side = -1 if n <= 14 else 1
            idx = n - 1 if n <= 14 else 28 - n
            pads.append(pad_line(str(n), side * 3.0, -4.225 + idx * 0.65, pin_map.get(str(n), ""), size=(1.65, 0.45)))
        pads.append(pad_line("29", 0, 0, "GND", size=(3.4, 5.5)))
    elif through:
        spacing = 5.08 if ref in {"J1", "J2"} else 2.54
        if ref == "RV1":
            coords = [(-5, 0), (0, 0), (5, 0)]
        else:
            coords = [(0, (i - (pin_count - 1) / 2) * spacing) for i in range(pin_count)]
        for (number, net), (px, py) in zip(pins, coords):
            pads.append(pad_line(number, px, py, net, smd=False, size=(2.2, 2.2), drill=1.0))
    else:
        if pin_count == 2:
            coords = [(-1.0, 0), (1.0, 0)]
        else:
            coords = [((i - (pin_count - 1) / 2) * 2.54, 0) for i in range(pin_count)]
        for (number, net), (px, py) in zip(pins, coords):
            pads.append(pad_line(number, px, py, net))

    body_w = 8 if ref in {"U2", "U3"} else max(4, pin_count * 1.8)
    body_h = 10 if ref in {"U2", "U3"} else 4
    return f'''  (footprint "Astra:{footprint_name}" (layer "F.Cu")
    (uuid {uid(f"footprint-{ref}")}) (at {x} {y} {rot})
    (property "Reference" "{ref}" (at 0 {-body_h / 2 - 1.5} {rot}) (layer "F.SilkS")
      (uuid {uid(f"fp-ref-{ref}")}) (effects (font (size 1 1) (thickness 0.15))))
    (property "Value" "{q(value)}" (at 0 {body_h / 2 + 1.5} {rot}) (layer "F.Fab")
      (uuid {uid(f"fp-value-{ref}")}) (effects (font (size 1 1) (thickness 0.15))))
    (fp_rect (start {-body_w / 2} {-body_h / 2}) (end {body_w / 2} {body_h / 2})
      (stroke (width 0.25) (type default)) (fill none) (layer "F.SilkS") (uuid {uid(f"fp-body-{ref}")}))
    (fp_circle (center {-body_w / 2 + 0.8} {-body_h / 2 + 0.8}) (end {-body_w / 2 + 1.2} {-body_h / 2 + 0.8})
      (stroke (width 0.2) (type default)) (fill none) (layer "F.SilkS") (uuid {uid(f"fp-pin1-{ref}")}))
{chr(10).join(pads)}
  )'''


def absolute_pad_positions() -> dict[str, list[tuple[float, float, str, str]]]:
    result: dict[str, list[tuple[float, float, str, str]]] = {}
    for ref, _value, _fp, pins in COMPONENTS:
        x, y, rot = PLACEMENT[ref]
        points: list[tuple[float, float, str, str]] = []
        if ref == "U2":
            pin_map = {n: net for n, net in pins}
            raw = []
            for n in range(1, 33):
                if n <= 8: p = (-3.8, -2.8 + (n - 1) * 0.8)
                elif n <= 16: p = (-2.8 + (n - 9) * 0.8, 3.8)
                elif n <= 24: p = (3.8, 2.8 - (n - 17) * 0.8)
                else: p = (2.8 - (n - 25) * 0.8, -3.8)
                raw.append((str(n), *p, pin_map.get(str(n), "")))
        elif ref == "U3":
            pin_map = {n: net for n, net in pins}
            raw = []
            for n in range(1, 29):
                side = -1 if n <= 14 else 1
                idx = n - 1 if n <= 14 else 28 - n
                raw.append((str(n), side * 3.0, -4.225 + idx * 0.65, pin_map.get(str(n), "")))
            raw.append(("29", 0, 0, "GND"))
        elif ref.startswith("J") or ref == "RV1" or ref == "U1" or ref == "C1":
            spacing = 5.08 if ref in {"J1", "J2"} else 2.54
            coords = [(-5, 0), (0, 0), (5, 0)] if ref == "RV1" else [(0, (i - (len(pins) - 1) / 2) * spacing) for i in range(len(pins))]
            raw = [(number, px, py, net) for (number, net), (px, py) in zip(pins, coords)]
        else:
            coords = [(-1.0, 0), (1.0, 0)] if len(pins) == 2 else [((i - (len(pins) - 1) / 2) * 2.54, 0) for i in range(len(pins))]
            raw = [(number, px, py, net) for (number, net), (px, py) in zip(pins, coords)]
        angle = math.radians(rot)
        for number, px, py, net in raw:
            ax = x + px * math.cos(angle) - py * math.sin(angle)
            ay = y + px * math.sin(angle) + py * math.cos(angle)
            points.append((round(ax, 3), round(ay, 3), number, net))
        result[ref] = points
    return result


def write_pcb() -> None:
    fps = [footprint(*component) for component in COMPONENTS]
    pads = absolute_pad_positions()
    by_net: dict[str, list[tuple[float, float, str, str]]] = {n: [] for n in NET_NAMES}
    for ref, points in pads.items():
        for x, y, number, net in points:
            if net:
                by_net[net].append((x, y, ref, number))

    segments = []
    vias = []
    # Deterministic Manhattan daisy-chain routes. GND is supplied by both zones.
    for net_index, (net, points) in enumerate(by_net.items()):
        if net == "GND" or len(points) < 2:
            continue
        width = 1.2 if net in {"VIN", "VBUS", "PHASE_A", "PHASE_B", "PHASE_C"} else (0.6 if net == "+3V3" else 0.3)
        use_bottom = width == 0.3 and net_index % 2 == 0
        for index, (a, b) in enumerate(zip(points, points[1:])):
            x1, y1, _, _ = a
            x2, y2, _, _ = b
            # Offset each route slightly to avoid visually stacking all paths.
            midx = round((x1 + x2) / 2 + ((index % 3) - 1) * 0.35, 3)
            if use_bottom:
                # Short top-layer escapes and two vias make alternate signal
                # routes visibly use both copper layers.
                escape = 1.2 if x2 >= x1 else -1.2
                va = (round(x1 + escape, 3), y1)
                vb = (round(x2 - escape, 3), y2)
                top_paths = [((x1, y1), va), (vb, (x2, y2))]
                bottom_pts = [va, (midx, y1), (midx, y2), vb]
                for top_idx, (p1, p2) in enumerate(top_paths):
                    segments.append(
                        f'''  (segment (start {p1[0]} {p1[1]}) (end {p2[0]} {p2[1]}) (width {width})
    (layer "F.Cu") (net {NET_ID[net]}) (uuid {uid(f"seg-top-{net}-{index}-{top_idx}")}))'''
                    )
                for via_idx, point in enumerate((va, vb)):
                    vias.append(
                        f'''  (via (at {point[0]} {point[1]}) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu")
    (net {NET_ID[net]}) (uuid {uid(f"via-{net}-{index}-{via_idx}")}))'''
                    )
                path_segments = list(zip(bottom_pts, bottom_pts[1:]))
                layer = "B.Cu"
            else:
                pts = [(x1, y1), (midx, y1), (midx, y2), (x2, y2)]
                path_segments = list(zip(pts, pts[1:]))
                layer = "F.Cu"
            for seg_idx, (p1, p2) in enumerate(path_segments):
                if p1 == p2:
                    continue
                segments.append(
                    f'''  (segment (start {p1[0]} {p1[1]}) (end {p2[0]} {p2[1]}) (width {width})
    (layer "{layer}") (net {NET_ID[net]}) (uuid {uid(f"seg-{net}-{index}-{seg_idx}")}))'''
                )
    # Six plated thermal vias tie the DRV8313 exposed pad into the bottom plane.
    for via_index, (dx, dy) in enumerate(
        [(-0.8, -1.6), (0, -1.6), (0.8, -1.6), (-0.8, 1.6), (0, 1.6), (0.8, 1.6)]
    ):
        vias.append(
            f'''  (via (at {70 + dx} {39 + dy}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu")
    (net {NET_ID["GND"]}) (uuid {uid(f"thermal-via-{via_index}")}))'''
        )

    outline = [
        ((5, 15), (85, 15)), ((85, 15), (90, 20)), ((90, 20), (90, 60)),
        ((90, 60), (85, 65)), ((85, 65), (5, 65)), ((5, 65), (2, 62)),
        ((2, 62), (2, 18)), ((2, 18), (5, 15)),
    ]
    edges = "\n".join(
        f'''  (gr_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]})
    (stroke (width 0.3) (type default)) (layer "Edge.Cuts") (uuid {uid(f"edge-{i}")}))'''
        for i, (a, b) in enumerate(outline)
    )
    mount_holes = []
    for i, (x, y) in enumerate([(7, 20), (85, 20), (7, 60), (85, 60)], 1):
        mount_holes.append(f'''  (footprint "MountingHole:MountingHole_3.2mm_M3" (layer "F.Cu")
    (uuid {uid(f"hole-{i}")}) (at {x} {y})
    (property "Reference" "H{i}" (at 0 -4 0) (layer "F.SilkS") hide
      (uuid {uid(f"hole-ref-{i}")}) (effects (font (size 1 1))))
    (property "Value" "M3" (at 0 4 0) (layer "F.Fab") hide
      (uuid {uid(f"hole-value-{i}")}) (effects (font (size 1 1))))
    (fp_circle (center 0 0) (end 3 0) (stroke (width 0.25) (type default)) (fill none) (layer "F.SilkS") (uuid {uid(f"hole-circle-{i}")}))
    (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask") (uuid {uid(f"hole-pad-{i}")}))
  )''')

    texts = [
        (46, 18, "ASTRA BLDC", 2.2),
        (46, 21, "12V EDUCATIONAL MOTOR CONTROLLER", 1.0),
        (8, 38, "POWER", 1.0), (83, 49, "MOTOR", 1.0),
        (65, 63, "HALL", 1.0), (46, 63, "SWD", 1.0),
        (46, 61, "DEMO • REV A", 1.0),
    ]
    graphics = "\n".join(
        f'''  (gr_text "{text}" (at {x} {y}) (layer "F.SilkS") (uuid {uid(f"pcb-text-{text}")})
    (effects (font (face "Arial") (size {size} {size}) (thickness 0.2))))'''
        for x, y, text, size in texts
    )
    zones = f'''  (zone (net {NET_ID["GND"]}) (net_name "GND") (layer "B.Cu") (uuid {uid("gnd-zone-bottom")}) (hatch edge 0.5)
    (connect_pads (clearance 0.3)) (min_thickness 0.25) (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.3))
    (polygon (pts (xy 3 19) (xy 6 16) (xy 84 16) (xy 89 21) (xy 89 59) (xy 84 64) (xy 6 64) (xy 3 61))))
  (zone (net {NET_ID["GND"]}) (net_name "GND") (layer "F.Cu") (uuid {uid("gnd-zone-top")}) (hatch edge 0.5)
    (connect_pads (clearance 0.4)) (min_thickness 0.25) (fill yes (thermal_gap 0.35) (thermal_bridge_width 0.35))
    (polygon (pts (xy 3 19) (xy 6 16) (xy 84 16) (xy 89 21) (xy 89 59) (xy 84 64) (xy 6 64) (xy 3 61))))'''

    content = f'''(kicad_pcb (version 20240108) (generator pcbnew)
  (general (thickness 1.6))
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "B.SilkS" user "b.silkscreen")
    (37 "F.SilkS" user "f.silkscreen")
    (44 "Edge.Cuts" user))
  (setup (pad_to_mask_clearance 0))
  (net 0 "")
{chr(10).join(f'  (net {NET_ID[n]} "{n}")' for n in NET_NAMES)}
{chr(10).join(fps)}
{chr(10).join(mount_holes)}
{edges}
{graphics}
{chr(10).join(segments)}
{chr(10).join(vias)}
{zones}
)'''
    (ROOT / "astra-bldc.kicad_pcb").write_text(content + "\n", encoding="utf-8")
    write_autoroute_input_board(content)
    write_demo_start_board(content)


def write_autoroute_input_board(finished_board: str) -> None:
    """Create a fixed-placement, unrouted input for the Freerouting test."""
    import re

    board = re.sub(r'^  \(segment .*\n    \(layer .*\n', "", finished_board, flags=re.MULTILINE)
    board = re.sub(r'^  \(via .*\n    \(net .*\n', "", board, flags=re.MULTILINE)
    board = board.replace('"DEMO • REV A"', '"FREEROUTING TEST INPUT"')
    (ROOT / "astra-bldc-autoroute-input.kicad_pcb").write_text(board + "\n", encoding="utf-8")


def write_demo_start_board(finished_board: str) -> None:
    """Create an unrouted native board for a KiCad mouse/keyboard demo."""
    import re

    start = finished_board
    start = re.sub(r'^  \(segment .*\n    \(layer .*\n', "", start, flags=re.MULTILINE)
    start = re.sub(r'^  \(via .*\n    \(net .*\n', "", start, flags=re.MULTILINE)

    # Arrange parts in functional groups, but leave obvious placement work for
    # M/R interaction. Every item remains a normal unlocked KiCad footprint.
    staging = {
        "J1": (12, 27, 90), "F1": (22, 20, 0), "D1": (30, 20, 0),
        "C1": (38, 20, 0), "C2": (46, 20, 0), "U1": (55, 20, 0),
        "C3": (65, 20, 0), "U2": (38, 39, 0), "U3": (65, 39, 0),
        "C4": (53, 31, 0), "C5": (75, 30, 0), "R1": (52, 48, 0),
        "R2": (59, 49, 0), "R3": (30, 50, 0), "D2": (38, 51, 0),
        "RV1": (20, 58, 0), "J2": (84, 39, 90), "J3": (68, 58, 90),
        "J4": (50, 58, 90), "R4": (28, 31, 0), "R5": (27, 42, 0),
        "C6": (20, 43, 0),
    }
    for ref, (new_x, new_y, new_rot) in staging.items():
        old_x, old_y, old_rot = PLACEMENT[ref]
        marker = f'(uuid {uid(f"footprint-{ref}")}) (at {old_x} {old_y} {old_rot})'
        replacement = f'(uuid {uid(f"footprint-{ref}")}) (at {new_x} {new_y} {new_rot})'
        assert marker in start, f"could not stage {ref}"
        start = start.replace(marker, replacement, 1)
    start = start.replace('"DEMO • REV A"', '"PLACE → ROUTE → REFILL"')
    (ROOT / "astra-bldc-demo-start.kicad_pcb").write_text(start + "\n", encoding="utf-8")


def write_bom() -> None:
    with (ROOT / "BOM.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Reference", "Value", "Footprint", "Purpose"])
        purposes = {
            "J1": "12 V power input", "F1": "Input overcurrent protection",
            "D1": "Input transient clamp", "U1": "3.3 V logic regulator",
            "U2": "Motor-control MCU", "U3": "Three-phase motor driver",
            "J2": "BLDC phase output", "J3": "Hall sensor interface",
            "J4": "SWD programming/debug", "RV1": "Speed command",
            "D2": "Status indicator",
        }
        for ref, value, fp, _pins in COMPONENTS:
            purpose = purposes.get(ref, "Decoupling / bias network")
            writer.writerow([ref, value, fp, purpose])


def write_readme() -> None:
    text = """# Astra BLDC — Educational KiCad Demo

An original KiCad project inspired by the PCB-layout sequence in the GPT-6 Astra launch demo. The public clip only identifies its board as **BLDC** and does not include design files, a schematic, or a BOM, so this project recreates the concept rather than claiming to be the source board.

## What is included

- Editable native KiCad schematic and two-layer PCB
- Unrouted `astra-bldc-demo-start.kicad_pcb` for a placement/routing playback
- Fixed-placement `astra-bldc-autoroute-input.kicad_pcb` for the DSN/Freerouting/SES test
- 12 V nominal input and approximately 2 A educational target
- STM32G031K8 controller and DRV8313 integrated three-phase driver
- Hall sensor header, speed potentiometer, SWD header, status LED
- Routed phase/power/control nets, top and bottom ground pours, and thermal pad
- Deterministic BOM and a reproducible generator in `tools/generate_project.py`

## Connectors

| Connector | Pins |
| --- | --- |
| J1 POWER IN | 1: +12 V, 2: GND |
| J2 MOTOR | 1: Phase A, 2: Phase B, 3: Phase C |
| J3 HALL | 1: 3V3, 2: GND, 3: Hall A, 4: Hall B, 5: Hall C |
| J4 SWD | 1: 3V3, 2: SWDIO, 3: SWCLK, 4: NRST, 5: GND |

## Architecture

`12 V input → fuse/TVS → DRV8313 → motor phases`

`12 V input → 3.3 V DC/DC → STM32 + Hall/SWD/control`

The MCU is intended to run Hall-sensored six-step commutation. Firmware is outside this PCB demo's scope.

## Open and validate

Open `astra-bldc.kicad_pro` with KiCad 8 or newer, refill zones with **B**, then inspect the schematic and PCB.

For an Astra-style hands-on sequence, open `astra-bldc-demo-start.kicad_pcb` and follow `DEMO.md`. All components are ordinary unlocked KiCad footprints: hover and press **M** to move, **R** to rotate, and **X** to route. The completed `astra-bldc.kicad_pcb` remains available as the reference end state.

For a no-interaction playback on Windows, double-click `run-demo.cmd`. If KiCad is missing, the launcher installs the current stable release with `winget`, enables KiCad's supported IPC API, and opens a disposable playback board. The external controller edits native board objects directly—placing footprints, adding tracks and vias, and filling copper—without controlling the mouse or keyboard.

To reproduce the external-autorouter workflow discussed by NextPCB, double-click `run-autorouter-test.cmd`. It performs `KiCad DSN export → Freerouting → KiCad SES import → DRC` and preserves every intermediate artifact. See `AUTOROUTER_TEST.md`.

The files were successfully parsed by KiCad CLI 10.0.6. The included `astra-bldc-erc.rpt` and `astra-bldc-drc.rpt` intentionally show warnings and violations because this remains a visual demo rather than a fabrication release. After making engineering corrections, rerun:

```powershell
kicad-cli sch erc astra-bldc.kicad_sch -o astra-bldc-erc.rpt
kicad-cli pcb drc astra-bldc.kicad_pcb -o astra-bldc-drc.rpt
```

## Safety and engineering status

**This is a demo design, not a fabrication release. Do not order or energize it without an engineer reviewing the actual DRV8313 and STM32 pin mapping, footprints, power dissipation, protection, creepage, current capacity, firmware fault handling, and component sourcing.** The schematic uses simplified custom symbols to keep the project self-contained. In particular, validate every IC pin against the current manufacturer datasheet and replace the illustrative DC/DC choice as required.
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def write_demo_guide() -> None:
    text = """# 15-second KiCad demo choreography

This sequence evokes the Astra PCB clip without reusing its board, footage, branding, or exact layout. Use the native `astra-bldc-demo-start.kicad_pcb` in KiCad's PCB Editor.

## Autonomous playback

1. Close unrelated dialogs and save other work.
2. Double-click `run-demo.cmd`.

No interaction is required after launch. If needed, the launcher installs KiCad through Windows Package Manager and the official `kicad-python` bindings first. It creates `astra-bldc-playback.kicad_pcb`, opens that board, and connects through KiCad's supported IPC API. The controller moves native footprints and progressively adds tracks and vias before filling the ground zones and saving the result. No screen coordinates or simulated input are used.

The console reports the current phase (`placement`, `routing`, `copper-fill`, or `complete`).

## Controls

- Pan: middle-mouse drag; zoom: mouse wheel
- Move the footprint under the cursor: **M**, move mouse, left-click
- Rotate the footprint under the cursor: **R**
- Start routing from a pad or ratsnest: **X**
- Place a via while routing: **V**
- Finish a route: **K** or double-click; cancel: **Esc**
- Refill the copper zones: **B**
- Toggle ratsnest: toolbar “Show board ratsnest”

## Suggested capture

1. **0–3 s — Placement:** box-select the controller cluster, then use **M**. Individually nudge U2, U3, J1, and J2; use **R** once on a connector.
2. **3–11 s — Routing:** hover a bright ratsnest endpoint and press **X**. Route PWM/control lines first, then the wider VBUS and motor-phase connections. Press **V** on one control route to change layers.
3. **11–13 s — Copper:** press **B** to refill the top and bottom GND zones.
4. **13–15 s — Reveal:** zoom to fit with **Home**, hide the ratsnest, then open the 3D Viewer with **Alt+3** if available.

The supplied completed board is a reference rather than a locked result. Its footprints, tracks, vias, text, and zones can all be selected and edited with normal KiCad mouse and keyboard operations.
"""
    (ROOT / "DEMO.md").write_text(text, encoding="utf-8")


def write_autorouter_guide() -> None:
    text = """# Freerouting orchestration test

This reproduces the workflow described in [NextPCB's GPT-6 Astra routing test](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test) on the educational BLDC board:

`KiCad fixed placement → Specctra DSN export → Freerouting → SES import → KiCad DRC`

## Run it

Double-click `run-autorouter-test.cmd`. The first run installs Java 25 and downloads Freerouting 2.5.0 if needed. Routing takes roughly one to two minutes on this machine and finishes by opening the imported board in KiCad.

## Preserved evidence

- `astra-bldc-autoroute-input.kicad_pcb`: fixed-placement, unrouted input
- `astra-bldc-autoroute-input.dsn`: KiCad's Specctra interchange export
- `astra-bldc-freerouted.ses`: Freerouting's routing session
- `astra-bldc-freerouted.kicad_pcb`: SES imported back into KiCad
- `astra-bldc-freerouting.log`: complete router execution history and score
- `astra-bldc-freerouted-drc.rpt`: independent KiCad DRC report

## Baseline result

Freerouting 2.5.0 started with 47 unrouted connections and completed 29, leaving 18 unrouted. It reported 32 pre-existing placement/footprint clearance violations and a score of 641.24 after approximately 67.2 seconds. KiCad's post-import DRC reported 142 violations and 42 unconnected items.

That is a valid hackathon result, not a fabrication-ready result. It demonstrates the same important distinction highlighted by NextPCB: the automation orchestrates the EDA workflow, while Freerouting performs the routing computation. Connecting some or all nets would still not establish electrical correctness, thermal adequacy, signal integrity, or manufacturability.
"""
    (ROOT / "AUTOROUTER_TEST.md").write_text(text, encoding="utf-8")


def main() -> None:
    write_project()
    write_schematic()
    write_pcb()
    write_bom()
    write_readme()
    write_demo_guide()
    write_autorouter_guide()
    print("Generated Astra BLDC KiCad demo project.")


if __name__ == "__main__":
    main()
