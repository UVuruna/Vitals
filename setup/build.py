"""
Build PMUsage into a distributable package.

Steps:
  1. Generate ICO from SVG (svg_to_ico — supersampled multi-resolution)
  2. Run PyInstaller (--onedir mode) to create the exe
  3. Sign the exe with self-signed certificate (optional)
  4. Call NSIS to create the installer

Prerequisites:
  - pip install pyinstaller pillow
  - Run create_cert.py once (for code signing, optional)
  - Install NSIS (https://nsis.sourceforge.io/) and add to PATH

Usage:
    python setup/build.py
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# -- Paths ---------------------------------------------------------
SETUP_DIR = Path(__file__).parent
PROJECT_DIR = SETUP_DIR.parent
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"

ICON_PATH = PROJECT_DIR / "assets" / "icon.ico"
CERT_PATH = SETUP_DIR / "cert" / "PMUsage.pfx"
PASSWORD_PATH = SETUP_DIR / "cert" / "password.txt"
NSI_PATH = SETUP_DIR / "installer.nsi"
APP_INFO_PATH = SETUP_DIR / "app_info.json"
VERSION_INFO_PATH = SETUP_DIR / "version_info.txt"


def _load_password() -> str:
    if not PASSWORD_PATH.exists():
        raise FileNotFoundError(
            f"Password file not found: {PASSWORD_PATH}\n"
            "Create setup/cert/password.txt with the certificate password."
        )
    return PASSWORD_PATH.read_text(encoding="utf-8").strip()


def _load_app_info() -> dict:
    return json.loads(APP_INFO_PATH.read_text(encoding="utf-8"))


CERT_PASSWORD = _load_password()
APP_INFO = _load_app_info()
APP_NAME = APP_INFO["app_name"]
ENTRY_POINT = PROJECT_DIR / "main.py"


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = version.split(".")
    nums = [int(p) for p in parts]
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums[:4])


def generate_version_info():
    step("0/4  Generating version_info.txt from app_info.json")

    v = APP_INFO["version"]
    vt = _version_tuple(v)

    content = f"""\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt},
    prodvers={vt},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{APP_INFO["company"]}'),
         StringStruct(u'FileDescription', u'{APP_INFO["description"]}'),
         StringStruct(u'FileVersion', u'{v}'),
         StringStruct(u'InternalName', u'{APP_INFO["app_name"]}'),
         StringStruct(u'LegalCopyright', u'{APP_INFO["copyright"]}'),
         StringStruct(u'OriginalFilename', u'{APP_INFO["app_name"]}.exe'),
         StringStruct(u'ProductName', u'{APP_INFO["product_name"]}'),
         StringStruct(u'ProductVersion', u'{v}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
"""
    VERSION_INFO_PATH.write_text(content, encoding="utf-8")
    print(f"  Written: {VERSION_INFO_PATH}")
    print(f"  Version: {v}  Company: {APP_INFO['company']}")


def step(msg: str):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def run(cmd: list[str], **kwargs):
    """Run a command, print it, and check for errors."""
    print(f"  > {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        if result.stderr:
            print(f"  {result.stderr}")
        sys.exit(1)
    return result


def generate_ico():
    step("1/4  Generating ICO from SVG")
    run([sys.executable, str(SETUP_DIR / "svg_to_ico.py")])


def build_pyinstaller():
    step("2/4  Building exe with PyInstaller")

    # Clean previous build
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            print(f"  Cleaning {d}")
            shutil.rmtree(d)

    # Packages not used at runtime
    exclude_modules = [
        "numpy",
        "setuptools",
        "pkg_resources",
        "charset_normalizer",
        "unittest",
        "xmlrpc",
        "pydoc",
        "tkinter",
        # QWebEngine = Chromium (~500 MB), not needed
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineQuick",
    ]

    # Modules PyInstaller fails to detect automatically
    hidden_imports = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "psutil",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name", APP_NAME,
        "--icon", str(ICON_PATH),
        "--windowed",
        "--version-file", str(VERSION_INFO_PATH),
        # Bundle assets and config
        "--add-data", f"{PROJECT_DIR / 'assets'};assets",
        "--add-data", f"{PROJECT_DIR / 'config'};config",
    ]

    # Add hidden imports
    for mod in hidden_imports:
        cmd.extend(["--hidden-import", mod])

    # Add exclude flags
    for mod in exclude_modules:
        cmd.extend(["--exclude-module", mod])

    # Entry point (must be last)
    cmd.append(str(ENTRY_POINT))

    start = time.time()
    run(cmd)
    elapsed = time.time() - start
    print(f"  PyInstaller completed in {elapsed:.1f}s")

    exe_path = DIST_DIR / APP_NAME / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print(f"  ERROR: Expected exe not found: {exe_path}")
        sys.exit(1)

    # Copy ICO to dist root so NSIS shortcuts can reference $INSTDIR\icon.ico
    dist_ico = DIST_DIR / APP_NAME / "icon.ico"
    shutil.copy2(ICON_PATH, dist_ico)
    print(f"  Copied icon.ico to {dist_ico.parent}")

    print(f"  Output: {exe_path}")
    return exe_path


def sign_exe(exe_path: Path):
    step("3/4  Signing exe with certificate")

    if not CERT_PATH.exists():
        print(f"  WARNING: Certificate not found: {CERT_PATH}")
        print("  Run 'python setup/create_cert.py' first.")
        print("  Skipping signing...")
        return

    # Use signtool from Windows SDK
    signtool = shutil.which("signtool")
    if not signtool:
        # Try common Windows SDK locations
        sdk_paths = [
            Path(r"C:\Program Files (x86)\Windows Kits\10\bin"),
            Path(r"C:\Program Files\Windows Kits\10\bin"),
        ]
        for sdk_base in sdk_paths:
            if sdk_base.exists():
                versions = sorted(sdk_base.glob("10.*/x64/signtool.exe"))
                if versions:
                    signtool = str(versions[-1])
                    break

    if not signtool:
        print("  WARNING: signtool.exe not found.")
        print("  Install Windows SDK or add signtool to PATH.")
        print("  Skipping signing...")
        return

    cmd = [
        signtool, "sign",
        "/f", str(CERT_PATH),
        "/p", CERT_PASSWORD,
        "/fd", "SHA256",
        "/t", "http://timestamp.digicert.com",
        str(exe_path),
    ]

    run(cmd)
    print("  Exe signed successfully.")


def build_installer():
    step("4/4  Building installer with NSIS")

    makensis = shutil.which("makensis")
    if not makensis:
        # Try common NSIS locations
        nsis_paths = [
            Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
            Path(r"C:\Program Files\NSIS\makensis.exe"),
        ]
        for p in nsis_paths:
            if p.exists():
                makensis = str(p)
                break

    if not makensis:
        print("  ERROR: makensis.exe not found.")
        print("  Install NSIS from https://nsis.sourceforge.io/")
        sys.exit(1)

    cmd = [
        makensis,
        f"/DPROJECT_DIR={PROJECT_DIR}",
        f"/DDIST_DIR={DIST_DIR}",
        f"/DSETUP_DIR={SETUP_DIR}",
        f"/DAPP_VERSION={APP_INFO['version']}",
        str(NSI_PATH),
    ]

    run(cmd)

    installer_path = DIST_DIR / f"{APP_NAME}_Setup.exe"
    if installer_path.exists():
        print(f"  Installer: {installer_path}")
        size_mb = installer_path.stat().st_size / (1024 * 1024)
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print("  WARNING: Installer exe not found at expected location.")


def main():
    print(f"Building {APP_NAME}")
    print(f"Project: {PROJECT_DIR}")

    if not ENTRY_POINT.exists():
        print(f"ERROR: Entry point not found: {ENTRY_POINT}")
        sys.exit(1)

    svg_path = PROJECT_DIR / "assets" / "icon.svg"
    if not svg_path.exists():
        print(f"ERROR: SVG icon not found: {svg_path}")
        sys.exit(1)

    generate_version_info()
    generate_ico()
    exe_path = build_pyinstaller()
    sign_exe(exe_path)
    build_installer()

    step("BUILD COMPLETE")
    print(f"  Installer: {DIST_DIR / f'{APP_NAME}_Setup.exe'}")
    print()


if __name__ == "__main__":
    main()
