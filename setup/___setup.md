# setup/

The Windows desktop build pipeline: turns the SVG logo and the Python source
into a signed, installable `Vitals_Setup.exe`. Everything here is invoked
manually (`python setup/build.py`) or as part of the monorepo's GIT RELEASE
step (`rules/SHIP.md`) — nothing in `app/` imports from this folder.

## Files

| File | Tier | One line |
|------|------|----------|
| `build.py` | Standard | 7-step build orchestrator, ends in a fail-closed verify gate — [about](__about/build.md) |
| `create_cert.py` | Standard | One-time self-signed code-signing certificate generator — [about](__about/create_cert.md) |
| `svg_to_ico.py` | Standard | Supersampled SVG -> multi-resolution ICO renderer, run by `build.py` as a subprocess — [about](__about/svg_to_ico.md) |
| `app_info.json` | Config | Single source of truth for `version`, `name`, `description`, `exe_name`, `installer_name` — not Python, no own doc |
| `installer.nsi` | Config | NSIS installer script — shortcuts, autostart, uninstaller, legacy-PMUsage cleanup — not Python, no own doc |
| `cert/` | — | Gitignored — holds `{name}.pfx` and `password.txt`; back up externally, never commit |
| `version_info.txt` | — | Gitignored — regenerated every build by `generate_version_info()` from `app_info.json` |

## Connections

### Uses
- [Entry Point](../__about/main.md) — `main.py` is the PyInstaller entry
  point bundled by `build_pyinstaller()`
- `assets/`, `config/config.json` — bundled into the exe via PyInstaller
  `--add-data`; only `config.json` ships, never the whole `config/` folder
  (that would also ship the developer's personal `config/last_setup.json`)

### Used by
- none (invoked directly by the owner via `python setup/build.py`, and by
  the monorepo's GIT RELEASE step in `rules/SHIP.md` — never imported by
  another module)

## Design Decisions

The 7-step pipeline:

```mermaid
flowchart LR
    A[SVG -> ICO] --> B[Version Info]
    B --> C[PyInstaller --onedir]
    C --> D[Sign exe]
    D --> E[NSIS Installer]
    E --> F[Sign Installer]
    F --> G[VERIFY\nfail-closed]
```

- **`verify_build()` is a fail-closed gate, not a formality.** Every step
  before it fails SILENTLY: PyInstaller without `--version-file` still
  builds an exe, just with an empty `CompanyName`; a skipped signing step
  just yields an unsigned file; the process still exits 0. `verify_build()`
  is the one place that asserts on the built OUTPUT — exe `CompanyName`
  matches `company.json`, exe `FileVersion` contains `app_info.json`'s
  version, and (when a certificate is configured) BOTH the exe and the
  installer carry an Authenticode signature — and calls `sys.exit(1)` if any
  of that is false, per `rules/SHIP.md`'s build contract.
- **`--onedir`, not `--onefile`** — lower RAM, faster startup, fewer AV
  false positives (per `rules/SHIP.md`).
- **`--uac-admin`** — the Network monitor's ETW kernel trace needs
  elevation, so the whole app runs elevated from launch.
- **Autostart uses Task Scheduler `/rl highest`, not the Registry `Run`
  key.** `installer.nsi`'s `SecAutostart` section creates a scheduled task
  because Windows silently skips a Registry `Run` entry for an elevated app
  — the registry route would look like it worked and simply never fire.
- **`sign_file()` is the ONE reusable signer** (root Rule #5), applied to
  BOTH the inner exe (step 3) and the final installer (step 5). Signing only
  the inner exe would ship an unsigned installer — the file the user
  actually downloads and runs — which defeats the SmartScreen mitigation
  signing exists for.
- **`setup/cert/` is gitignored and must be backed up externally** — losing
  it means re-signing every future build with a new, untrusted certificate.
  The certificate password is read lazily, only when `sign_file()` actually
  needs it, so a missing `cert/` folder does not abort the build before
  PyInstaller/NSIS even run — it just ships unsigned, with a warning.
- **`installer.nsi`'s `SecMain` unconditionally cleans up the old PMUsage
  install** (kills the process, deletes its scheduled task, shortcuts, and
  uninstall registry key) so upgrading from the pre-rename app leaves
  nothing behind, even though every one of those commands is a no-op on a
  fresh machine.
