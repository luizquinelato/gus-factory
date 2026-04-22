#!/usr/bin/env python3
"""
scripts/setup_venv.py — auth service
======================================
Creates .venv and installs requirements/install.txt.
Runs independently — no dependency on project-level scripts.

Usage:
    python services/auth/scripts/setup_venv.py
    python services/auth/scripts/setup_venv.py --force
"""
import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
INSTALL_TXT  = SERVICE_ROOT / "requirements" / "install.txt"
VENV_DIR     = SERVICE_ROOT / ".venv"


def python_bin(venv_dir: Path) -> Path:
    sub = "Scripts" if sys.platform == "win32" else "bin"
    exe = "python.exe" if sys.platform == "win32" else "python"
    return venv_dir / sub / exe


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Setup venv for {SERVICE_ROOT.name}.")
    parser.add_argument("--force", "-f", action="store_true", help="Recreate venv from scratch")
    args = parser.parse_args()

    print(f"\n📦 {SERVICE_ROOT.name}  ({SERVICE_ROOT})")

    if not INSTALL_TXT.exists():
        print("   ❌  requirements/install.txt not found.")
        sys.exit(1)

    if args.force and VENV_DIR.exists():
        print("   Removing existing venv...")
        shutil.rmtree(VENV_DIR)

    if not VENV_DIR.exists():
        print("   Creating venv...")
        venv.create(VENV_DIR, with_pip=True)
    else:
        print("   venv exists — reusing.")

    py = python_bin(VENV_DIR)
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], check=True)
    print("   Installing requirements/install.txt...")
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(INSTALL_TXT)], check=True)

    print(f"   ✅ {SERVICE_ROOT.name} ready.")


if __name__ == "__main__":
    main()
