# Settings Dialog

**Script:** [settings_dialog.py (script)](settings_dialog.py)

---

## Purpose

Every dialog in the app: the shared setup screen (`InitialSettingsDialog`)
and the per-mode settings dialogs (`CPUSettingsDialog`, `MemorySettingsDialog`,
`NetworkSettingsDialog`), plus the draggable color-scale widget and the
Company Legend popup. `BaseSettingsDialog` centralizes the theme, window
icon, and the row-builders duplicated across all four dialogs
(current/history rows, refresh rate, retention, font size, network options).

The **setup screen** is now reachable at any time from the tray's Settings
action, not just at startup, and configures all three monitors in one place
(owner 2026-07-24).

Also owns Windows autostart registration and the `last_setup.json` write for
the initial launcher screen.

---

## Connections

### Uses

- [Monitor](monitor.md) — `MonitorMode`, `get_commit_limit_bytes()` (Memory dialog's Commit color-scale max)
- [Persistence](persistence.md) — `get_base_path()` (dialog icon), `load_last_setup()`/`save_last_setup()`
- [Styles](styles.md) — `Defaults`, `FontScale`, `MEMORY_UNITS`, `NETWORK_UNITS`
- [Theme](theme.md) — `Palette`, `ThemeScope`, `app_theme()`. Every dialog is bound to ONE scope at construction — a per-mode dialog to the window that opened it, `InitialSettingsDialog` to the app-wide `app_theme()` — and every stylesheet builder takes that scope's palette
- [Theme Transition](transition.md) — `flip_app_theme()`, the setup screen's own switch (the GLOBAL flip)
- [Day/Night Switch](theme_switch.md) — the setup screen's own theme toggle
- [Color Management](color_management.md) — `ProcessColorManager` (thresholds, hue params, legend data)
- [Network Monitor](network_monitor.md) — `get_link_speed_mbps()` (default max-speed spinbox value)

### Used by

- [Main Window](main_window.md) — `CPUWindow`/`MemoryWindow`/`NetworkWindow` open `CPUSettingsDialog`/`MemorySettingsDialog`/`NetworkSettingsDialog` from `_create_settings_dialog()`
- [Tray Controller](tray.md) — opens `InitialSettingsDialog` from the menu's **Settings** action
- [Window Manager](window_manager.md) — consumes the `InitialSettings` the setup screen returns
- `main.py` — shows `InitialSettingsDialog` before any window is created

---

## Classes

### ColorScaleWidget

Paints a 5-color gradient bar with 4 draggable diamond handles marking zone
boundaries. `ColorScaleWidget(colors, thresholds, scope, parent=None, scale_max=100)`
— the `scope` decides which theme its handle outline and percentage labels
follow. Emits `thresholds_changed(list[int])` while dragging; each settings
dialog reads `.thresholds` on accept and persists it via
`ProcessColorManager.update_value_thresholds()`.

### CompanyLegendDialog

`CompanyLegendDialog(scope, parent=None)` — opened from a per-mode settings
dialog, so it renders in the theme of the window that owns it, and its
Saturation/Lightness sliders tune THAT theme's wheel params only. Shows every
detected company with its assigned color and active process count
(expandable to list the individual process names), plus hue
saturation/lightness sliders. Self-refreshes every second
(`QTimer`) so it stays live while the collector discovers new companies.

### BaseSettingsDialog (QDialog)

Shared scaffolding — not instantiated directly. `BaseSettingsDialog(scope, parent=None)`
binds the dialog to ONE `ThemeScope` for its whole lifetime: a per-mode
dialog gets the scope of the window that opened it, `InitialSettingsDialog`
gets `app_theme()`. That is what lets the CPU settings dialog be dark while
the Memory one is light at the same time.

| Method | Description |
|--------|-------------|
| `_apply_theme()` | Sets the window icon, this dialog's `self._theme.palette` as `QPalette`, and re-runs every registered restyler. Both the initial styling pass and the theme-flip handler. |
| `_register_restyle(fn)` / `_themed_sheet(widget, builder)` | Register a closure that (re)applies one widget's theme styling, and run it now. `_themed_sheet` calls `builder(self._theme.palette)`. |
| `_make_label(text, size, bold, color)` / `_make_combo(items, default)` | Styled widget factories used by every dialog; both self-register as restylers. `color` is a Palette ATTRIBUTE NAME (`"TEXT_MUTED"`), not a hex — the token is what survives a flip. |
| `_make_legend_btn()` | Builds the themed "Company Legend" button shared by all three per-mode dialogs. |
| `_build_color_section(layout, show_legend=True, mode="cpu", title=..., max_info="", scale_max=100)` | Adds one color-settings section (label + `ColorScaleWidget` + optional Legend button) to a dialog's layout; returns the `ColorScaleWidget` so the caller reads `.thresholds` on accept. |
| `_show_legend()` | Opens `CompanyLegendDialog` bound to this dialog's own scope. |
| `_build_common_settings_rows(layout)` | Builds the 5 rows shared by all 4 dialogs: current processes, history records, refresh rate, history retention, font size. Returns the widgets for the caller to store as attributes. |
| `_build_network_settings_rows(layout, default_speed_mbps)` | Builds the network section (speed unit, sort mode, max download/upload spinboxes where `0` = auto) shared by `InitialSettingsDialog` and `NetworkSettingsDialog`. |
| `done(result)` | Override: clears the registered restyler list, then calls `super().done(result)`. Breaks the dialog's self-reference cycle so it can be freed deterministically — see Design Decisions. |

#### The restyle registry

Every widget these factories build registers a closure that rebuilds its
stylesheet from `self._theme.palette`, so `_apply_theme()` can be re-run on a
flip. The per-mode dialogs are modal and never see one; the setup screen
carries its own Day/Night switch and connects to `app_theme().changed`, so
it restyles live.

Toggle buttons (the three mode buttons, the autostart switch) already had a
method that repaints them for their checked state — that method IS their
restyler, registered rather than duplicated. It is registered LAST, because
it touches widgets built further down `_setup_ui()`.

### InitialSettingsDialog

The setup screen. `first_run=False` (the tray's Settings action) changes the
subtitle and labels the primary button **Apply** instead of **Start
Monitoring**; everything else is identical, so there is one screen rather
than two.

Bound to `app_theme()`, not any window's scope — it exists before any
monitor window does. Its Day/Night switch is the GLOBAL one: unlike a
monitor header's switch, which flips that window alone, this one calls
`flip_app_theme()`, forcing one theme onto the app scope and every monitor
window (open or not). That is the whole reason the setup screen still
carries a switch now that each window has its own.

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
variants; Network: download + upload). Each takes
`(scope, parent=None, settings=None)` — the OPENING window hands in its own
`ThemeScope`, so the dialog matches that window's theme rather than a global
one. Each dialog's `accept()` persists its `ColorScaleWidget` thresholds via
`ProcessColorManager.update_value_thresholds()` before calling
`super().accept()`.

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

**`done()` clears the restyler list — the fix for a real zombie-dialog
leak.** Every restyler registered via `_register_restyle()`/`_themed_sheet()`
is a closure over `self`, so as long as one survives, the dialog holds a
live reference to itself. A parentless dialog (the setup screen opened from
the tray's **Settings** action) therefore outlived its own close as a
zombie with its `changed` connection to the theme still live, until
Python's cyclic collector happened to run — one more zombie accumulating
per open. Clearing `self._restylers_list()` in `done()`, before
`super().done()` runs, makes destruction deterministic instead of leaving
it to gc.
