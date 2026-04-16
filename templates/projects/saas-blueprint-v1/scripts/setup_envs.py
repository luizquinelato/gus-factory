#!/usr/bin/env python3
"""
scripts/setup_envs.py — SaaS Blueprint V1 (project-level)
==========================================================
Creates venvs and installs dependencies. Reads requirements/install.txt.

Entry types (detected by filename):
  services/backend/requirements/install.txt  → pip: .venv at services/backend/
  requirements/common.txt                    → pip: .venv at project root
  services/frontend/package.json             → npm install (always idempotent)
  services/backend                           → delegates to setup_venv.py (legacy)

The venv location for pip entries is always path.parent.parent.
--force only affects pip entries (recreates .venv); npm is always idempotent.

Usage:
    python scripts/setup_envs.py                   # all services
    python scripts/setup_envs.py --backend         # backend only
    python scripts/setup_envs.py --auth            # auth only
    python scripts/setup_envs.py --force / -f      # recreate Python venvs
    python scripts/setup_envs.py --backend -f      # backend venv recreated
"""
import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTALL_TXT  = PROJECT_ROOT / "requirements" / "install.txt"

CYAN, RESET = "\033[36m", "\033[0m"


def _rmtree(path: Path) -> None:
    """Remove a directory tree.
    On Windows, delegates to cmd /c rd to handle executables locked by the current process."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "rd", "/s", "/q", str(path)],
            capture_output=True,
        )
        if result.returncode != 0 and path.exists():
            raise PermissionError(f"Could not remove {path}:\n{result.stderr.decode()}")
    else:
        shutil.rmtree(path)


def _svc_banner(name: str) -> str:
    """Print a cyan service header. Returns the closing bar string to print after the block."""
    dashes = "\u2500" * 16
    bar    = "\u2500" * (32 + len(name) + 2)
    print(f"\n{CYAN}{dashes} {name} {dashes}{RESET}")
    return f"{CYAN}{bar}{RESET}"


def python_bin(venv_dir: Path) -> Path:
    sub = "Scripts" if sys.platform == "win32" else "bin"
    exe = "python.exe" if sys.platform == "win32" else "python"
    return venv_dir / sub / exe


def read_entries() -> list[dict]:
    """Parse install.txt → [{name, path, kind}, ...]."""
    if not INSTALL_TXT.exists():
        print(f"\u274c  {INSTALL_TXT} not found.")
        return []
    entries = []
    for line in INSTALL_TXT.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path = PROJECT_ROOT / line
        if path.is_file():
            if path.name == "package.json":
                kind = "npm"
                name = path.parent.name
            else:
                kind = "requirements_file"
                service_root = path.parent.parent
                name = service_root.name if service_root != PROJECT_ROOT else "root"
        elif path.is_dir():
            kind = "service_dir"
            name = path.name
        else:
            print(f"\u26a0\ufe0f  Not found: {line} \u2014 skipping")
            continue
        entries.append({"name": name, "path": path, "kind": kind})
    return entries


def setup_requirements_file(entry: dict, force: bool) -> bool:
    """Create venv at path.parent.parent, install the requirements file."""
    req_file     = entry["path"]
    service_root = req_file.parent.parent
    venv_dir     = service_root / ".venv"

    close = _svc_banner(entry["name"])

    if force and venv_dir.exists():
        print("   Removing existing venv...")
        _rmtree(venv_dir)
        if venv_dir.exists():
            print("   \u26a0\ufe0f  Venv parcialmente removido \u2014 arquivos em uso por outro processo.")
            print("      Feche qualquer terminal usando este venv e tente novamente.")
            print(close)
            return False

    # Broken venv: directory exists but pyvenv.cfg is missing — recreate
    if venv_dir.exists() and not (venv_dir / "pyvenv.cfg").exists():
        print("   \u26a0\ufe0f  Venv corrompido (pyvenv.cfg ausente) \u2014 recriando...")
        _rmtree(venv_dir)

    if not venv_dir.exists():
        print("   Creating venv...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    else:
        print("   venv exists \u2014 reusing.")

    py = python_bin(venv_dir)
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], check=True)
    print(f"   Installing {req_file.relative_to(PROJECT_ROOT)}...")
    result = subprocess.run([str(py), "-m", "pip", "install", "-r", str(req_file)]).returncode == 0
    print(close)
    return result


def setup_npm(entry: dict) -> bool:
    """Run npm install in the service directory (always idempotent, ignores --force)."""
    service_root = entry["path"].parent
    close = _svc_banner(entry["name"])
    print("   Running npm install...")
    result = subprocess.run(["npm", "install"], cwd=service_root, shell=sys.platform == "win32").returncode == 0
    print(close)
    return result


def setup_service_dir(entry: dict, force: bool) -> bool:
    """Delegate to the service's own scripts/setup_venv.py (legacy)."""
    script = entry["path"] / "scripts" / "setup_venv.py"
    close = _svc_banner(entry["name"])
    if not script.exists():
        print(f"   \u26a0\ufe0f  scripts/setup_venv.py not found \u2014 skipping.")
        print(close)
        return False
    cmd = [sys.executable, str(script)] + (["--force"] if force else [])
    result = subprocess.run(cmd).returncode == 0
    print(close)
    return result


def main() -> None:
    entries = read_entries()
    if not entries:
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Setup Python envs for this project.")
    parser.add_argument("--backend",      action="store_true", help="Setup backend only")
    parser.add_argument("--auth",         action="store_true", help="Setup auth only")
    parser.add_argument("--frontend",     action="store_true", help="Setup frontend only")
    parser.add_argument("--frontend-etl", action="store_true", dest="frontend_etl", help="Setup frontend-etl only")
    parser.add_argument("--force", "-f",  action="store_true", help="Recreate venv from scratch")
    args = parser.parse_args()

    any_flag = args.backend or args.auth or args.frontend or args.frontend_etl
    if any_flag:
        targets = [e for e in entries if (
            (args.backend      and e["name"] == "backend") or
            (args.auth         and e["name"].startswith("auth")) or
            (args.frontend     and e["kind"] == "npm" and "etl" not in e["name"]) or
            (args.frontend_etl and e["kind"] == "npm" and "etl" in e["name"])
        )]
    else:
        targets = entries

    print(f"\U0001f680 Setup \u2014 {PROJECT_ROOT.name}")
    print(f"   Entries: {', '.join(e['name'] for e in targets)}")

    ok = 0
    for e in targets:
        if e["kind"] == "npm":
            ok += setup_npm(e)
        elif e["kind"] == "requirements_file":
            ok += setup_requirements_file(e, args.force)
        else:
            ok += setup_service_dir(e, args.force)

    print(f"\n\u2705 Done \u2014 {ok}/{len(targets)} entries ready.")


if __name__ == "__main__":
    main()
