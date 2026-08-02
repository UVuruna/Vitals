# Base Settings Dialog

**Script:** [Base Settings Dialog (script)](../base_dialog.py)

## Purpose

`BaseSettingsDialog` is the shared scaffolding every settings dialog is
built on: theme binding, the window icon, the label/combo/spinbox
factories, and the row builders for the settings blocks that would
otherwise be written four times over (`InitialSettingsDialog`,
`CPUSettingsDialog`, `MemorySettingsDialog`, `NetworkSettingsDialog`). It
also owns the **restyler** mechanism — the registry of closures that lets a
dialog follow a live theme flip instead of freezing at the palette that was
active when it was built.

## Connections

### Uses
- [Dialog Styles](dialog_styles.md) — `combo_style`, `slider_style`, `spinbox_style`, registered as restylers for every combo/slider/spinbox the factories build
- [Color Scale](color_scale.md) — `ColorScaleWidget`, built and returned by `_build_color_section()`
- [Company Legend](company_legend.md) — `CompanyLegendDialog`, opened by `_show_legend()`
- [Color Management](../../__about/color_management.md) — `ProcessColorManager.get_value_ranges()`, read by `_build_color_section()` to seed a scale's colors and thresholds
- [Persistence](../../__about/persistence.md) — `get_base_path()`, for the dialog window icon
- [Styles](../../__about/styles.md) — `Defaults`, the initial values for every row the factories build
- [Theme](../../__about/theme.md) — `ThemeScope`, the type every dialog binds to at construction

### Used by
- [Setup Dialog](setup_dialog.md) — `InitialSettingsDialog` subclasses `BaseSettingsDialog`
- [Mode Dialogs](mode_dialogs.md) — `CPUSettingsDialog`, `MemorySettingsDialog`, `NetworkSettingsDialog` all subclass it

## Classes

### BaseSettingsDialog (QDialog)
Not instantiated directly. `__init__(scope, parent=None)` binds `self._theme`
to the given `ThemeScope` for the dialog's whole lifetime.

| Method | Description |
|--------|-------------|
| `done(result)` | Clears the registered restylers before calling `super().done()` — breaks the dialog's self-reference cycle (see Design Decisions in the [folder doc](../___dialogs.md)). |
| `_restylers_list()` | The registered restyle closures, created on first use. |
| `_register_restyle(fn)` | Appends a restyle closure and calls it immediately. |
| `_themed_sheet(widget, builder)` | Registers a closure that sets `widget`'s stylesheet to `builder(self._theme.palette)`, now and on every flip. |
| `_apply_theme()` | Sets the window icon, builds a `QPalette` from `self._theme.palette`, and re-runs every registered restyler — both the initial styling pass and the theme-flip handler. |
| `_make_label(text, size=12, bold=False, color=None)` | Themed `QLabel` factory. `color` is a `Palette` ATTRIBUTE NAME (e.g. `"TEXT_MUTED"`), not a hex string, so the token — not a frozen color — survives a flip. |
| `_make_legend_btn()` | Builds the themed "Company Legend" button shared by the three per-mode dialogs. |
| `_build_color_section(layout, show_legend=True, mode="cpu", title=..., max_info="", scale_max=100)` | Adds a labeled `ColorScaleWidget` (and optional Legend button) to a layout; returns the widget so the caller reads `.thresholds` on accept. |
| `_show_legend()` | Opens `CompanyLegendDialog` bound to this dialog's own scope. |
| `_make_combo(items, default)` | Themed `QComboBox` factory. |
| `_build_common_settings_rows(layout)` | Builds the 5 rows every dialog shares: current processes, history records, refresh rate, history retention, font size. Returns the widgets for the caller to store as attributes. |
| `_build_network_settings_rows(layout, default_speed_mbps=0)` | Builds the network section (speed unit, sort mode, max download/upload spinboxes where `0` = auto) shared by `InitialSettingsDialog` and `NetworkSettingsDialog`. |

### Functions
| Function | Description |
|----------|-------------|
| `make_spinbox(default=1)` | Creates an unstyled 1–100 numeric input. Left unstyled deliberately — the caller registers it with `_themed_sheet`, which is what actually paints it; styling it here too would just be a duplicate a flip overwrites. |
