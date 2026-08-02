# Color Management

**Script:** [Color Management (script)](../color_management.py) ·
**Flow:** [diagram](../__flow/color_management.md)

## Purpose

Owns every data-driven coloring decision in Vitals — company-based process
name coloring, ranked by how many process names a company runs, and
value-based usage coloring (0-100% mapped to a 5-zone scale, independent per
monitor mode). The palettes themselves live in [Theme](theme.md); this
module only derives colors FROM them.

The manager is theme-LESS: every getter takes the `Palette` it must answer
for, rather than reading one "active" theme, because each monitor window
carries its own independent theme (owner 2026-07-26) — a single
active-theme cache would simply answer one window wrong while another is on
the opposite theme.

## Connections

### Uses
- [Theme](theme.md) — `THEMES`, `Palette`, `wheel_color()`, `shade_for_theme()` — every getter takes the palette its caller wants answered
- [Persistence](persistence.md) — `get_base_path()` to read `config/config.json`; `load_last_setup()`/`save_last_setup()` for per-theme hue params and saved thresholds
- `config/config.json` — `value_colors.ranges` (authored hues + thresholds)
- `psutil` — resolves an exe path per process for company lookup
- Windows `version.dll` (via `ctypes`) — reads `CompanyName` from PE version info

### Used by
- [Collect (subfolder)](../collect/___collect.md) — the collector calls `lookup_company()` and `refresh_active_counts()` every tick, off the UI thread
- [Windows (subfolder)](../windows/___windows.md) — each window's `get_process_color(name, palette)` / `get_value_color(pct, mode, palette)`, passing ITS OWN palette; the process context menu's color swatch
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — `get_value_ranges(mode, palette)`, `update_value_thresholds()`, `get_legend(palette)`, `get_hue_params(palette)` / `update_hue_params(...)`, `get_singleton_companies()`, `get_company_processes()` — the palette is that of the window whose dialog is open

## Classes

### ProcessColorManager
Thread-safe singleton (`QMutex`-guarded `__new__`), reached as
`ProcessColorManager()` from any thread.

| Method | Thread | Description |
|--------|--------|--------------|
| `lookup_company(name, pid)` | Background (collector) | Registers a process name and resolves its company via PE version info. Fast no-op once cached. |
| `refresh_active_counts(active_names)` | Background (collector) | Recomputes per-company counts AND ranks from the current tick's active names, every cycle. |
| `get_process_color(name, palette)` | Main | `QColor` for a process name in the caller's theme, or `None` if not yet looked up. |
| `get_company_name(name)` | Main | Resolved company name, or `None`. |
| `get_value_color(pct, mode, palette)` | Any | `QColor` for a 0-100 usage percentage under the given mode's thresholds, shaded for the caller's theme. |
| `get_value_ranges(mode, palette)` | Main | `list[tuple[float, QColor]]` for the color-scale widget, shaded for the caller's theme. |
| `update_value_thresholds(thresholds, mode)` | Main | Updates the 4 threshold values in-memory and persists them. |
| `get_hue_params(palette)` / `update_hue_params(palette, sat, light)` | Main | Read/write ONE theme's wheel saturation and lightness — the palette says which. |
| `get_legend(palette)` | Main | `list[tuple[str, QColor, int]]` — `(label, color, process_count)` sorted by count descending; the order IS the color ranking. |
| `get_singleton_companies()` / `get_company_processes(company)` | Main | Drill-down lists for the Company Legend dialog's expandable rows. |

`mode` is one of `"cpu"`, `"cpu_all"`, `"memory"`, `"memory_total"`,
`"memory_all"`, `"memory_all_total"`, `"net_dl"`, `"net_ul"`.

## Design Decisions

- **Eight independent value-threshold lists, not one shared scale.** A
  per-process row (e.g. one process at 20% CPU) and the sigma total row need
  different zone boundaries — 20% is high for one process but normal
  system-wide. Memory additionally splits Usage vs. Commit.
- **Ranks are recomputed every cycle, not frozen at discovery.** The rule
  ("most processes = plain contrast color") is a statement about the LIVE
  ranking, so the colors must follow it; ties are broken by company name so
  equal counts never flicker between cycles.
- **Both themes' shaded ranges are cached at once, rebuilt only on load or
  a threshold edit — never on a flip.** Since two windows can be dark and
  light simultaneously, invalidating one cached shade on a flip would leave
  the other window's colors stale. `get_value_color()` stays a dict lookup
  plus a list walk on the per-cell refresh hot path (root Priority A).
- **One authored hue set serves both themes.** `config/config.json`'s value
  colors are hues only; each theme re-shades them via `shade_for_theme()`
  rather than the config carrying a second, hand-maintained light-mode table
  (root Rule #19).
- **Temperature colors are not in this module.** `config/config.json`'s
  `temp_colors` section carries only `warning_threshold` / `critical_threshold`;
  the colors themselves come from the palette (`TEMP_WARNING`/`TEMP_CRITICAL`)
  so they follow the theme.
- **Legacy shape guards on load.** A `color_thresholds` or `hue_params`
  entry from `last_setup.json` that isn't shaped as the current per-theme
  dict is discarded rather than applied — pre-2.0/-2.2 versions stored both
  as flat structures.
- **Config errors fall back to defaults, not a crash.** An unreadable or
  invalid `config/config.json` is reported to stderr and the built-in
  default ranges are used instead — the same documented-fallback pattern as
  [Persistence](persistence.md).
