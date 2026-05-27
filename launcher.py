from __future__ import annotations

import os
import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

APP_ROOT = Path(__file__).resolve().parent
APP_FILE = APP_ROOT / "app.py"


def resolve_python() -> str:
    env_python = os.environ.get("CELLSEARCH_PYTHON")
    if env_python and Path(env_python).exists():
        return env_python

    candidates = [
        APP_ROOT / ".venv" / "Scripts" / "pythonw.exe",
        APP_ROOT / ".venv" / "Scripts" / "python.exe",
        APP_ROOT / "venv" / "Scripts" / "pythonw.exe",
        APP_ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    for command in ("pythonw", "python", "py"):
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


def main() -> int:
    if not APP_FILE.exists():
        show_error("app.py wurde nicht gefunden:\\n" + str(APP_FILE))
        return 1

    try:
        python_cmd = resolve_python()
        command = build_command(python_cmd)
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(command, cwd=APP_ROOT, creationflags=creationflags)
        return 0
    except Exception as exc:
        show_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
