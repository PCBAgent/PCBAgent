#!/usr/bin/env python3
"""One deterministic stage, cancelled only by the user. Full logs stay on disk; stdout is compact JSON."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
STAGES = {
    "prepare": ["skills/requirements/check_spec.py", "skills/parts/choose_ic.py"],
    "verify": ["skills/circuit/verify.py"],
    "parts": ["skills/parts/lookup.py"],
    "netlist": ["skills/parts/netlist.py"],
}
INPUTS = ("design/circuit-spec.json", "design/ic.json", "design/skidl_sim.py", "parts/parts.json", "parts/skidl_kicad.py")


def run_command(command):
    """Wait without a deadline; clean up the process group on user cancellation."""
    proc = subprocess.Popen(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate()
        return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()


def execute(root, stage):
    root = Path(root).resolve()
    if not root.is_dir():
        return {"status": "environment_error", "reason": "Design directory does not exist"}
    folder = root / ".agent"
    folder.mkdir(exist_ok=True)
    state_path = folder / f"{stage}.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"failures": 0}
    fingerprint = hashlib.sha256(b"".join(name.encode() + (root / name).read_bytes()
        for name in INPUTS if (root / name).is_file())).hexdigest()
    started = time.monotonic()
    log = folder / f"{stage}-{time.time_ns()}.log"
    status, code, output = "pass", 0, ""
    for script in STAGES[stage]:
        argument = root / "design" / "circuit-spec.json" if script.endswith("check_spec.py") else root
        try:
            proc = run_command([sys.executable, str(REPO / script), str(argument)])
            output += f"{script}\n{proc.stdout}{proc.stderr}\n"
            code = proc.returncode
        except OSError as error:
            output += str(error)
            status, code = "environment_error", 127
            break
        if code:
            status = "unmet_requirement" if code == 1 else "execution_error"
            try:
                details = json.loads(proc.stdout)
                if isinstance(details, dict) and details.get("status") == "unverified":
                    status = "unverified"
            except (ValueError, TypeError):
                pass
            break
    log.write_text(output)
    state.update(failures=state.get("failures", 0) + 1 if code else 0,
                 failed_fingerprint=fingerprint if code else None, log=str(log), status=status)
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    lines = list(dict.fromkeys(line for line in output.splitlines() if line.strip() and not line.startswith("WARNING:")))
    return {"stage": stage, "status": status, "exit_code": code, "elapsed_s": round(time.monotonic()-started, 3),
            "failed_attempts": state["failures"], "summary": "\n".join(lines[-24:])[-3500:], "log": str(log)}


def main():
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--reset-budget", action="store_true", help="Clear diagnostic history (legacy option; retries are unlimited)")
    args = parser.parse_args()
    if args.reset_budget:
        (Path(args.design) / ".agent" / f"{args.stage}.json").unlink(missing_ok=True)
    result = execute(args.design, args.stage)
    print(json.dumps(result))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
