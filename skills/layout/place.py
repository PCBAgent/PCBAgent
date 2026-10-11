#!/usr/bin/env python3
"""Read board.net and constraints.json, choose part coordinates, and score a placement.

The placer starts from a force-directed layout and refines it with simulated annealing. Its cost covers
wire length, overlap, constraint violations, board area, and loop area. Coordinates are millimeters with
y pointing down, as in KiCad. Rotations are KiCad footprint orientations in degrees.
"""

import json
import math
import random
import re


DEFAULT_RULES = {
    "track_width_mm": 0.25,
    "min_track_width_mm": 0.15,
    "clearance_mm": 0.2,
    "via_diameter_mm": 0.6,
    "via_drill_mm": 0.3,
    "edge_clearance_mm": 0.5,
    "part_gap_mm": 0.5,
}

DEFAULT_WEIGHT = 1.0
DEFAULT_GROUP_GAP_MM = 3.0
DEFAULT_EDGE_GAP_MM = 0.5
HARD_FACTOR = 1000.0
OVERLAP_FACTOR = 5000.0
SIZE_FACTOR = 2000.0
AREA_FACTOR = 0.02
LOOP_FACTOR = 0.05
NET_BOOST = 4.0
EDGES = ("left", "right", "top", "bottom")
BOARD_ORIGIN_MM = (20.0, 20.0)


class LayoutError(Exception):
    pass


# Netlist


def parse_sexpr(text):
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)
    stack = [[]]
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            if len(stack) < 2:
                raise LayoutError("unbalanced ')' in s-expression")
            done = stack.pop()
            stack[-1].append(done)
        elif token.startswith('"'):
            stack[-1].append(token[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(token)
    if len(stack) != 1:
        raise LayoutError("unbalanced '(' in s-expression")
    return stack[0]


def children(node, name):
    return [item for item in node[1:] if isinstance(item, list) and item and item[0] == name]


def child_value(node, name):
    found = children(node, name)
    if not found or len(found[0]) < 2:
        return None
    return found[0][1]


def parse_netlist(text):
    tree = parse_sexpr(text)
    if not tree or not isinstance(tree[0], list) or tree[0][0] != "export":
        raise LayoutError("board.net is not a KiCad netlist: no (export ...) root")
    export = tree[0]
    components = []
    for section in children(export, "components"):
        for comp in children(section, "comp"):
            source = children(comp, "libsource")
            components.append({
                "ref": child_value(comp, "ref"),
                "value": child_value(comp, "value"),
                "description": child_value(comp, "description"),
                "footprint": child_value(comp, "footprint"),
                "lib": child_value(source[0], "lib") if source else None,
                "part": child_value(source[0], "part") if source else None,
            })
    nets = {}
    for section in children(export, "nets"):
        for net in children(section, "net"):
            name = child_value(net, "name")
            nodes = [(child_value(node, "ref"), child_value(node, "pin")) for node in children(net, "node")]
            nets[name] = nodes
    return {"components": components, "nets": nets}


# Constraints


def rules_from(constraints):
    rules = dict(DEFAULT_RULES)
    rules.update(constraints.get("rules") or {})
    return rules


def refs_of(constraint):
    refs = list(constraint.get("components") or [])
    if constraint.get("component"):
        refs.append(constraint["component"])
    return refs


def semantic_errors(constraints, netlist):
    """Problems a schema cannot see: unknown parts or nets, and constraints that contradict each other."""
    known_refs = {comp["ref"] for comp in netlist["components"]}
    known_nets = set(netlist["nets"])
    errors = []
    orientation = {}
    for index, constraint in enumerate(constraints.get("constraints", [])):
        label = f"constraints[{index}] ({constraint['type']})"
        for ref in refs_of(constraint) + list(constraint.get("from") or []):
            if ref not in known_refs:
                errors.append(f"{label}: {ref} is not a component in board.net")
        for net in constraint.get("nets") or []:
            if net not in known_nets:
                errors.append(f"{label}: {net} is not a net in board.net")
        if constraint["type"] == "orientation" and constraint.get("hard"):
            for ref in refs_of(constraint):
                previous = orientation.setdefault(ref, constraint["rotation_deg"])
                if previous != constraint["rotation_deg"]:
                    errors.append(f"{label}: {ref} already has a hard rotation of {previous}")
    rules = rules_from(constraints)
    if rules["min_track_width_mm"] > rules["track_width_mm"]:
        errors.append("rules: min_track_width_mm is larger than track_width_mm")
    if rules["via_drill_mm"] >= rules["via_diameter_mm"]:
        errors.append("rules: via_drill_mm must be smaller than via_diameter_mm")
    return errors


# Geometry


def rotate(x, y, degrees):
    angle = math.radians(degrees)
    c = round(math.cos(angle), 12)
    s = round(math.sin(angle), 12)
    return x * c + y * s, -x * s + y * c


def rotated_box(box, degrees):
    x0, y0, x1, y1 = box
    corners = [rotate(x, y, degrees) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    return min(xs), min(ys), max(xs), max(ys)


def box_gap(a, b):
    dx = max(0.0, b[0] - a[2], a[0] - b[2])
    dy = max(0.0, b[1] - a[3], a[1] - b[3])
    return math.hypot(dx, dy)


def box_overlap(a, b, margin):
    w = min(a[2], b[2]) - max(a[0], b[0]) + margin
    h = min(a[3], b[3]) - max(a[1], b[1]) + margin
    if w <= 0 or h <= 0:
        return 0.0
    return w * h


def hull_area(points):
    points = sorted(set(points))
    if len(points) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    area = 0.0
    for i, p in enumerate(hull):
        q = hull[(i + 1) % len(hull)]
        area += p[0] * q[1] - q[0] * p[1]
    return abs(area) / 2.0


class Problem:
    """Everything the cost function needs, built once per run."""

    def __init__(self, netlist, footprints, constraints, board_max_mm=None, extra_gap_mm=0.0):
        self.rules = rules_from(constraints)
        self.constraints = constraints.get("constraints", [])
        self.extra_gap = extra_gap_mm
        self.close_pairs = set()
        for constraint in self.constraints:
            refs = refs_of(constraint)
            if constraint["type"] == "proximity":
                self.close_pairs.update(frozenset((refs[0], ref)) for ref in refs[1:])
            elif constraint["type"] == "group":
                self.close_pairs.update(frozenset((a, b)) for a in refs for b in refs if a != b)
        self.refs = [comp["ref"] for comp in netlist["components"]]
        self.footprint_of = {comp["ref"]: comp["footprint"] for comp in netlist["components"]}
        self.geometry = {}
        for ref in self.refs:
            fpid = self.footprint_of[ref]
            if fpid not in footprints:
                raise LayoutError(f"no footprint geometry for {ref} ({fpid})")
            self.geometry[ref] = footprints[fpid]
        self.board_max = None
        if board_max_mm:
            width, height = board_max_mm["width"], board_max_mm["height"]
            self.board_max = (max(width, height), min(width, height))

        boost = {}
        for constraint in self.constraints:
            if constraint["type"] in ("high_current", "differential_pair"):
                for net in constraint["nets"]:
                    boost[net] = boost.get(net, 0.0) + NET_BOOST * constraint.get("weight", DEFAULT_WEIGHT)
        self.nets = []
        for name, nodes in netlist["nets"].items():
            pins = [(ref, pin) for ref, pin in nodes if ref in self.geometry]
            if len({ref for ref, _ in pins}) < 2:
                continue
            self.nets.append((name, pins, 1.0 + boost.get(name, 0.0)))

        self.margins = {edge: self.rules["edge_clearance_mm"] for edge in EDGES}
        for constraint in self.constraints:
            if constraint["type"] == "keepout":
                self.margins[constraint["edge"]] += constraint["depth_mm"]

        self.fixed_rotation = {}
        for constraint in self.constraints:
            if constraint["type"] == "orientation" and constraint.get("hard"):
                for ref in refs_of(constraint):
                    self.fixed_rotation[ref] = constraint["rotation_deg"]

    def gap(self, a, b):
        """Smallest courtyard gap allowed between a and b. Parts tied by proximity or group skip the retry gap."""
        if frozenset((a, b)) in self.close_pairs:
            return self.rules["part_gap_mm"]
        return self.rules["part_gap_mm"] + self.extra_gap

    def courtyard(self, ref, spot):
        x0, y0, x1, y1 = rotated_box(self.geometry[ref]["courtyard"], spot["rotation"])
        return x0 + spot["x"], y0 + spot["y"], x1 + spot["x"], y1 + spot["y"]

    def pad(self, ref, pin, spot):
        pads = self.geometry[ref]["pads"]
        px, py = pads.get(str(pin), (0.0, 0.0))
        rx, ry = rotate(px, py, spot["rotation"])
        return rx + spot["x"], ry + spot["y"]

    def outline(self, placement):
        boxes = [self.courtyard(ref, placement[ref]) for ref in self.refs]
        x0 = min(b[0] for b in boxes) - self.margins["left"]
        y0 = min(b[1] for b in boxes) - self.margins["top"]
        x1 = max(b[2] for b in boxes) + self.margins["right"]
        y1 = max(b[3] for b in boxes) + self.margins["bottom"]
        return x0, y0, x1, y1

    def evaluate(self, placement):
        """Return (total cost, cost terms, violations). A violation with hard true makes the placement illegal."""
        boxes = {ref: self.courtyard(ref, placement[ref]) for ref in self.refs}
        terms = {"wire_length": 0.0, "overlap": 0.0, "board_area": 0.0, "board_size": 0.0, "loop_area": 0.0, "constraints": 0.0}
        violations = []

        for name, pins, weight in self.nets:
            points = [self.pad(ref, pin, placement[ref]) for ref, pin in pins]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            terms["wire_length"] += weight * ((max(xs) - min(xs)) + (max(ys) - min(ys)))

        for i, a in enumerate(self.refs):
            for b in self.refs[i + 1:]:
                gap = self.gap(a, b)
                overlap = box_overlap(boxes[a], boxes[b], gap)
                if overlap > 0:
                    terms["overlap"] += OVERLAP_FACTOR * (overlap + overlap ** 0.5)
                    violations.append({
                        "type": "overlap",
                        "components": [a, b],
                        "hard": True,
                        "message": f"{a} and {b} courtyards are closer than {gap:g} mm",
                    })

        x0, y0, x1, y1 = self.outline(placement)
        width, height = x1 - x0, y1 - y0
        terms["board_area"] = AREA_FACTOR * width * height
        if self.board_max:
            long_side, short_side = max(width, height), min(width, height)
            excess = max(0.0, long_side - self.board_max[0]) + max(0.0, short_side - self.board_max[1])
            if excess > 1e-6:
                terms["board_size"] = SIZE_FACTOR * (excess + excess ** 2)
                violations.append({
                    "type": "board_size",
                    "hard": True,
                    "message": f"board is {width:.2f} x {height:.2f} mm, larger than {self.board_max[0]} x {self.board_max[1]} mm",
                })

        inner = (x0 + self.margins["left"], y0 + self.margins["top"], x1 - self.margins["right"], y1 - self.margins["bottom"])
        for index, constraint in enumerate(self.constraints):
            amount, message = self.violation(constraint, boxes, placement, inner)
            if constraint["type"] == "loop_area":
                centers = [(placement[ref]["x"], placement[ref]["y"]) for ref in refs_of(constraint)]
                terms["loop_area"] += LOOP_FACTOR * constraint.get("weight", DEFAULT_WEIGHT) * hull_area(centers)
            if amount <= 1e-6:
                continue
            hard = bool(constraint.get("hard"))
            weight = constraint.get("weight", DEFAULT_WEIGHT)
            factor = HARD_FACTOR if hard else 10.0
            terms["constraints"] += factor * weight * (amount + amount ** 2)
            violations.append({"type": constraint["type"], "constraint": index, "hard": hard, "amount": round(amount, 4), "message": message})

        return sum(terms.values()), terms, violations

    def violation(self, constraint, boxes, placement, inner):
        kind = constraint["type"]
        refs = refs_of(constraint)
        if kind == "proximity":
            anchor = refs[0]
            limit = constraint["max_distance_mm"]
            worst = max(box_gap(boxes[anchor], boxes[ref]) for ref in refs[1:])
            return max(0.0, worst - limit), f"{', '.join(refs[1:])} must be within {limit} mm of {anchor}; worst gap {worst:.2f} mm"
        if kind == "group":
            limit = constraint.get("max_distance_mm", DEFAULT_GROUP_GAP_MM)
            worst = 0.0
            for ref in refs:
                nearest = min(box_gap(boxes[ref], boxes[other]) for other in refs if other != ref)
                worst = max(worst, nearest)
            return max(0.0, worst - limit), f"group {', '.join(refs)} must stay within {limit} mm of each other; widest gap {worst:.2f} mm"
        if kind == "board_edge":
            edge = constraint["preferred_edge"]
            limit = constraint.get("max_distance_mm", DEFAULT_EDGE_GAP_MM)
            worst = 0.0
            for ref in refs:
                box = boxes[ref]
                distance = {
                    "left": box[0] - inner[0],
                    "top": box[1] - inner[1],
                    "right": inner[2] - box[2],
                    "bottom": inner[3] - box[3],
                }[edge]
                worst = max(worst, distance)
            return max(0.0, worst - limit), f"{', '.join(refs)} must sit within {limit} mm of the {edge} edge; worst {worst:.2f} mm"
        if kind == "separation":
            limit = constraint["min_distance_mm"]
            closest = min(box_gap(boxes[a], boxes[b]) for a in refs for b in constraint["from"])
            return max(0.0, limit - closest), f"{', '.join(refs)} must be at least {limit} mm from {', '.join(constraint['from'])}; closest {closest:.2f} mm"
        if kind == "loop_area":
            limit = constraint.get("max_area_mm2")
            area = hull_area([(placement[ref]["x"], placement[ref]["y"]) for ref in refs])
            if limit is None:
                return 0.0, ""
            return max(0.0, area - limit), f"loop through {', '.join(refs)} encloses {area:.2f} mm2, limit {limit} mm2"
        if kind == "orientation":
            wanted = constraint["rotation_deg"]
            wrong = [ref for ref in refs if placement[ref]["rotation"] % 360 != wanted]
            return float(len(wrong)), f"{', '.join(wrong)} must be rotated {wanted} degrees"
        return 0.0, ""


# Placer


def initial_rotation(problem, ref):
    if ref in problem.fixed_rotation:
        return problem.fixed_rotation[ref]
    for constraint in problem.constraints:
        if constraint["type"] == "orientation" and ref in refs_of(constraint):
            return constraint["rotation_deg"]
    return 0


def size_of(problem, ref):
    x0, y0, x1, y1 = problem.geometry[ref]["courtyard"]
    return x1 - x0, y1 - y0


def force_directed(problem, rng, iterations=300):
    refs = problem.refs
    gap = problem.rules["part_gap_mm"]
    total = sum((w + gap) * (h + gap) for w, h in (size_of(problem, ref) for ref in refs))
    span = math.sqrt(total) * 1.5
    placement = {
        ref: {"x": rng.uniform(0, span), "y": rng.uniform(0, span), "rotation": initial_rotation(problem, ref)}
        for ref in refs
    }
    neighbors = {ref: {} for ref in refs}
    for _, pins, weight in problem.nets:
        members = sorted({ref for ref, _ in pins})
        share = weight / (len(members) - 1)
        for a in members:
            for b in members:
                if a != b:
                    neighbors[a][b] = neighbors[a].get(b, 0.0) + share
    for step in range(iterations):
        cooling = 1.0 - step / iterations
        moves = {ref: [0.0, 0.0] for ref in refs}
        for a in refs:
            pa = placement[a]
            for b, weight in neighbors[a].items():
                pb = placement[b]
                moves[a][0] += 0.05 * weight * (pb["x"] - pa["x"])
                moves[a][1] += 0.05 * weight * (pb["y"] - pa["y"])
        for i, a in enumerate(refs):
            wa, ha = size_of(problem, a)
            for b in refs[i + 1:]:
                wb, hb = size_of(problem, b)
                dx = placement[a]["x"] - placement[b]["x"]
                dy = placement[a]["y"] - placement[b]["y"]
                want = (math.hypot(wa, ha) + math.hypot(wb, hb)) / 2 + gap
                distance = math.hypot(dx, dy)
                if distance < 1e-6:
                    dx, dy, distance = rng.uniform(-1, 1), rng.uniform(-1, 1), 1e-3
                if distance < want:
                    push = 0.5 * (want - distance) / distance
                    moves[a][0] += dx * push
                    moves[a][1] += dy * push
                    moves[b][0] -= dx * push
                    moves[b][1] -= dy * push
        limit = max(0.5, span * 0.1 * cooling)
        for ref in refs:
            mx, my = moves[ref]
            length = math.hypot(mx, my)
            if length > limit:
                mx, my = mx * limit / length, my * limit / length
            placement[ref]["x"] += mx
            placement[ref]["y"] += my
    return placement


def anneal(problem, placement, rng, steps):
    refs = problem.refs
    cost, _, _ = problem.evaluate(placement)
    best = {ref: dict(spot) for ref, spot in placement.items()}
    best_cost = cost
    x0, y0, x1, y1 = problem.outline(placement)
    reach = max(x1 - x0, y1 - y0, 5.0)

    samples = []
    for _ in range(min(60, steps)):
        ref = rng.choice(refs)
        old = dict(placement[ref])
        placement[ref]["x"] += rng.gauss(0, reach * 0.2)
        placement[ref]["y"] += rng.gauss(0, reach * 0.2)
        trial, _, _ = problem.evaluate(placement)
        samples.append(abs(trial - cost))
        placement[ref] = old
    temperature = max(1e-3, sum(samples) / max(1, len(samples)))
    final_temperature = temperature * 1e-4
    decay = (final_temperature / temperature) ** (1.0 / max(1, steps))

    for _ in range(steps):
        scale = max(0.05, reach * 0.3 * math.sqrt(temperature / (temperature + best_cost * 1e-3 + 1e-9)))
        move = rng.random()
        changed = {}
        if move < 0.7 or len(refs) < 2:
            ref = rng.choice(refs)
            changed[ref] = dict(placement[ref])
            placement[ref]["x"] += rng.gauss(0, scale)
            placement[ref]["y"] += rng.gauss(0, scale)
        elif move < 0.85:
            free = [ref for ref in refs if ref not in problem.fixed_rotation]
            if not free:
                temperature *= decay
                continue
            ref = rng.choice(free)
            changed[ref] = dict(placement[ref])
            placement[ref]["rotation"] = (placement[ref]["rotation"] + rng.choice((90, 180, 270))) % 360
        else:
            a, b = rng.sample(refs, 2)
            changed[a] = dict(placement[a])
            changed[b] = dict(placement[b])
            placement[a]["x"], placement[b]["x"] = changed[b]["x"], changed[a]["x"]
            placement[a]["y"], placement[b]["y"] = changed[b]["y"], changed[a]["y"]
        trial, _, _ = problem.evaluate(placement)
        delta = trial - cost
        if delta <= 0 or rng.random() < math.exp(-delta / temperature):
            cost = trial
            if cost < best_cost:
                best_cost = cost
                best = {ref: dict(spot) for ref, spot in placement.items()}
        else:
            for ref, spot in changed.items():
                placement[ref] = spot
        temperature *= decay
    return best


def separate(problem, placement, rounds=200):
    """Push apart any courtyards still closer than their allowed gap after annealing."""
    refs = problem.refs
    for _ in range(rounds):
        moved = False
        for i, a in enumerate(refs):
            for b in refs[i + 1:]:
                gap = problem.gap(a, b)
                ba = problem.courtyard(a, placement[a])
                bb = problem.courtyard(b, placement[b])
                ox = min(ba[2], bb[2]) - max(ba[0], bb[0]) + gap
                oy = min(ba[3], bb[3]) - max(ba[1], bb[1]) + gap
                if ox <= 1e-9 or oy <= 1e-9:
                    continue
                moved = True
                if ox < oy:
                    shift = ox / 2 + 1e-3
                    sign = 1 if placement[a]["x"] >= placement[b]["x"] else -1
                    placement[a]["x"] += sign * shift
                    placement[b]["x"] -= sign * shift
                else:
                    shift = oy / 2 + 1e-3
                    sign = 1 if placement[a]["y"] >= placement[b]["y"] else -1
                    placement[a]["y"] += sign * shift
                    placement[b]["y"] -= sign * shift
        if not moved:
            return placement
    return placement


def place(problem, seed=1, steps=None):
    """Return a placement dict with parts, outline, cost terms, and violations."""
    rng = random.Random(seed)
    if steps is None:
        steps = 4000 + 1500 * len(problem.refs)
    placement = force_directed(problem, rng)
    placement = anneal(problem, placement, rng, steps)
    placement = separate(problem, placement)

    x0, y0, x1, y1 = problem.outline(placement)
    dx = BOARD_ORIGIN_MM[0] - x0
    dy = BOARD_ORIGIN_MM[1] - y0
    for spot in placement.values():
        spot["x"] = round(spot["x"] + dx, 4)
        spot["y"] = round(spot["y"] + dy, 4)
        spot["rotation"] = int(spot["rotation"]) % 360
    cost, terms, violations = problem.evaluate(placement)
    x0, y0, x1, y1 = problem.outline(placement)
    return {
        "seed": seed,
        "parts": {ref: placement[ref] for ref in problem.refs},
        "outline_mm": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)],
        "board_mm": {"width": round(x1 - x0, 3), "height": round(y1 - y0, 3)},
        "cost": round(cost, 4),
        "terms": {key: round(value, 4) for key, value in terms.items()},
        "violations": violations,
        "legal": not any(v["hard"] for v in violations),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        print("usage: place.py <board.net> <footprints.json> <constraints.json>", file=sys.stderr)
        raise SystemExit(2)
    with open(sys.argv[1], encoding="utf-8") as handle:
        net = parse_netlist(handle.read())
    with open(sys.argv[2], encoding="utf-8") as handle:
        geometry = json.load(handle)
    with open(sys.argv[3], encoding="utf-8") as handle:
        wanted = json.load(handle)
    print(json.dumps(place(Problem(net, geometry, wanted)), indent=2))
