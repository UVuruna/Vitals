# Build Orchestrator

**Script:** [Build Orchestrator (script)](../build.py)

## Purpose

Orchestrates the full desktop build for Vitals: generate the Windows version
resource, render the ICO, run PyInstaller, sign the exe, build the NSIS
installer, sign the installer, and finish with a fail-closed verification
gate that asserts the built artifacts actually carry the metadata and
signatures every earlier step only claims to produce. Run directly —
`python setup/build.py` — never imported. See [Setup (folder)](../___setup.md)
for the pipeline diagram and the design rationale behind each step.

## Connections

### Uses
- [SVG to ICO](svg_to_ico.md) — `generate_ico()` runs it as a subprocess
  (`python setup/svg_to_ico.py`), not an import

### Used by
- none (run directly via `python setup/build.py`; not imported by any other
  module)

## Functions

- `_load_password() / _load_app_info() / _load_company()` — module-level
  loaders for `setup/cert/password.txt`, `setup/app_info.json` and the
  monorepo-root `company.json`; `_load_password` raises `FileNotFoundError`
  with a "run `create_cert.py`" hint when the password file is missing.
- `_version_tuple(version) -> tuple[int, int, int, int]` — splits the dotted
  version string and pads it to the four components the Windows VERSIONINFO
  structure requires.
- `step(msg)` — prints a banner line between pipeline stages; cosmetic only.
- `run(cmd, mask=None, **kwargs)` — the single subprocess wrapper every step
  uses: stdout is left inherited so PyInstaller/NSIS still stream progress
  live, stderr is captured so a failure prints the real error, and a
  non-zero return code calls `sys.exit(1)`. `mask` lets a value (the
  certificate password) be printed as `***` while the real value still
  reaches the process.
- `generate_version_info()` — writes `setup/version_info.txt` (gitignored,
  regenerated every build) from `app_info.json` + `company.json`; this is
  the file PyInstaller's `--version-file` embeds into the exe.
- `generate_ico()` — runs `svg_to_ico.py` as a subprocess.
- `build_pyinstaller() -> Path` — cleans `dist/`/`build/`, then runs
  PyInstaller in `--onedir --windowed --uac-admin` mode with
  `--version-file`, bundling `assets/`, only `config/config.json` (not the
  whole `config/` folder), `app_info.json` and the root `company.json`.
  Copies `icon.ico` to the dist root so the NSIS shortcuts can reference
  `$INSTDIR\icon.ico`. Returns the built exe's path.
- `sign_file(file_path) -> bool` — the one reusable Authenticode signer.
  Looks up `signtool.exe` on `PATH`, then in the known Windows SDK install
  locations. Returns `False` (with a warning, build continues unsigned) if
  the certificate or signtool cannot be found. The certificate password is
  read lazily HERE, at signing time, so a missing `setup/cert/` folder never
  aborts the build before PyInstaller/NSIS even run.
- `sign_exe(exe_path)` — calls `sign_file` on the freshly built inner exe.
- `build_installer()` — locates `makensis.exe`, invokes it against
  `installer.nsi` with `/D` flags carrying `PROJECT_DIR`, `DIST_DIR`,
  `SETUP_DIR`, `APP_VERSION`, `APP_PUBLISHER`, `APP_URL`; then calls
  `sign_file` on the produced installer.
- `_powershell(script) -> str` — runs one PowerShell command, returns its
  trimmed stdout; used by `verify_build` to query `Get-Item` and
  `Get-AuthenticodeSignature`.
- `verify_build(exe_path, installer_path)` — the fail-closed gate. Reads the
  exe's `CompanyName`/`FileVersion` and compares them against
  `company.json`/`app_info.json`; when both a certificate AND a password
  file exist, also asserts `Get-AuthenticodeSignature` is not
  `NotSigned`/empty on both the exe and the installer. Collects every
  problem before printing them, then `sys.exit(1)` if any were found.
- `main()` — runs the pipeline in order: `generate_version_info` ->
  `generate_ico` -> `build_pyinstaller` -> `sign_exe` -> `build_installer`
  -> `verify_build`. Exits early if `main.py` or `assets/icon.svg` is
  missing.
