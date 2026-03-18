#!/usr/bin/env python3
"""Windows launcher for running the Streamlit app like a desktop program."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys


APP_FILENAME = "app.py"
APP_TITLE = "Scholar Archive"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, APP_TITLE, 0x10)


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def candidate_project_dirs() -> list[Path]:
    candidates: list[Path] = [Path.cwd()]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir.parent])
    else:
        script_dir = Path(__file__).resolve().parent
        candidates.extend([script_dir, script_dir.parent])
    return unique_paths(candidates)


def find_project_dir() -> Path | None:
    for directory in candidate_project_dirs():
        if (directory / APP_FILENAME).is_file():
            return directory
    return None


def candidate_python_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    env_python = os.environ.get("SCHOLAR_ARCHIVE_PYTHON")
    if env_python:
        commands.append([env_python])

    if not getattr(sys, "frozen", False):
        commands.append([sys.executable])

    for name in ("py", "python", "pythonw"):
        path = shutil.which(name)
        if path:
            commands.append([path])

    deduped: list[list[str]] = []
    seen: set[str] = set()
    for command in commands:
        key = command[0].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(command)
    return deduped


def launch_streamlit(project_dir: Path) -> bool:
    app_path = project_dir / APP_FILENAME
    creation_flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

    for base_command in candidate_python_commands():
        command = [
            *base_command,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.headless=false",
        ]
        try:
            subprocess.Popen(
                command,
                cwd=project_dir,
                creationflags=creation_flags,
                close_fds=True,
            )
            return True
        except FileNotFoundError:
            continue
        except OSError:
            continue
    return False


def main() -> int:
    project_dir = find_project_dir()
    if project_dir is None:
        show_error(
            "Could not find app.py.\n\n"
            "Place ScholarArchive.exe in the project folder or keep it next to the repository."
        )
        return 1

    if launch_streamlit(project_dir):
        return 0

    show_error(
        "Could not start Streamlit.\n\n"
        "Make sure Python and the project dependencies are installed.\n"
        "If needed, set SCHOLAR_ARCHIVE_PYTHON to the interpreter you want to use."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
