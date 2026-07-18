# Settings Dialog

**Script:** [settings_dialog.py (script)](settings_dialog.py)

---

## Purpose

Every dialog in the app: the startup launcher (`InitialSettingsDialog`) and
the per-mode settings dialogs (`CPUSettingsDialog`, `MemorySettingsDialog`,
`NetworkSettingsDialog`), plus the draggable color-scale widget and the
Company Legend popup. `BaseSettingsDialog` centralizes the dark palette,
window icon, and the row-builders duplicated across all four dialogs
(current/history rows, refresh rate, retention, font size, network options).

Also owns Windows autostart registration and the `last_setup.json` write for
the initial launcher screen.

---

## Connections

### Uses

- [Monitor](monitor.md) — `MonitorMode`, `get_commit_limit_bytes()` (Memory dialog's Commit color-scale max)
- [Persistence](persistence.md) — `get_base_path()` (dialog icon), `load_last_setup()`/`save_last_setup()`
- [Styles](styles.md) — `Colors`, `Defaults`, `FontScale`, `MEMORY_UNITS`, `NETWORK_UNITS`
- [Color Management](color_management.md) — `ProcessColorManager` (thresholds, hue params, legend data)
- [Network Monitor](network_monitor.md) — `get_link_speed_mbps()` (default max-speed spinbox value)

### Used by

- [Main Window](main_window.md) — `CPUWindow`/`MemoryWindow`/`NetworkWindow` open `CPUSettingsDialog`/`MemorySettingsDialog`/`NetworkSettingsDialog` from `_create_settings_dialog()`
- `main.py` — shows `InitialSettingsDialog` before any window is created

---

## Classes

### ColorScaleWidget

Paints a 5-color gradient bar with 4 draggable diamond handles marking zone
boundaries. Emits `thresholds_changed(list[int])` while dragging; each
settings dialog reads `.thresholds` on accept and persists it via
`ProcessColorManager.update_value_thresholds()`.

### CompanyLegendDialog

Shows every detected company with its assigned color and active process
count (expandable to list the individual process names), plus hue
saturation/lightness sliders. Self-refreshes every second
(`QTimer`) so it stays live while the collector discovers new companies.

### BaseSettingsDialog (QDialog)

Shared scaffolding — not instantiated directly.

| Method | Description |
|--------|-------------|
| `_apply_dark_theme()` | Sets the window icon and the shared dark `QPalette`. |
| `_make_label(text, size, bold, color)` / `_make_combo(items, default)` | Styled widget factories used by every dialog. |
| `_build_common_settings_rows(layout)` | Builds the 5 rows shared by all 4 dialogs: current processes, history records, refresh rate, history retention, font size. Returns the widgets for the caller to store as attributes. |
| `_build_network_settings_rows(layout, default_speed_mbps)` | Builds the network section (speed unit, sort mode, max download/upload spinboxes where `0` = auto) shared by `InitialSettingsDialog` and `NetworkSettingsDialog`. |

### InitialSettings / CPUSettings / MemorySettings / NetworkSettings (dataclasses)

Per-scope settings containers passed into/out of each dialog.
`InitialSettings` additionally exposes `cpu_threads`/`ram_gb` (auto-detected
via `psutil`) and `commit_limit_bytes` (via [Monitor](monitor.md)'s
`get_commit_limit_bytes()`) as computed properties.

### InitialSettingsDialog

The launcher shown before any window opens. Mode buttons (CPU/Memory/Network,
any combination) enable/disable the Start button and the network settings
section; restores the previous session via `_apply_last_setup(load_last_setup())`;
`_on_start()` registers/unregisters Windows autostart and calls
`_save_last_setup()` before accepting.

### CPUSettingsDialog / MemorySettingsDialog / NetworkSettingsDialog

Per-mode dialogs built from the shared rows plus mode-specific color-scale
sections (CPU: usage + Σ-total; Memory: usage + commit + their Σ-total
variants; Network: download + upload). Each dialog's `accept()` persists its
`ColorScaleWidget` thresholds via `ProcessColorManager.update_value_thresholds()`
before calling `super().accept()`.

---

## Functions

| Function | Description |
|----------|-------------|
| `is_startup_registered()` | Frozen exe: queries the `Vitals` Task Scheduler task. Dev mode: checks the HKCU `Run` registry value. |
| `set_startup_registered(enabled)` | Frozen exe: creates/deletes the same Task Scheduler task the installer manages (`/rl highest`) and cleans up any legacy `Run` entry. Dev mode: sets/deletes the HKCU `Run` value. |

---

## Design Decisions

**Task Scheduler for the frozen exe, not Registry Run.** Windows silently
skips `HKCU\...\Run` entries that point at a UAC-elevated executable, so a
Registry-only toggle would appear to work but never actually autostart the
installed app. `set_startup_registered()` instead creates a Task Scheduler
task named `Vitals` — the **same name** `setup/installer.nsi`'s optional
autostart section creates — so the in-app toggle and the installer manage
one shared task, not two competing autostart mechanisms.

**Legacy Run-entry cleanup runs unconditionally.** `_delete_legacy_run_value()`
removes any `Vitals` value left by pre-2.0.214 versions every time
`set_startup_registered()` runs on a frozen build, since that entry is dead
weight at best (points at an elevated exe Windows won't launch via Run).

**Color thresholds are read and persisted only on dialog `accept()`.**
`ColorScaleWidget` tracks its own `_thresholds` locally while dragging
(repainting and emitting `thresholds_changed` for a live view of the bar) —
it never touches `ProcessColorManager` itself. Only `accept()` reads the
widget's final `.thresholds` and calls
`ProcessColorManager.update_value_thresholds()`, so canceling the dialog
leaves the persisted (and in-memory) thresholds completely untouched.
