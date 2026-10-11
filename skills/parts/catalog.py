"""Search a local JLCPCB cache. The cache is a CSV on disk. Lookups do not use the network."""

import csv
import re
from difflib import SequenceMatcher
from functools import lru_cache
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
    "SOT-223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
    "SOT-89-3": "Package_TO_SOT_SMD:SOT-89-3",
    "TO-252-2(DPAK)": "Package_TO_SOT_SMD:TO-252-2",
    "TO-263-5": "Package_TO_SOT_SMD:TO-263-5_TabPin3",
}

DIODE_FOOTPRINTS = {
    "SMA(DO-214AC)": "Diode_SMD:D_SMA",
    "SMA": "Diode_SMD:D_SMA",
    "SMA_DO-214AC": "Diode_SMD:D_SMA",
    "SMB": "Diode_SMD:D_SMB",
    "SMC": "Diode_SMD:D_SMC",
    "SMC(DO-214AB)": "Diode_SMD:D_SMC",
    "SOD-123": "Diode_SMD:D_SOD-123",
    "SOD-323": "Diode_SMD:D_SOD-323",
}

VF_AT = re.compile(r"mV@(\d+(?:\.\d+)?)A\b", re.I)
MV_RANGE = re.compile(r"(\d+(?:\.\d+)?)mV~(\d+(?:\.\d+)?)V")


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
    fraction = re.search(r"(\d+)\s*/\s*(\d+)\s*W\b", text)
    if fraction and int(fraction[2]):
        return int(fraction[1]) / int(fraction[2])
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


KIND_LIBRARIES = {
    "resistor": ("Resistor_SMD",),
    "capacitor": ("Capacitor_SMD",),
    "inductor": ("Inductor_SMD",),
    "diode": ("Diode_SMD", "Package_TO_SOT_SMD"),
    "regulator": ("Package_SO", "Package_TO_SOT_SMD", "Package_TO_SOT_THT", "Package_DFN_QFN", "Package_DIP"),
}

SIZE_CODES = ("0201", "0402", "0603", "0805", "1206", "1210", "2010", "2512")

FAMILY_ALIASES = {
    "ESOP": ("ESOP", "SOIC", "SOP"),
    "TSSOP": ("TSSOP",),
    "SSOP": ("SSOP",),
    "MSOP": ("MSOP",),
    "SOIC": ("SOIC",),
    "SOP": ("SOP", "SOIC"),
    "VQFN": ("VQFN", "QFN"),
    "QFN": ("QFN",),
    "DFN": ("DFN",),
    "SOD": ("SOD",),
    "SOT": ("SOT",),
    "SMAF": ("SMAF", "SMA"),
    "SMBF": ("SMBF", "SMB"),
    "SMA": ("SMA",),
    "SMB": ("SMB",),
    "SMC": ("SMC",),
    "DIP": ("DIP",),
    "TO": ("TO",),
}

FAMILY_ORDER = (
    "ESOP", "TSSOP", "SSOP", "MSOP", "SOIC", "SOP", "VQFN", "QFN", "DFN",
    "SMAF", "SMBF", "SOD", "SOT", "SMA", "SMB", "SMC", "DIP", "TO",
)


def _exact_footprint(kind, package):
    if kind == "diode":
        return DIODE_FOOTPRINTS.get(package)
    if kind in PASSIVE_LIB and package in PASSIVE_SIZE:
        lib = PASSIVE_LIB[kind]
        name = f"{PASSIVE_PREFIX[kind]}_{package}_{PASSIVE_SIZE[package]}"
        return f"{lib}:{name}"
    for prefix, candidate in IC_FOOTPRINTS.items():
        if package == prefix:
            return candidate
    return None


def _footprint_file(footprint_dir, ref):
    lib, name = ref.split(":", 1)
    return (footprint_dir / f"{lib}.pretty" / f"{name}.kicad_mod").is_file()


def _has_token(text, token):
    return re.search(rf"(^|[^A-Z0-9]){re.escape(token)}([^A-Z0-9]|$)", text.upper()) is not None


def _chip_size(package):
    for code in SIZE_CODES:
        if _has_token(package, code):
            return code
    return None


def _family(package):
    text = package.upper()
    paren = re.search(r"\(([A-Z0-9-]+)\)", text)
    if paren and paren.group(1) in FAMILY_ALIASES:
        name = paren.group(1)
        return name, FAMILY_ALIASES[name]
    size = _chip_size(text)
    if size:
        return size, (size,)
    for name in FAMILY_ORDER:
        if _has_token(text, name):
            return name, FAMILY_ALIASES[name]
    dims = re.findall(r"(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)", text.replace("×", "X"))
    if dims:
        return "DIM", tuple(f"{a}X{b}" for a, b in dims)
    return None, ()


def _pin_count(text, family):
    upper = text.upper()
    if family in SIZE_CODES or family == "DIM" or family is None:
        return None
    if family in {"SOD", "SMA", "SMB", "SMC", "SMAF", "SMBF"}:
        return 2
    if family == "SOT":
        match = re.search(r"SOT-23-(\d)", upper)
        if match:
            return int(match.group(1))
        match = re.search(r"SOT-89-(\d)", upper)
        if match:
            return int(match.group(1))
        if "SOT-23" in upper or "SOT-89" in upper:
            return 3
        return None
    if family == "TO":
        match = re.search(r"TO-?\d+[A-Z0-9]*-(\d+)", upper)
        return int(match.group(1)) if match else None
    match = re.search(rf"{family}-(\d+)", upper)
    return int(match.group(1)) if match else None


def _has_exposed_pad(text):
    upper = text.upper()
    return "ESOP" in upper or re.search(r"(^|[^A-Z])EP([^A-Z]|$)", upper) is not None


@lru_cache(maxsize=64)
def _footprint_names(directory):
    path = Path(directory)
    if not path.is_dir():
        return ()
    return tuple(sorted(item.stem for item in path.glob("*.kicad_mod")))


def _dimension_match(package_dims, stem):
    found = re.findall(r"(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)", stem.upper().replace("×", "X"))
    for wanted in package_dims:
        left, right = wanted.split("X")
        for one, two in found:
            if abs(float(left) - float(one)) <= 0.2 and abs(float(right) - float(two)) <= 0.2:
                return True
    return False


def _footprint_score(package, stem, family, aliases):
    if family == "DIM":
        if not _dimension_match(aliases, stem):
            return None
        pin_match = 1
    else:
        if not any(_has_token(stem, alias) for alias in aliases):
            return None
        wanted = _pin_count(package, family)
        found = _pin_count(stem, family)
        if wanted is not None and found is not None and wanted != found:
            return None
        pin_match = 1 if wanted is not None and found == wanted else 0
    exposed = _has_exposed_pad(package)
    has_pad = _has_exposed_pad(stem)
    plain = "HANDSOLDER" not in stem.upper() and "PAD" not in stem.upper() and "THERMALVIAS" not in stem.upper()
    ratio = SequenceMatcher(None, re.sub(r"[^A-Z0-9]", "", package.upper()), re.sub(r"[^A-Z0-9]", "", stem.upper())).ratio()
    return (pin_match, 1 if exposed == has_pad else 0, 1 if plain else 0, ratio, -len(stem))


def closest_footprint_name(package, library_dir):
    """Nearest footprint stem in one .pretty directory, or None."""
    if not package:
        return None
    family, aliases = _family(package)
    if family is None:
        return None
    best = None
    best_score = None
    for stem in _footprint_names(str(library_dir)):
        score = _footprint_score(package, stem, family, aliases)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best = stem
            best_score = score
    return best


def _closest_footprint(kind, package, footprint_dir):
    for lib in KIND_LIBRARIES.get(kind, ()):
        stem = closest_footprint_name(package, footprint_dir / f"{lib}.pretty")
        if stem:
            return f"{lib}:{stem}"
    return None


def footprint_for(kind, package, footprint_dir):
    ref = _exact_footprint(kind, package)
    if footprint_dir is None:
        return ref
    if ref and _footprint_file(footprint_dir, ref):
        return ref
    return _closest_footprint(kind, package or "", footprint_dir)


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
            if token == name or (len(name) >= 4 and token.startswith(name)):
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
        "footprint_match": "exact" if footprint_for(kind, package, footprint_dir) == _exact_footprint(kind, package) else "heuristic",
        "datasheet": row.get("file") or row.get("datasheet") or "",
    }


def _eligible(record, supply_v, stress=None):
    if not record.get("stock") or record["stock"] <= 0 or not record.get("footprint"):
        return False
    stress = stress or {}
    limits = []
    if record["kind"] == "capacitor":
        limits.append(("voltage_rating_v", stress.get("voltage_v", supply_v)))
    if record["kind"] == "resistor":
        limits.extend((key, stress.get(measured)) for key, measured in
                      (("power_rating_w", "power_w"), ("voltage_rating_v", "voltage_v")))
    if record["kind"] == "inductor":
        limits.append(("current_rating_a", stress.get("current_a")))
    return all(required is None or (record.get(key) is not None and record[key] >= required)
               for key, required in limits)


def search_passive(rows, kind, value_si, supply_v, footprint_dir, symbol_dir, stress=None):
    found = []
    for row in rows:
        if row.get("category") != KIND_CATEGORY[kind]:
            continue
        record = row_record(row, kind, footprint_dir)
        record["kind"] = kind
        if record["value_si"] is None or not _eligible(record, supply_v, stress):
            continue
        if relative_error(record["value_si"], value_si) > 0.01:
            continue
        record["symbol"] = symbol_for(kind, record["manufacturer_part_number"], symbol_dir)
        if record["symbol"]:
            found.append(record)
    found.sort(key=lambda item: (item["availability"] != "basic", item["price"] is None,
                                 item["price"] or 0, -(item["stock"] or 0)))
    return found[0] if found else None


def wanted_topologies(spec):
    """Which regulator families the prompt asked for. A bare 'regulator' allows all three."""
    prompt = (spec.get("prompt") or "").lower()
    buck = any(word in prompt for word in ("buck", "step-down", "step down", "switching"))
    boost = "boost" in prompt
    ldo = any(word in prompt for word in ("ldo", "linear"))
    named = {name for name, flag in (("buck", buck), ("boost", boost), ("ldo", ldo)) if flag}
    return named or {"buck", "boost", "ldo"}


def row_topology(row):
    blob = f"{row.get('type') or ''} {row.get('describe') or ''}".lower()
    if "low drop" in blob or re.search(r"\bldo\b", blob) or "linear" in blob:
        return "ldo"
    buck = "buck" in blob or "step-down" in blob or "step down" in blob
    boost = "boost" in blob
    if buck and boost:
        return "buck-boost"
    if buck:
        return "buck"
    if boost:
        return "boost"
    return None


def topology_fits(row_name, wanted):
    if row_name == "buck-boost":
        return "buck" in wanted or "boost" in wanted
    return row_name in wanted


def chosen_topology(row_name, wanted):
    if row_name == "buck-boost":
        if wanted == {"boost"}:
            return "boost"
        return "buck"
    return row_name


def is_synchronous(text):
    low = text.lower()
    if "non-synchronous" in low or "nonsynchronous" in low:
        return False
    if "synchronous" in low:
        return True
    return re.search(r"built-in\s+yes", low) is not None


def feedback_voltage(text, adjustable):
    """Reference of an adjustable regulator: the low end of its output range."""
    if not adjustable:
        return None
    candidates = [low for low, high in voltage_ranges(text) if low <= 1.5 and high >= 5]
    for number, high in MV_RANGE.findall(text):
        low = float(number) / 1000
        if low <= 1.5 and float(high) >= 5:
            candidates.append(low)
    return min(candidates) if candidates else None


def diode_forward_current(text):
    """Average forward current from the Vf test, not the surge rating."""
    match = VF_AT.search(text)
    if match is None:
        return None
    return float(match.group(1))


def _in_stock(record):
    return record.get("stock") is not None and record["stock"] > 0


def _with_libraries(record, kind, symbol_dir):
    record["symbol"] = symbol_for(kind, record["manufacturer_part_number"], symbol_dir)
    if not record.get("symbol") or not record.get("footprint") or not _in_stock(record):
        return None
    return record


def search_diode(rows, supply_v, current_a, footprint_dir, symbol_dir):
    """A Schottky catch diode rated for the supply voltage and the load current."""
    found = []
    for row in rows:
        if "schottky" not in (row.get("type") or "").lower():
            continue
        text = row.get("describe") or ""
        record = row_record(row, "diode", footprint_dir)
        record["kind"] = "diode"
        record["current_rating_a"] = diode_forward_current(text)
        rating = record["voltage_rating_v"]
        if supply_v is not None and (rating is None or rating < supply_v):
            continue
        forward = record["current_rating_a"]
        if current_a is not None and (forward is None or forward < current_a):
            continue
        ready = _with_libraries(record, "diode", symbol_dir)
        if ready is not None:
            found.append(ready)
    found.sort(key=lambda item: (item["availability"] != "basic", item["price"] is None, item["price"] or 0, -(item["stock"] or 0)))
    return found[0] if found else None


def search_regulator(rows, spec, footprint_dir, symbol_dir):
    supply = spec.get("supply_voltage_v")
    output = spec.get("output_voltage_v")
    current = spec.get("output_current_a")
    if output is None or current is None:
        return None
    tolerance = (spec.get("tolerances") or {}).get("output_voltage_v", 0.05)
    wanted = wanted_topologies(spec)
    found = []
    for row in rows:
        family = row_topology(row)
        if not topology_fits(family, wanted):
            continue
        text = f"{row.get('describe') or ''} {row.get('type') or ''}"
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
        topology = chosen_topology(family, wanted)
        record["topology"] = topology
        record["adjustable"] = adjustable
        record["feedback_voltage_v"] = feedback_voltage(text, adjustable)
        record["external_diode"] = topology in ("buck", "boost") and not is_synchronous(text)
        ready = _with_libraries(record, "regulator", symbol_dir)
        if ready is not None:
            found.append(ready)
    found.sort(key=lambda item: (item["availability"] != "basic", item["price"] is None, item["price"] or 0))
    return found[0] if found else None
