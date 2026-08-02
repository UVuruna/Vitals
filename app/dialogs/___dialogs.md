# dialogs/

Every dialog the app opens: the setup screen that configures all three
monitors at once, the three per-monitor settings dialogs and the shared base
they are built from, the two small widgets those dialogs are built out of
(the draggable color scale, the company legend popup), and the two
process-action confirmation dialogs shown from a monitor window's right-click
menu.

Every dialog here is bound to ONE `ThemeScope` at construction — a per-mode
dialog to the window that opened it, the setup screen to the app-wide scope
— so two open dialogs can be on different themes at the same time.

## Files

| File | Tier | One line |
|------|------|----------|
| `base_dialog.py` | Standard | `BaseSettingsDialog` — theme binding, widget factories, row builders and the restyler mechanism shared by all four settings dialogs — [about](__about/base_dialog.md) |
| `dialog_styles.py` | Standard | QSS builder functions (spinbox/slider/combo/buttons), each a function of a palette, never a frozen constant — [about](__about/dialog_styles.md) |
| `color_scale.py` | Standard | `ColorScaleWidget` — the draggable 5-zone gradient bar with 4 threshold handles — [about](__about/color_scale.md) |
| `company_legend.py` | Standard | `CompanyLegendDialog` — which color belongs to which company, plus the hue-wheel tuning sliders — [about](__about/company_legend.md) |
| `setup_dialog.py` | Algorithmic | `InitialSettingsDialog` — the app's front door; the only dialog with a live restyle path and the global Day/Night switch — [about](__about/setup_dialog.md) · [flow](__flow/setup_dialog.md) |
| `mode_dialogs.py` | Standard | `CPUSettingsDialog` / `MemorySettingsDialog` / `NetworkSettingsDialog` — the three per-monitor settings dialogs — [about](__about/mode_dialogs.md) |
| `process_dialog.py` | Standard | `KillConfirmDialog` / `PriorityDialog` — the two process-action confirmation dialogs — [about](__about/process_dialog.md) |
| `__init__.py` | Trivial | package docstring only |

## Connections

### Uses
- [Theme](../__about/theme.md) — `Palette`, `ThemeScope`, `app_theme()`, `window_theme()`; every dialog is bound to one scope at construction
- [Settings](../__about/settings.md) — `InitialSettings`, `CPUSettings`, `MemorySettings`, `NetworkSettings` — the dataclasses every dialog edits and returns; they live outside this folder because windows and the window manager read them too
- [Startup](../__about/startup.md) — `is_startup_registered()` / `set_startup_registered()`, read by the setup screen's autostart toggle
- [Persistence](../__about/persistence.md) — `get_base_path()` (dialog window icon), `load_last_setup()` (the setup screen restores the previous session)
- [Color Management](../__about/color_management.md) — `ProcessColorManager`, read by the color-scale sections and the legend, persisted to on a mode dialog's `accept()`
- [Day/Night Switch](../__about/theme_switch.md) — `DayNightSwitch`, the setup screen's global toggle
- [Theme Transition](../__about/transition.md) — `flip_app_theme()`, what the setup screen's switch calls
- [Styles](../__about/styles.md) — `Defaults`, `Fonts`, `MEMORY_UNITS`
- [Process Actions](../__about/process_actions.md) — `PRIORITY_CLASSES`, read by `process_dialog.py`
- [Collect (subfolder)](../collect/___collect.md) — `get_commit_limit_bytes()` (Memory dialog's Commit color-scale max), `get_link_speed_mbps()` (setup screen's default max-speed spinbox value)

### Used by
- [App (folder)](../___app.md) — `main.py` shows `InitialSettingsDialog` before any monitor window exists; `app/__init__.py` re-exports every dialog class; `app/tray.py` reopens `InitialSettingsDialog` from the tray's **Settings** action
- [Windows (subfolder)](../windows/___windows.md) — each monitor window's `_create_settings_dialog()` opens its per-mode dialog bound to that window's own `ThemeScope`; `process_menu.py` opens `KillConfirmDialog` / `PriorityDialog` with the window's palette

## Design Decisions

- **One `ThemeScope` per dialog, bound for life.** A per-mode dialog takes
  the scope of the window that opened it; the setup screen takes the
  app-wide `app_theme()`. That is what lets the CPU settings dialog sit dark
  while the Memory one is light — nothing here ever asks "what is the
  theme?", only "what is MY scope's theme?"
- **The restyler mechanism (`BaseSettingsDialog`).** Every widget the shared
  factories build registers a closure that rebuilds its stylesheet from
  `self._theme.palette`; `_apply_theme()` re-runs them all. `done()` clears
  the list before closing — every restyler closes over `self`, so leaving
  them registered would let a parentless dialog (the setup screen opened
  from the tray) survive its own close as a zombie with a live `changed`
  connection, until the cyclic collector happened to run.
- **QSS builders are functions of a palette, never module-level strings.**
  `dialog_styles.py` exists entirely to keep that true — a constant string
  would freeze whichever palette happened to be active at import time,
  exactly the bug `ThemeScope` exists to prevent.
- **The setup screen alone carries the global Day/Night switch.** It is
  shown before any monitor window exists, so it needs a theme control of its
  own; its switch calls `flip_app_theme()` (every window, not just itself).
  The per-mode dialogs are modal and never see a flip, so they style once
  and skip the `changed` connection entirely.
- **`mode_dialogs.py` holds all three per-monitor dialogs on purpose.** CPU,
  Memory and Network settings are one family — same shared rows, same Apply
  button, differing only in which color scales and extra controls each mode
  needs. Reading one means reading the family; the file is ~356 lines,
  comfortably under the ~1,000-line Structure Law threshold, so a further
  split would only scatter three cohesive twins.
- **`process_dialog.py` takes a plain `Palette`, not a scope.** Both dialogs
  are modal and read the palette once at construction from the window that
  opened them — there is no flip to follow, so a full `ThemeScope` binding
  would be dead weight.
- **The settings dataclasses and autostart logic live outside this folder.**
  `InitialSettings`/`CPUSettings`/`MemorySettings`/`NetworkSettings` live in
  `app/settings.py` because three layers read them (the dialogs that edit
  them, the windows that apply them, the window manager that distributes
  them) — no single dialog owns that shape. Windows autostart lives in
  `app/startup.py` for the same reason: the setup screen is just a caller.
