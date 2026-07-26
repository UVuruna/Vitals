# Color Management

**Script:** [color_management.py (script)](color_management.py)

---

## Purpose

Handles data-driven coloring only. The palettes live in [Theme](theme.md),
not here — this module owns:

- **Company-based coloring**, ranked by how many process names a company runs:
  the busiest company is plain contrast (white on dark, black on light),
  every other named company walks a **blue → red** wheel as its count drops,
  singleton companies share the last (red) "Other" slot, and processes with
  no company info are the reserved **gray** "Unknown".
- **Value-based coloring** — eight independent threshold sets (CPU, CPU-Σ-total,
  Memory, Memory-Commit, Memory-Σ-total, Memory-Commit-Σ-total, Network
  download, Network upload) each map 0–100% to one of 5 colors.

Both are **theme-aware**, but the manager itself is **theme-LESS**: every
getter takes the `Palette` it must answer for, rather than reading one
"active" theme. Each monitor window carries its own theme now, so one dark
and one light table can be on screen at the same time — a single active-theme
cache would simply answer one of them wrong. Both themes' shaded value ranges
are held at once and rebuilt on load and on a threshold edit, never on a
flip.

Default thresholds are read from `config/config.json`; user overrides
persist to `config/last_setup.json` via [Persistence](persistence.md).

---

## Connections

### Uses

- `config/config.json` — `value_colors.ranges` default thresholds
- [Theme](theme.md) — `Palette`, `THEMES`, `wheel_color()`, `shade_for_theme()` — every getter takes the palette its caller wants answered, so the manager never reads a "current" theme of its own
- [Persistence](persistence.md) — `load_last_setup()`/`save_last_setup()` for per-theme hue params and saved thresholds
- `psutil` — resolves an exe path per process for company lookup
- Windows `version.dll` (via `ctypes`) — reads `CompanyName` from PE version info

### Used by

- [Main Window](main_window.md) — `get_process_color(name, palette)`, `get_value_color(pct, mode, palette)`, `get_company_name()`, `lookup_company()`, `refresh_active_counts()` (the last two called every tick by [Monitor](monitor.md)'s collector loop). Each window passes ITS OWN palette.
- [Settings Dialog](settings_dialog.md) — `get_value_ranges(mode, palette)`, `update_value_thresholds()`, `get_legend(palette)`, `get_hue_params(palette)`, `update_hue_params(palette, sat, light)`, `get_singleton_companies()`, `get_company_processes()` — the palette is the one of the window whose dialog is open

---

## Classes

### ProcessColorManager

Thread-safe singleton (`QMutex`-guarded `__new__`), accessed as
`ProcessColorManager()` from any thread.

#### Company-Based Coloring

Colors follow the **ranking** the legend shows — most processes first:

```
EVERY REFRESH, given the companies of the currently active processes:
    counts    = number of distinct process names per company
    multi     = companies with count > 1, sorted by count DESC, then name ASC
    rank[c]   = position of company c in `multi`   (0 = the most processes)
    slots     = max(len(multi) - 1, 0) + 1         # ranks 1.. plus "Other"

FOR a process name:
    IF it has no company             → COMPANY_UNKNOWN  (gray, reserved)
    ELSE IF rank == 0                → COMPANY_TOP      (white on dark / black on light)
    ELSE IF the company is a singleton → wheel slot `slots - 1`  ("Other", red)
    ELSE                             → wheel slot `rank - 1`
```

Wheel slot 0 is blue and the last slot is red, stepping counter-clockwise
through cyan, green and yellow (see [Theme](theme.md)'s `wheel_hue`).

Ties are broken by company name, so two companies with the same count keep a
stable order — and therefore stable colors — between cycles.

Saturation and lightness are **per theme**: `0.84`/`0.84` on dark (vivid
pastels) and `0.84`/`0.34` on light (deep tints readable on a pale surface).
Both pairs are user-tunable via the Company Legend dialog's sliders, and
tuning one theme never disturbs the other.

#### Methods

| Method | Thread | Description |
|--------|--------|--------------|
| `lookup_company(name, pid)` | Background (collector) | Registers a process name and resolves its company via PE version info. Fast no-op for already-cached names. |
| `refresh_active_counts(active_names)` | Background (collector) | Recomputes per-company counts AND ranks from the current tick's active names every cycle. |
| `get_process_color(name, palette)` | Main | `QColor` for a process name in the caller's theme, or `None` if not yet looked up. |
| `get_company_name(name)` | Main | Resolved company name, or `None`. |
| `get_value_color(pct, mode, palette)` | Any | `QColor` for a 0–100 usage percentage under the given mode's thresholds, shaded for the caller's theme. |
| `get_value_ranges(mode, palette)` | Main | `list[tuple[float, QColor]]` for `ColorScaleWidget` display, shaded for the caller's theme. |
| `update_value_thresholds(thresholds, mode)` | Main | Updates the 4 threshold values in-memory and persists them. Unchanged by the per-window theme split — thresholds are shared, only the shading differs. |
| `get_hue_params(palette)` / `update_hue_params(palette, sat, light)` | Main | Read/write ONE theme's wheel saturation and lightness — the palette says which. |
| `get_legend(palette)` | Main | `list[tuple[str, QColor, int]]` — `(label, color, process_count)` sorted by count descending, shaded for the caller's theme; the order IS the color ranking. Includes `"Other"` (singletons, red slot) and `"Unknown"` (no company info, gray). |
| `get_singleton_companies()` / `get_company_processes(company)` | Main | Drill-down lists for the Company Legend dialog's expandable rows. |

`mode` is one of: `"cpu"`, `"cpu_all"`, `"memory"`, `"memory_total"`,
`"memory_all"`, `"memory_all_total"`, `"net_dl"`, `"net_ul"`.

---

## Design Decisions

**Value thresholds are eight independent lists, not one shared scale.**
The per-row color (e.g. one process's CPU %) and the Σ total-row color need
different zone boundaries — a process using 20% CPU is high, but the
system-wide total is normal at 20%. `_DEFAULT_VALUE_RANGES_CPU_ALL` and
`_DEFAULT_VALUE_RANGES_MEM_ALL` give the Σ rows their own defaults; Memory
additionally splits Usage vs. Commit.

**Ranks are recomputed every cycle, not frozen at discovery.** The owner's
rule is that the company with the MOST processes is the plain contrast color,
which is a statement about the live ranking — so the colors have to follow
it. The cost is that a company changing rank changes color; in practice the
top ranks are stable (the OS vendor dominates), and the name tie-break keeps
equal counts from swapping back and forth.

**Theme-derived colors are cached, not recomputed per cell — and BOTH themes
are cached at once.** `_rebuild_themed_ranges()` re-shades all eight
threshold lists for every theme in `THEMES`, on load and on a threshold edit.
There is no "on a flip" case anymore: since two windows can be dark and light
simultaneously, invalidating one cached shade on a flip would leave the other
window's colors stale. `get_value_color()` stays a dict lookup (by theme
name) plus a plain list walk on the per-cell refresh hot path (root
Priority A).

**One authored hue set serves both themes.** The value colors in
`config/config.json` are hues only; each theme re-shades them via
`shade_for_theme()` rather than the config carrying a second, hand-maintained
light-mode table (root Rule #19).

**Temperature colors are NOT in config.** `config/config.json`'s
`temp_colors` section now carries only `warning_threshold` and
`critical_threshold`; the colors themselves come from the palette so they
follow the theme.

**Legacy shape guard on load.** `_load_config()` and `update_value_thresholds()`
discard `color_thresholds` from `last_setup.json` if it isn't a `dict` —
pre-2.0 versions stored it as a flat list. The same applies to `hue_params`,
which pre-2.2 versions stored as ONE flat `{saturation, lightness}` pair
rather than a per-theme mapping. Both are treated as stale hand-edited/legacy
data to fall back from, not a fatal error.

**Config errors fall back to defaults, not a crash.** An unreadable or
invalid `config/config.json` is reported to stderr and `_DEFAULT_VALUE_RANGES`
is used instead — documented fallback behavior per [Persistence](persistence.md)'s
corruption-recovery pattern.
