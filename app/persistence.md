# Persistence

**Script:** [persistence.py (script)](persistence.py)

---

## Purpose

Single access point for `config/last_setup.json` — the user's saved setup
(monitor selection, display settings, per-window layouts, color thresholds,
hue params). Every module that reads or writes that file goes through here
instead of opening it directly, so the atomic-write and corruption-recovery
guarantees apply everywhere.

Also resolves two distinct base directories used throughout the app:
bundled read-only resources vs. user-writable data.

---

## Connections

### Uses

- None — stdlib only (`json`, `os`, `sys`, `pathlib`).

### Used by

- [Color Management](color_management.md) — loads/saves hue params and value-color thresholds
- [Main Window](main_window.md) — loads/saves per-window geometry, splitter sizes, column widths
- [Settings Dialog](settings_dialog.md) — loads/saves the initial-dialog setup (`_save_last_setup`)
- [Network Monitor](network_monitor.md) — `get_data_dir()` resolves the opt-in debug log path
- `main.py` — `get_base_path()` resolves `assets/icon.ico`, `setup/app_info.json`, `company.json`

---

## Functions

| Function | Description |
|----------|-------------|
| `get_base_path()` | Root for bundled, read-only resources. Frozen exe: PyInstaller's `sys._MEIPASS` (temp extraction dir, recreated every launch). Dev mode: project root. |
| `get_data_dir()` | Root for user-writable app data. Frozen exe: `%APPDATA%\PMUsage`. Dev mode: project root (same as `get_base_path()` — no separate writable dir needed when running from source). |
| `get_last_setup_path()` | `get_data_dir() / "config" / "last_setup.json"`. |
| `load_last_setup()` | Returns the saved setup dict, or `{}` if the file is missing or invalid. |
| `save_last_setup(data)` | Atomically writes the full setup dict. |

---

## Design Decisions

**`get_base_path()` vs. `get_data_dir()`.** A frozen exe's install directory
(`Program Files\PMUsage`) is not writable without elevation, and PyInstaller's
`sys._MEIPASS` extraction directory is wiped on every launch. Bundled assets
(icons, `app_info.json`, `config.json` defaults) must be read from
`get_base_path()`; anything the app writes (`last_setup.json`, opt-in debug
logs) must go to `get_data_dir()` (`%APPDATA%\PMUsage`) instead. In dev mode
both resolve to the project root, so the distinction is invisible until build.

**Atomic writes.** `save_last_setup()` writes to a `.tmp` file first, then
swaps it in with `os.replace()`. A crash or forced shutdown mid-write can
never leave a truncated `last_setup.json` behind — the old file stays intact
until the new one is fully written.

**Corruption recovery is a documented fallback, not an error.** `load_last_setup()`
treats an unreadable or invalid file as `{}` (logging to stderr) rather than
raising. This matters because pre-atomic-write versions of the app could
leave a truncated file from an old crash; failing forever on that file would
strand the user with unrecoverable settings. The next `save_last_setup()`
overwrites it with valid content.
