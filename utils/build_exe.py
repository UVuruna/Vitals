"""
Build executable for Process Monitor.

Usage:
    python utils/build_exe.py

Requires:
    pip install pyinstaller
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def build():
    """Build the executable using config from config/build.json."""
    root = Path(__file__).parent.parent
    config_path = root / "config" / "build.json"

    # Load config
    if not config_path.exists():
        print(f"ERROR: {config_path} not found!")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    app_name = config.get("app_name", "App")
    main_script = root / config.get("main_script", "main.py")
    icon_path = root / config.get("icon", "assets/icon.ico")
    one_file = config.get("one_file", True)
    windowed = config.get("windowed", True)
    hidden_imports = config.get("hidden_imports", [])
    data_files = config.get("data_files", [])

    # Check main script exists
    if not main_script.exists():
        print(f"ERROR: Main script not found: {main_script}")
        sys.exit(1)

    # Output directories (all in exe/ folder)
    exe_dir = root / "exe"

    # Clean old build artifacts
    if exe_dir.exists():
        shutil.rmtree(exe_dir)
    exe_dir.mkdir(exist_ok=True)

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", app_name,
        "--clean",
        "--distpath", str(exe_dir),
        "--workpath", str(exe_dir / "build"),
        "--specpath", str(exe_dir),
    ]

    if one_file:
        cmd.append("--onefile")
    if windowed:
        cmd.append("--windowed")

    if icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
    else:
        print(f"Warning: Icon not found: {icon_path}")

    # Add hidden imports
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])

    # Add data files (folders to bundle)
    for src, dst in data_files:
        src_path = root / src
        if src_path.exists():
            cmd.extend(["--add-data", f"{src_path};{dst}"])
        else:
            print(f"Warning: Data path not found: {src_path}")

    # Add main script
    cmd.append(str(main_script))

    print("Building executable...")
    print(f"Config: {config_path}")
    print(f"Output: {exe_dir}")
    print(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=root)

    if result.returncode == 0:
        exe_path = exe_dir / f"{app_name}.exe"
        print()
        print("=" * 50)
        print(f"SUCCESS! Executable created at:")
        print(f"  {exe_path}")
        print("=" * 50)
    else:
        print()
        print("BUILD FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    build()
