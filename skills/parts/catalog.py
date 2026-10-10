"""Search a local JLCPCB cache. The cache is a CSV on disk. Lookups do not use the network."""

import csv
import re
from pathlib import Path


CATALOG_URL = "https://lrks.github.io/jlcpcb-economic-parts/economic-parts.csv"

OHM = re.compile(r"(\d+(?:\.\d+)?)\s*(mΩ|kΩ|MΩ|Ω|mohm|kohm|Mohm|ohm)\b", re.I)
FARAD = re.compile(r"(\d+(?:\.\d+)?)\s*(pF|nF|uF|µF|μF|mF|F)\b")
HENRY = re.compile(r"(\d+(?:\.\d+)?)\s*(nH|uH|µH|μH|mH|H)\b")
VOLT = re.compile(r"(\d+(?:\.\d+)?)\s*V\b")
VOLT_RANGE = re.compile(r"(\d+(?:\.\d+)?)V~(\d+(?:\.\d+)?)V")
AMP = re.compile(r"(\d+(?:\.\d+)?)\s*(mA|A)\b")
WATT = re.compile(r"(\d+(?:\.\d+)?)\s*(mW|W)\b")
TOL = re.compile(r"±\s*(\d+(?:\.\d+)?)\s*%")

SKIDL_SCALE = {
    "u_ohm": 1,
    "u_kohm": 1e3,
    "u_mohm": 1e-3,
    "u_Mohm": 1e6,
    "u_F": 1,
    "u_mf": 1e-3,
    "u_uf": 1e-6,
    "u_nf": 1e-9,
    "u_pf": 1e-12,
    "u_H": 1,
    "u_mh": 1e-3,
    "u_uh": 1e-6,
    "u_nh": 1e-9,
}

KIND_CATEGORY = {
    "resistor": "Resistors",
    "capacitor": "Capacitors",
    "inductor": "Inductors, Coils, Chokes",
    "diode": "Diodes",
}

PASSIVE_SYMBOL = {
    "resistor": "Device:R",
    "capacitor": "Device:C",
    "inductor": "Device:L",
    "diode": "Device:D",
}

PASSIVE_LIB = {
    "resistor": "Resistor_SMD",
    "capacitor": "Capacitor_SMD",
    "inductor": "Inductor_SMD",
}

PASSIVE_PREFIX = {"resistor": "R", "capacitor": "C", "inductor": "L"}

PASSIVE_SIZE = {
    "0402": "1005Metric",
    "0603": "1608Metric",
    "0805": "2012Metric",
    "1206": "3216Metric",
}

IC_FOOTPRINTS = {
    "SOIC-8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "SOT-23-6": "Package_TO_SOT_SMD:SOT-23-6",
    "SOT-23-5": "Package_TO_SOT_SMD:SOT-23-5",
    "SOT-23": "Package_TO_SOT_SMD:SOT-23",
    "SOT-89-3": "Package_TO_SOT_SMD:SOT-89-3",
    "TO-263-5": "Package_TO_SOT_SMD:TO-263-5_TabPin3",
}


def repo_root():
    return Path(__file__).resolve().parents[2]


def default_catalog():
    return repo_root() / ".tools" / "jlcpcb" / "economic-parts.csv"


def load_catalog(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def si_from_skidl(number, unit):
    if unit == "u_mOhm":
        scale = 1e-3
    elif unit == "u_MOhm":
        scale = 1e6
    else:
        scale = SKIDL_SCALE.get(unit) or SKIDL_SCALE.get(unit.lower())
    if scale is None:
        raise ValueError(f"unknown SKiDL unit {unit}")
    return float(number) * scale


def parse_ohms(text):
    match = OHM.search(text)
    if not match:
        return None
    number = float(match.group(1))
    raw = match.group(2)
    token = raw.replace("Ω", "ohm")
    if token == "Mohm" or raw.startswith("M"):
        scale = 1e6
    elif token.lower() == "mohm":
        scale = 1e-3
    elif token.lower() == "kohm":
        scale = 1e3
    else:
        scale = 1
    return number * scale


def parse_farads(text):
    match = FARAD.search(text)
    if not match:
        return None
    unit = match.group(2).replace("µ", "u").replace("μ", "u").lower()
    scales = {"pf": 1e-12, "nf": 1e-9, "uf": 1e-6, "mf": 1e-3, "f": 1}
    return float(match.group(1)) * scales[unit]


def parse_henries(text):
    match = HENRY.search(text)
    if not match:
        return None
    unit = match.group(2).replace("µ", "u").replace("μ", "u").lower()
    scales = {"nh": 1e-9, "uh": 1e-6, "mh": 1e-3, "h": 1}
    return float(match.group(1)) * scales[unit]


def parse_value(kind, text):
    if kind == "resistor":
        return parse_ohms(text)
    if kind == "capacitor":
        return parse_farads(text)
    if kind == "inductor":
        return parse_henries(text)
    return None


def first_number(pattern, text, scales):
    match = pattern.search(text)
    if not match:
        return None
    return float(match.group(1)) * scales[match.group(2)]


def voltage_rating(text):
    values = [float(item) for item in VOLT.findall(text)]
    return max(values) if values else None


def power_rating(text):
    return first_number(WATT, text, {"mW": 1e-3, "W": 1, "mw": 1e-3, "w": 1})


def current_rating(text):
    values = []
    for number, unit in AMP.findall(text):
        values.append(float(number) * (1e-3 if unit == "mA" else 1))
    return max(values) if values else None


def tolerance_text(text):
    match = TOL.search(text)
    return f"±{match.group(1)}%" if match else None


def covers(low, high, value):
    return low <= value <= high


def voltage_ranges(text):
    return [(float(low), float(high)) for low, high in VOLT_RANGE.findall(text)]


def relative_error(actual, wanted):
    if wanted == 0:
        return abs(actual)
    return abs(actual - wanted) / abs(wanted)


def availability(row):
    return "basic" if row.get("library") == "base" else "preferred"


def price_of(row):
    try:
        return float(row["price"])
    except (TypeError, ValueError):
        return None


def stock_of(row):
    try:
        return int(float(row["stock"]))
    except (TypeError, ValueError):
        return None


def footprint_for(kind, package, footprint_dir):
    if kind in PASSIVE_LIB and package in PASSIVE_SIZE:
        lib = PASSIVE_LIB[kind]
        name = f"{PASSIVE_PREFIX[kind]}_{package}_{PASSIVE_SIZE[package]}"
        ref = f"{lib}:{name}"
    else:
        ref = None
        for prefix, candidate in IC_FOOTPRINTS.items():
            if package != prefix:
                continue
            ref = candidate
            break
    if ref is None or footprint_dir is None:
        return ref
    lib, name = ref.split(":", 1)
    path = footprint_dir / f"{lib}.pretty" / f"{name}.kicad_mod"
    return ref if path.is_file() else None


def symbol_for(kind, model, symbol_dir):
    if kind in PASSIVE_SYMBOL:
        return PASSIVE_SYMBOL[kind]
    if symbol_dir is None or not model:
        return None
    token = model.split("/")[0]
    best = None
    for path in symbol_dir.glob("*.kicad_sym"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'^\t\(symbol "([^"]+)"', text, re.M):
            name = match.group(1)
            if token == name or token.startswith(name):
                if best is None or len(name) > len(best[0]):
                    best = (name, f"{path.stem}:{name}")
    return best[1] if best else None


def row_record(row, kind, footprint_dir):
    text = f"{row.get('describe') or ''} {row.get('model') or ''}"
    package = row.get("package") or ""
    return {
        "lcsc": row.get("code") or row.get("lcsc"),
        "manufacturer_part_number": row.get("model") or "",
        "manufacturer": row.get("brand") or row.get("manufacturer") or "",
        "value": text.strip(),
        "value_si": parse_value(kind, text),
        "tolerance": tolerance_text(text),
        "voltage_rating_v": voltage_rating(text),
        "current_rating_a": current_rating(text),
        "power_rating_w": power_rating(text),
        "package": package,
        "stock": stock_of(row),
        "price": price_of(row),
        "availability": availability(row),
        "symbol": None,
        "footprint": footprint_for(kind, package, footprint_dir),
        "datasheet": row.get("file") or row.get("datasheet") or "",
    }


def _eligible(record, supply_v):
    if record["kind"] == "capacitor" and supply_v is not None and record["voltage_rating_v"] is not None:
        if record["voltage_rating_v"] < supply_v:
            return False
    return True


def search_passive(rows, kind, value_si, supply_v, footprint_dir, symbol_dir):
    category = KIND_CATEGORY[kind]
    found = []
    for row in rows:
        if row.get("category") != category:
            continue
        record = row_record(row, kind, footprint_dir)
        record["kind"] = kind
        if record["value_si"] is None or not _eligible(record, supply_v):
            continue
        if relative_error(record["value_si"], value_si) > 0.01:
            continue
        found.append(record)
        found.sort(key=lambda item: (item["availability"] != "basic", item["price"] is None, item["price"] or 0, -(item["stock"] or 0)))
    if not found:
        return None
    chosen = found[0]
    chosen["symbol"] = symbol_for(kind, chosen["manufacturer_part_number"], symbol_dir)
    return chosen


def search_regulator(rows, spec, footprint_dir, symbol_dir):
    supply = spec.get("supply_voltage_v")
    output = spec.get("output_voltage_v")
    current = spec.get("output_current_a")
    if output is None or current is None:
        return None
    tolerance = (spec.get("tolerances") or {}).get("output_voltage_v", 0.05)
    found = []
    for row in rows:
        text = f"{row.get('describe') or ''} {row.get('type') or ''} {row.get('category') or ''}"
        if "buck" not in text.lower() and "dc-dc" not in text.lower():
            continue
        record = row_record(row, "regulator", footprint_dir)
        record["kind"] = "regulator"
        rating = record["current_rating_a"]
        if rating is None or rating < current:
            continue
        ranges = voltage_ranges(text)
        fixed = [float(value) for value in VOLT.findall(text)]
        adjustable = "adjustable" in text.lower()
        output_ranges = [item for item in ranges if covers(item[0], item[1], output)]
        if adjustable and output_ranges:
            output_ok = True
        elif any(abs(value - output) <= tolerance for value in fixed):
            output_ok = True
        else:
            output_ok = False
        if not output_ok:
            continue
        if supply is not None and ranges:
            input_ranges = [item for item in ranges if item not in output_ranges] or ranges
            if not any(covers(low, high, supply) for low, high in input_ranges):
                continue
        found.append(record)
    found.sort(key=lambda item: (item["availability"] != "basic", item["price"] is None, item["price"] or 0))
    if not found:
        return None
    chosen = found[0]
    chosen["symbol"] = symbol_for("regulator", chosen["manufacturer_part_number"], symbol_dir)
    return chosen
