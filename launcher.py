from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


def detect_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT = detect_app_root()
APP_FILE = APP_ROOT / "app.py"
LAUNCHER_LOG = APP_ROOT / "launcher_debug.log"
APP_STDOUT_LOG = APP_ROOT / "app_stdout.log"
APP_STDERR_LOG = APP_ROOT / "app_stderr.log"
REQUIRED_PATHS = [
    APP_ROOT / "app.py",
    APP_ROOT / "hub",
    APP_ROOT / "bundled_tools",
    APP_ROOT / "assets",
]


def log(message: str):
    try:
        with LAUNCHER_LOG.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def resolve_python() -> str:
    env_python = os.environ.get("CELLSEARCH_PYTHON")
    if env_python and Path(env_python).exists():
        return env_python

    candidates = [
        APP_ROOT / ".venv" / "Scripts" / "python.exe",
        APP_ROOT / ".venv" / "Scripts" / "pythonw.exe",
        APP_ROOT / "venv" / "Scripts" / "python.exe",
        APP_ROOT / "venv" / "Scripts" / "pythonw.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    for command in ("python", "py", "pythonw"):
        resolved = shutil.which(command)
        if resolved:
            return resolved

    raise FileNotFoundError(
        "Kein Python Interpreter gefunden. Installiere Python oder setze CELLSEARCH_PYTHON auf deine python.exe."
    )


def build_command(python_cmd: str) -> list[str]:
    return [python_cmd, str(APP_FILE)]


def show_error(message: str):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("CellSearchHub Launcher", message)
    root.destroy()


def validate_layout() -> list[str]:
    missing: list[str] = []
    for required in REQUIRED_PATHS:
        if not required.exists():
            missing.append(str(required))
    return missing


def tail_text(path: Path, limit: int = 1200) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return data[-limit:]


def main() -> int:
    try:
        LAUNCHER_LOG.write_text("", encoding="utf-8")
        APP_STDOUT_LOG.write_text("", encoding="utf-8")
        APP_STDERR_LOG.write_text("", encoding="utf-8")
    except Exception:
        pass

    log(f"APP_ROOT={APP_ROOT}")
    log(f"APP_FILE={APP_FILE}")
    log(f"argv0={sys.argv[0] if sys.argv else ''}")
    try:
        log(f"cwd={Path.cwd()}")
    except Exception:
        pass

    missing = validate_layout()
    if missing:
        message = (
            "CellSearchHub erwartet app.py, hub, bundled_tools und assets direkt neben der EXE.\n\n"
            + "Erkannter Ordner:\n"
            + str(APP_ROOT)
            + "\n\nFehlende Pfade:\n- "
            + "\n- ".join(missing)
        )
        log("Missing layout: " + " | ".join(missing))
        show_error(message)
        return 1

    try:
        python_cmd = resolve_python()
        command = build_command(python_cmd)
        log(f"python_cmd={python_cmd}")
        log(f"command={' '.join(command)}")

        with APP_STDOUT_LOG.open("a", encoding="utf-8") as stdout_handle, APP_STDERR_LOG.open("a", encoding="utf-8") as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=APP_ROOT,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
            )
            time.sleep(2)
            return_code = process.poll()

        if return_code is not None and return_code != 0:
            stderr_tail = tail_text(APP_STDERR_LOG)
            stdout_tail = tail_text(APP_STDOUT_LOG)
            log(f"child_exit={return_code}")
            message = (
                f"Die App wurde gestartet, aber sofort mit Fehlercode {return_code} beendet.\n\n"
                + f"Ordner: {APP_ROOT}\n\n"
                + "app_stderr.log:\n"
                + (stderr_tail or "<leer>")
            )
            if stdout_tail and stdout_tail != stderr_tail:
                message += "\n\napp_stdout.log:\n" + stdout_tail
            show_error(message)
            return 1

        log("child_started_ok")
        return 0
    except Exception as exc:
        log(f"launcher_error={type(exc).__name__}: {exc}")
        show_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
