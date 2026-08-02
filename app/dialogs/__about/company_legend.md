# Company Legend

**Script:** [Company Legend (script)](../company_legend.py)

## Purpose

`CompanyLegendDialog` shows which color belongs to which company — the list
IS the color ranking itself: the busiest company first in plain contrast,
then the blue-to-red wheel by process count, then "Other" and "Unknown".
Each row expands to the individual process names behind it. Opened from a
per-mode settings dialog, it renders in the theme of the window that owns
it, and its two Saturation/Lightness sliders tune THAT theme's hue-wheel
parameters only — the other theme's wheel is untouched. A 1-second timer
re-reads the legend and rebuilds it only when the company set or counts
actually changed, since the process list moves constantly and the legend
must not flicker with it.

## Connections

### Uses
- [Color Management](../../__about/color_management.md) — `ProcessColorManager.get_legend()`, `get_hue_params()`, `update_hue_params()`, `get_singleton_companies()`, `get_company_processes()`
- [Persistence](../../__about/persistence.md) — `get_base_path()`, for the dialog window icon
- [Theme](../../__about/theme.md) — `ThemeScope`, read once at construction (the dialog is modal)

### Used by
- [Base Settings Dialog](base_dialog.md) — opened by `_show_legend()`, bound to the calling dialog's own scope

## Classes

### CompanyLegendDialog (QDialog)
`CompanyLegendDialog(scope, parent=None)`.

| Method | Description |
|--------|-------------|
| `_setup_ui()` | Builds the title, scroll area, ranking-legend note, the Saturation/Lightness slider pair, and the Close button. |
| `_rebuild_legend_content()` | Rebuilds the scroll area's row list from `ProcessColorManager.get_legend()`; expanded companies list their individual process names indented beneath them. |
| `_toggle_company(label)` | Expands/collapses one company's process-name sublist and rebuilds. |
| `_refresh_legend()` | The 1-second `QTimer` handler — compares the current legend's `(company, count)` keys against the cached ones and rebuilds only on an actual change, so the constantly-moving process list does not flicker the legend. |
| `_on_hue_params_changed()` | Reads both sliders, calls `ProcessColorManager.update_hue_params(palette, sat, light)` for this dialog's own theme, and rebuilds. |
