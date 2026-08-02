# Persistence

**Script:** [Persistence (script)](../persistence.py)

## Purpose

Single access point for `config/last_setup.json` — the user's saved setup
(monitor selection, display settings, per-window layouts, theme choices,
color thresholds, hue params). Every module that reads or writes that file
goes through here instead of opening it directly, so the atomic-write and
corruption-recovery guarantees apply everywhere. Also resolves the two base
directories the rest of the app builds paths from: bundled read-only
resources vs. user-writable data.

## Connections

### Uses
- none (stdlib only — `json`, `os`, `sys`, `pathlib`)

### Used by
- [Theme](theme.md) — each `ThemeScope` reads/writes its own `last_setup.json` slot
- [Color Management](color_management.md) — loads/saves hue params and value-color thresholds
- [Icons](icons.md) — `get_base_path()` to locate `assets/icons/`
- [Settings](settings.md) — `save_initial_settings()` updates the shared setup entry
- [Window Manager](window_manager.md) — checks/clears a window's remembered position
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — the setup screen restores the previous session and resolves the dialog window icon
- [Windows (subfolder)](../windows/___windows.md) — per-window geometry, splitter sizes and column widths
- [Collect (subfolder)](../collect/___collect.md) — `get_data_dir()` resolves the opt-in network-trace debug log path
- `main.py` — `get_base_path()` resolves `assets/icon.ico`, `setup/app_info.json`, `company.json`

## Functions

| Function | Description |
|----------|--------------|
| `get_base_path()` | Root for bundled, read-only resources. Frozen exe: PyInstaller's `sys._MEIPASS` (recreated every launch). Dev mode: the project root. |
| `get_data_dir()` | Root for user-writable app data. Frozen exe: `%APPDATA%\Vitals` (one-time migration from `%APPDATA%\PMUsage` if present). Dev mode: the project root. |
| `get_last_setup_path()` | `get_data_dir() / "config" / "last_setup.json"`. |
| `load_last_setup()` | Returns the saved setup dict, or `{}` if the file is missing or invalid. |
| `save_last_setup(data)` | Atomically writes the full setup dict (temp file + `os.replace`). |

## Design Decisions

- **`get_base_path()` vs. `get_data_dir()`.** A frozen exe's install
  directory is not writable without elevation, and `sys._MEIPASS` is wiped on
  every launch. Bundled assets are read from `get_base_path()`; anything the
  app writes goes to `get_data_dir()` instead. In dev mode both resolve to
  the project root, so the split is invisible until build.
- **One-time `PMUsage` -> `Vitals` migration.** If `%APPDATA%\PMUsage` exists
  and `%APPDATA%\Vitals` does not, `get_data_dir()` renames the old folder in
  place (same-volume, metadata-only) so existing users keep their settings. A
  failed rename is reported to stderr and the app proceeds with a fresh,
  empty folder rather than crashing.
- **Atomic writes.** `save_last_setup()` writes to a `.tmp` file first, then
  swaps it in with `os.replace()`, so a crash mid-write can never leave a
  truncated file behind.
- **Corruption recovery is a documented fallback, not an error.**
  `load_last_setup()` treats an unreadable or invalid file as `{}` (logged to
  stderr) rather than raising — the next save overwrites the bad file with
  valid content instead of the app failing forever on it.
