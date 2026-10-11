"""Read pin names from an installed KiCad symbol."""

import re


def parse_sexpr(text):
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)
    stack = [[]]
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            if len(stack) < 2:
                raise ValueError("unbalanced ')' in symbol")
            done = stack.pop()
            stack[-1].append(done)
        elif token.startswith('"'):
            stack[-1].append(token[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(token)
    if len(stack) != 1:
        raise ValueError("unbalanced '(' in symbol")
    return stack[0]


def _child(node, name):
    for item in node[1:]:
        if isinstance(item, list) and item and item[0] == name and len(item) > 1:
            return item[1]
    return None


def _symbol(tree, name):
    nodes = list(tree)
    for item in tree:
        if isinstance(item, list) and item and item[0] == "kicad_symbol_lib":
            nodes.extend(item[1:])
    for item in nodes:
        if isinstance(item, list) and item and item[0] == "symbol" and len(item) > 1 and item[1] == name:
            return item
    return None


def _pins(node, found):
    if isinstance(node, list) and node and node[0] == "pin":
        name = _child(node, "name")
        number = _child(node, "number")
        if name and number:
            found.append({"number": str(number), "name": str(name), "type": str(node[1]) if len(node) > 1 else ""})
        return
    if isinstance(node, list):
        for item in node[1:]:
            _pins(item, found)


ROLE_NAMES = (
    ("input", {"VIN", "PVIN", "VCC", "IN", "VI"}),
    ("switch", {"SW", "LX", "PH", "SWITCH"}),
    ("output", {"OUT", "VOUT", "VO"}),
    ("feedback", {"FB", "ADJ", "VFB"}),
    ("ground", {"GND", "PGND", "AGND", "VSS"}),
    ("enable", {"EN", "SHDN", "ON", "ENABLE"}),
)


def _clean(name):
    text = name.strip()
    if text.startswith("~{") and text.endswith("}"):
        text = text[2:-1]
    return text.upper()


def pin_roles(pins, topology=None):
    roles = {}
    for role, names in ROLE_NAMES:
        for pin in pins:
            if _clean(pin["name"]) in names and role not in roles:
                roles[role] = pin["name"]
    if topology in ("buck", "boost") and "switch" not in roles and "output" in roles:
        roles["switch"] = roles["output"]
    return roles


def symbol_pins(symbol, symbol_dir):
    """Pins of a 'Library:Name' symbol. An `extends` symbol uses its parent's pins."""
    if not symbol or symbol_dir is None or ":" not in symbol:
        return []
    library, name = symbol.split(":", 1)
    path = symbol_dir / f"{library}.kicad_sym"
    if not path.is_file():
        return []
    try:
        tree = parse_sexpr(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        return []
    body = _symbol(tree, name)
    if body is None:
        return []
    parent = _child(body, "extends")
    if parent:
        body = _symbol(tree, parent) or body
    found = []
    _pins(body, found)
    return found
