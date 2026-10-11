"""Optional, failure-isolated recording of layout stage results."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def atomic_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class Recorder:
    def __init__(self, root, python, launch=True, speed=1):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.directory = root / "layout" / "demo" / f"{stamp}-{uuid4().hex[:8]}"
        self.directory.mkdir(parents=True)
        self.python = python
        self.disabled = False
        self.player = None
        self.data = {"version": 1, "status": "running", "producer_pid": os.getpid(), "events": []}
        self.path = self.directory / "manifest.json"
        atomic_json(self.path, self.data)
        atomic_json(self.directory.parent / "latest.json", {"manifest": str(self.path.relative_to(self.directory.parent))})
        if launch:
            try:
                log_path = self.directory / "playback.log"
                with log_path.open("w") as log:
                    self.player = subprocess.Popen(
                        [sys.executable, str(Path(__file__).with_name("demo.py")),
                         "--manifest", str(self.path), "--speed", str(speed)],
                        stdout=log, stderr=log, start_new_session=True,
                    )
                print(f"Demo playback log: {log_path}", file=sys.stderr)
            except OSError as error:
                print(f"Demo playback unavailable: {error}. Recording continues.", file=sys.stderr)

    def emit(self, kind, attempt=None, work=None, board=None, **details):
        """Publish only complete artifacts; a visualization failure never fails layout."""
        if self.disabled:
            return
        try:
            event = {"sequence": len(self.data["events"]), "kind": kind, "attempt": attempt, **details}
            if work is not None:
                destination = self.directory / f"attempt-{attempt}"
                destination.mkdir(exist_ok=True)
                artifacts = {}
                for source in sorted(Path(work).iterdir()):
                    if source.suffix not in {".kicad_pcb", ".kicad_pro", ".json", ".log"}:
                        continue
                    if source.name == "job.json":
                        continue
                    target = destination / source.name
                    temporary = target.with_suffix(target.suffix + ".tmp")
                    shutil.copy2(source, temporary)
                    temporary.replace(target)
                    artifacts[source.name] = str(target.relative_to(self.directory))
                event["artifacts"] = artifacts
                if board:
                    scene = destination / f"{Path(board).stem}.scene.json"
                    temporary = scene.with_suffix(".tmp")
                    subprocess.run(
                        [self.python, str(Path(__file__).with_name("kicad.py")), "scene",
                         str(destination / board), str(temporary)],
                        check=True, capture_output=True, text=True, timeout=60,
                    )
                    temporary.replace(scene)
                    event.update(board=artifacts[board], scene=str(scene.relative_to(self.directory)))
            self.data["events"].append(event)
            if kind in {"finished", "aborted"}:
                self.data["status"] = "complete" if kind == "finished" else "aborted"
            atomic_json(self.path, self.data)
        except Exception as error:
            self.disabled = True
            print(f"Demo recording stopped: {error}. Layout continues.", file=sys.stderr)
            self.data["status"] = "recording_failed"
            self.data["error"] = str(error)
            try:
                atomic_json(self.path, self.data)
            except OSError:
                pass
