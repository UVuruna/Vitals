# Mode Dialogs

**Script:** [Mode Dialogs (script)](../mode_dialogs.py)

## Purpose

The three per-monitor settings dialogs — `CPUSettingsDialog`,
`MemorySettingsDialog`, `NetworkSettingsDialog` — opened from the gear
button in their window's header. All three are the same shape: the shared
rows from `BaseSettingsDialog`, then the color scales that mode owns, then
Apply. They live in one file deliberately (see the [folder doc](../___dialogs.md)'s
Design Decisions): reading one means reading the family. What differs is
exactly the per-mode part — which color scales exist, what "100%" means on
each, and which extra controls the mode needs (Memory's display unit,
Network's unit/sort/max-speed block). Each dialog is constructed with the
`ThemeScope` of the window that opened it, so the CPU dialog can be dark
while the Memory one is light; being modal, none of the three can see a
flip, so they style once instead of registering for `changed`.

## Connections

### Uses
- [Base Settings Dialog](base_dialog.md) — the shared base class, factories and row builders
- [Dialog Styles](dialog_styles.md) — `apply_button_style`
- [Color Management](../../__about/color_management.md) — `ProcessColorManager.update_value_thresholds()`, called on `accept()`
- [Settings](../../__about/settings.md) — `CPUSettings`, `MemorySettings`, `NetworkSettings`
- [Styles](../../__about/styles.md) — `MEMORY_UNITS`, for `_format_bytes_in_unit()`
- [Theme](../../__about/theme.md) — `ThemeScope`
- [System Query](../../collect/__about/system_query.md) — `get_commit_limit_bytes()`, the Memory dialog's Commit color-scale max

### Used by
- [App (folder)](../../___app.md) — `app/__init__.py` re-exports all three dialog classes
- [CPU Window](../../windows/__about/cpu_window.md) — `_create_settings_dialog()` returns `CPUSettingsDialog(self._theme, self, self._settings)`
- [Memory Window](../../windows/__about/memory_window.md) — returns `MemorySettingsDialog(self._theme, self, self._settings)`
- [Network Window](../../windows/__about/network_window.md) — returns `NetworkSettingsDialog(self._theme, self, self._settings)`

## Functions

| Function | Description |
|----------|-------------|
| `_format_bytes_in_unit(total_bytes, unit)` | Formats a byte count in the user's selected memory unit (KB/MB/GB) for a color section's `max_info` label. |

## Classes

### CPUSettingsDialog (BaseSettingsDialog)
`CPUSettingsDialog(scope, parent=None, settings=None)`. No mode selection,
no memory unit. Two color sections: per-core usage (`mode="cpu"`) and total
usage across all cores (`mode="cpu_all"`, which also carries the Company
Legend button). `accept()` persists both scales' thresholds before calling
`super().accept()`.

### MemorySettingsDialog (BaseSettingsDialog)
`MemorySettingsDialog(scope, parent=None, settings=None)`. Adds the display
unit combo (KB/MB/GB) and four color sections: usage, commit, and their
`_all` (summed-across-processes) variants — `commit_limit_bytes` comes from
`get_commit_limit_bytes()`. `accept()` persists all four scales' thresholds.

### NetworkSettingsDialog (BaseSettingsDialog)
`NetworkSettingsDialog(scope, parent=None, settings=None)`. Adds the shared
network settings rows (speed unit, sort mode, max download/upload) plus two
color sections: download and upload. `accept()` persists both scales'
thresholds.

Each dialog also implements `_load_settings()` (push a settings dataclass
into the widgets) and `get_settings()` (read the widgets back into a fresh
settings dataclass) — the same pair `InitialSettingsDialog` implements, kept
per-class rather than shared because each mode's dataclass shape differs.
