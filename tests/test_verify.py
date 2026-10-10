"""Contract for simulation inside /design.

The runner is skills/circuit/verify.py. /design runs the design tests against
one design directory:

    .venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>

Those tests read that directory's circuit-spec.json. They do not assume a
particular circuit. Without --design they skip.

The other tests check the runner itself with a synthetic spec. They are not
the design.
"""

import functools
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "circuit" / "verify.py"
CHECK_SPEC = ROOT / "skills" / "requirements" / "check_spec.py"
SCHEMAS = ROOT / "skills" / "circuit" / "schemas"
RESULT_SCHEMA = json.loads((SCHEMAS / "simulation-result.schema.json").read_text())
SPEC_SCHEMA = json.loads((SCHEMAS / "circuit-spec.schema.json").read_text())
MEASURED = ("output_voltage_v", "gain", "bandwidth_hz", "output_current_a")

DIVIDER_SIM = '''
from skidl.pyspice import *


def measure():
    reset()
    vin = Net("VIN")
    vout = Net("VOUT")
    V(ref="VS", dc_value=5 @ u_V)["p", "n"] += vin, gnd
    R(value=10 @ u_kOhm)["p", "n"] += vin, vout
    R(value=6.8 @ u_kOhm)["p", "n"] += vout, gnd
    op = Simulator.factory().simulation(generate_netlist()).operating_point()
    return {"output_voltage_v": float(op.nodes["vout"][0])}
'''

DIVIDER_VOUT = 5 * 6.8 / 16.8


def measured_spec(**fields):
    spec = {
        "prompt": "runner fixture",
        "supply_voltage_v": 5,
        "load": "fixture load",
        "tolerances": {},
    }
    for name, (target, tolerance) in fields.items():
        spec[name] = target
        spec["tolerances"][name] = tolerance
    return spec


def divider_spec(target):
    return {
        "prompt": "resistor divider fixture",
        "supply_voltage_v": 5,
        "output_voltage_v": target,
        "load": "open circuit",
        "tolerances": {"output_voltage_v": 0.05},
    }


@pytest.fixture
def design(request):
    raw = request.config.getoption("design")
    if not raw:
        pytest.skip("design tests run when /design passes --design")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if not (path / "design" / "circuit-spec.json").is_file():
        pytest.fail(f"no design/circuit-spec.json in {path}")
    return path


@functools.cache
def load_verify():
    if not RUNNER.is_file():
        pytest.fail(f"no verify runner at {RUNNER.relative_to(ROOT)}")
    spec = importlib.util.spec_from_file_location("verify", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_sim(measurements):
    return f"def measure():\n    return {measurements!r}\n"


def dc_source(voltage, returns):
    body = ", ".join(f"{name!r}: {expr}" for name, expr in returns.items())
    return f'''from skidl.pyspice import *


def measure():
    reset()
    vout = Net("VOUT")
    V(ref="VS", dc_value={voltage} @ u_V)["p", "n"] += vout, gnd
    R(value=1 @ u_kOhm)["p", "n"] += vout, gnd
    op = Simulator.factory().simulation(generate_netlist()).operating_point()
    voltage = float(op.nodes["vout"][0])
    return {{{body}}}
'''


def circuit_files(slug):
    return slug / "design"


def make_design(root, spec, sim_source, results=None):
    folder = circuit_files(root)
    folder.mkdir()
    (folder / "circuit-spec.json").write_text(json.dumps(spec, indent=2))
    (folder / "skidl_sim.py").write_text(sim_source)
    if results is not None:
        (folder / "simulation-results.json").write_text(json.dumps(results, indent=2))
    return root


def run_verify(design, cwd):
    if not RUNNER.is_file():
        pytest.fail(f"no verify runner at {RUNNER.relative_to(ROOT)}")
    return subprocess.run(
        [sys.executable, str(RUNNER), str(design)],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=300,
    )


def read_results(design):
    path = circuit_files(design) / "simulation-results.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def by_requirement(results):
    return {result["requirement"]: result for result in results}


def passing(results):
    return [r["requirement"] for r in results or [] if r.get("status") == "pass"]


def test_judge_passes_inside_tolerance():
    result = load_verify().judge("output_voltage_v", target=1.0, measured=1.05, tolerance=0.1)
    assert result == {
        "requirement": "output_voltage_v",
        "target": 1.0,
        "measured": 1.05,
        "tolerance": 0.1,
        "status": "pass",
    }
    jsonschema.validate(result, RESULT_SCHEMA)


def test_judge_passes_on_tolerance_boundary():
    assert load_verify().judge("output_current_a", target=0.5, measured=0.6, tolerance=0.1)["status"] == "pass"


def test_judge_fails_above_tolerance():
    result = load_verify().judge("output_voltage_v", target=1.0, measured=1.2, tolerance=0.1)
    assert result["status"] == "fail"
    jsonschema.validate(result, RESULT_SCHEMA)


def test_judge_fails_below_tolerance():
    assert load_verify().judge("gain", target=10, measured=9, tolerance=0.5)["status"] == "fail"


def test_judge_fails_on_nan_measurement():
    assert load_verify().judge("output_voltage_v", target=1.0, measured=float("nan"), tolerance=0.1)["status"] == "fail"


def test_judge_rejects_negative_tolerance():
    with pytest.raises(ValueError):
        load_verify().judge("output_voltage_v", target=1.0, measured=1.0, tolerance=-0.1)


def test_expected_checks_come_from_spec():
    spec = measured_spec(output_voltage_v=(1.0, 0.1), gain=(10, 0.5))
    checks = sorted(load_verify().expected_checks(spec), key=lambda c: c["requirement"])
    assert checks == [
        {"requirement": "gain", "target": 10, "tolerance": 0.5},
        {"requirement": "output_voltage_v", "target": 1.0, "tolerance": 0.1},
    ]


def test_expected_checks_refuse_to_invent_tolerance():
    spec = measured_spec(output_voltage_v=(1.0, 0.1), output_current_a=(0.5, 0.05))
    del spec["tolerances"]["output_current_a"]
    with pytest.raises(ValueError, match="output_current_a"):
        load_verify().expected_checks(spec)


def test_runner_writes_passing_results(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1), output_current_a=(0.5, 0.05))
    folder = make_design(
        tmp_path,
        spec,
        dc_source(1.02, {"output_voltage_v": "voltage", "output_current_a": "voltage / 2"}),
    )
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 0, proc.stderr
    results = read_results(folder)
    assert results is not None
    for result in results:
        jsonschema.validate(result, RESULT_SCHEMA)
    assert by_requirement(results) == {
        "output_voltage_v": {"requirement": "output_voltage_v", "target": 1.0, "measured": 1.02, "tolerance": 0.1, "status": "pass"},
        "output_current_a": {"requirement": "output_current_a", "target": 0.5, "measured": 0.51, "tolerance": 0.05, "status": "pass"},
    }


def test_runner_reports_out_of_tolerance_as_fail(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1), output_current_a=(0.5, 0.05))
    folder = make_design(
        tmp_path,
        spec,
        dc_source(0.5, {"output_voltage_v": "voltage", "output_current_a": "voltage"}),
    )
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 1, proc.stderr
    assert "output_voltage_v failed" in proc.stderr
    assert "low" in proc.stderr
    results = by_requirement(read_results(folder))
    assert results["output_voltage_v"]["status"] == "fail"
    assert results["output_voltage_v"]["measured"] == 0.5
    assert results["output_current_a"]["status"] == "pass"


def test_runner_overwrites_stale_pass_with_new_fail(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1))
    stale = [{"requirement": "output_voltage_v", "target": 1.0, "measured": 1.0, "tolerance": 0.1, "status": "pass"}]
    folder = make_design(tmp_path, spec, dc_source(0.2, {"output_voltage_v": "voltage"}), stale)
    run_verify(folder, tmp_path)
    assert by_requirement(read_results(folder))["output_voltage_v"]["status"] == "fail"


def test_runner_crash_leaves_no_pass(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1))
    stale = [{"requirement": "output_voltage_v", "target": 1.0, "measured": 1.0, "tolerance": 0.1, "status": "pass"}]
    folder = make_design(tmp_path, spec, "raise ValueError('bad netlist')\n", stale)
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 2
    assert passing(read_results(folder)) == []


def test_runner_clean_exit_without_measurements_is_not_a_pass(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1))
    stale = [{"requirement": "output_voltage_v", "target": 1.0, "measured": 1.0, "tolerance": 0.1, "status": "pass"}]
    folder = make_design(tmp_path, spec, "print('.title netlist only')\n", stale)
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 2
    assert passing(read_results(folder)) == []


def test_runner_missing_measurement_is_not_a_pass(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1), gain=(10, 0.5))
    stale = [{"requirement": "gain", "target": 10, "measured": 10, "tolerance": 0.5, "status": "pass"}]
    folder = make_design(tmp_path, spec, dc_source(1.0, {"output_voltage_v": "voltage"}), stale)
    proc = run_verify(folder, tmp_path)
    assert proc.returncode != 0
    assert "gain" not in passing(read_results(folder))


def test_runner_drops_checks_not_in_spec(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1))
    folder = make_design(
        tmp_path,
        spec,
        dc_source(1.0, {"output_voltage_v": "voltage", "switching_frequency": "voltage"}),
    )
    run_verify(folder, tmp_path)
    assert set(by_requirement(read_results(folder))) == {"output_voltage_v"}


def test_runner_refuses_spec_without_tolerance(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1))
    del spec["tolerances"]
    folder = make_design(tmp_path, spec, fake_sim({"output_voltage_v": 1.0}))
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 2
    assert read_results(folder) is None


def test_runner_never_edits_spec(tmp_path):
    spec = measured_spec(output_voltage_v=(1.0, 0.1))
    folder = make_design(tmp_path, spec, fake_sim({"output_voltage_v": 0.2}))
    before = (circuit_files(folder) / "circuit-spec.json").read_bytes()
    run_verify(folder, tmp_path)
    assert (circuit_files(folder) / "circuit-spec.json").read_bytes() == before


def test_runner_rejects_spec_targets_without_a_circuit(tmp_path):
    spec = measured_spec(output_voltage_v=(3.3, 0.05), output_current_a=(2.0, 0.1))
    sim = "def measure():\n    return {'output_voltage_v': 3.3, 'output_current_a': 2.0}\n"
    folder = make_design(tmp_path, spec, sim)
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 2
    assert read_results(folder) is None
    assert "ngspice" in proc.stderr


def test_runner_rejects_simulation_scaled_to_the_target(tmp_path):
    spec = measured_spec(output_voltage_v=(3.3, 0.05))
    sim = '''from skidl.pyspice import *


def measure():
    reset()
    vout = Net("VOUT")
    V(ref="VS", dc_value=1 @ u_V)["p", "n"] += vout, gnd
    R(value=1 @ u_kOhm)["p", "n"] += vout, gnd
    op = Simulator.factory().simulation(generate_netlist()).operating_point()
    voltage = float(op.nodes["vout"][0])
    return {"output_voltage_v": voltage * (3.3 / voltage)}
'''
    folder = make_design(tmp_path, spec, sim)
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert read_results(folder) is None
    assert "not measured from the simulation" in proc.stderr


def test_runner_measures_with_ngspice(tmp_path):
    folder = make_design(tmp_path, divider_spec(2.0), DIVIDER_SIM)
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 0, proc.stderr
    result = by_requirement(read_results(folder))["output_voltage_v"]
    assert result["measured"] == pytest.approx(DIVIDER_VOUT, rel=1e-3)
    assert result["status"] == "pass"


def test_runner_fails_real_simulation_off_target(tmp_path):
    folder = make_design(tmp_path, divider_spec(3.3), DIVIDER_SIM)
    proc = run_verify(folder, tmp_path)
    assert proc.returncode == 1, proc.stderr
    result = by_requirement(read_results(folder))["output_voltage_v"]
    assert result["measured"] == pytest.approx(DIVIDER_VOUT, rel=1e-3)
    assert result["status"] == "fail"


def test_verify_design(design):
    spec_path = design / "design" / "circuit-spec.json"
    spec = json.loads(spec_path.read_text())
    jsonschema.validate(spec, SPEC_SCHEMA)
    check = subprocess.run(
        [sys.executable, str(CHECK_SPEC), str(spec_path)],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout
    before = spec_path.read_bytes()
    proc = run_verify(design, ROOT)
    assert spec_path.read_bytes() == before
    assert proc.returncode in (0, 1), proc.stderr
    results = read_results(design)
    assert isinstance(results, list) and results, proc.stderr
    for result in results:
        jsonschema.validate(result, RESULT_SCHEMA)
        inside = abs(result["measured"] - result["target"]) <= result["tolerance"]
        assert result["status"] == ("pass" if inside else "fail"), result
    tolerances = spec.get("tolerances", {})
    expected = {name for name in MEASURED if isinstance(spec.get(name), (int, float)) and not isinstance(spec.get(name), bool)}
    assert set(by_requirement(results)) == expected
    for result in results:
        name = result["requirement"]
        assert result["target"] == spec[name], result
        assert result["tolerance"] == tolerances.get(name), result
    assert proc.returncode == 0, proc.stdout
