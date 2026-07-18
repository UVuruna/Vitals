# Color Management

**Script:** [color_management.py (script)](color_management.py)

---

## Purpose

Handles process-coloring logic only. The app chrome/dark-theme palette
(`Colors`) lives in [Styles](styles.md), not here — this module owns:

- **Company-based coloring** — companies with more than one active process
  name get an individual hue (`360°/N` evenly spaced); companies with
  exactly one process name share a single "Other" color; processes with no
  company info get a fixed near-white color.
- **Value-based coloring** — eight independent threshold sets (CPU, CPU-Σ-total,
  Memory, Memory-Commit, Memory-Σ-total, Memory-Commit-Σ-total, Network
  download, Network upload) each map 0–100% to one of 5 colors.

Default thresholds are read from `config/config.json`; user overrides
persist to `config/last_setup.json` via [Persistence](persistence.md).

---

## Connections

### Uses

- `config/config.json` — `value_colors.ranges` default thresholds
- [Persistence](persistence.md) — `load_last_setup()`/`save_last_setup()` for hue params and saved thresholds
- `psutil` — resolves an exe path per process for company lookup
- Windows `version.dll` (via `ctypes`) — reads `CompanyName` from PE version info

### Used by

- [Main Window](main_window.md) — `get_process_color()`, `get_value_color()`, `get_company_name()`, `lookup_company()`, `refresh_active_counts()` (called every tick by [Monitor](monitor.md)'s collector loop)
- [Settings Dialog](settings_dialog.md) — `get_value_ranges()`, `update_value_thresholds()`, `get_legend()`, `get_hue_params()`, `update_hue_params()`, `get_singleton_companies()`, `get_company_processes()`

---

## Classes

### ProcessColorManager

Thread-safe singleton (`QMutex`-guarded `__new__`), accessed as
`ProcessColorManager()` from any thread.

#### Company-Based Coloring

```
hue = multi_company_index / (multi_company_count + 1) * 360°
```

The `+1` reserves the last hue slot for the shared "Other" color (singleton
companies). Hue assignments are never revoked once granted
(`_company_multi_idx`), so colors stay stable even if a company temporarily
drops to a single active process. Saturation/lightness default to `0.84`/`0.84`
(vivid pastel, readable on the dark background) and are user-tunable via the
Company Legend dialog's sliders.

#### Methods

| Method | Thread | Description |
|--------|--------|--------------|
| `lookup_company(name, pid)` | Background (collector) | Registers a process name and resolves its company via PE version info. Fast no-op for already-cached names. |
| `refresh_active_counts(active_names)` | Background (collector) | Recomputes per-company counts from the current tick's active names every cycle. |
| `get_process_color(name)` | Main | `QColor` for a process name, or `None` if not yet looked up. |
| `get_company_name(name)` | Main | Resolved company name, or `None`. |
| `get_value_color(pct, mode)` | Any | `QColor` for a 0–100 usage percentage under the given mode's thresholds. |
| `get_value_ranges(mode)` | Main | `list[tuple[float, QColor]]` for `ColorScaleWidget` display. |
| `update_value_thresholds(thresholds, mode)` | Main | Updates the 4 threshold values in-memory and persists them. |
| `get_hue_params()` / `update_hue_params(sat, light)` | Main | Read/write the company-hue saturation and lightness. |
| `get_legend()` | Main | `list[tuple[str, QColor, int]]` — `(label, color, process_count)` sorted by count descending; includes `"Other"` (singletons) and `"Unknown"` (no company info). |
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

**Legacy shape guard on load.** `_load_config()` and `update_value_thresholds()`
discard `color_thresholds` from `last_setup.json` if it isn't a `dict` —
pre-2.0 versions stored it as a flat list. This is treated as stale
hand-edited/legacy data to fall back from, not a fatal error.

**Config errors fall back to defaults, not a crash.** An unreadable or
invalid `config/config.json` is reported to stderr and `_DEFAULT_VALUE_RANGES`
is used instead — documented fallback behavior per [Persistence](persistence.md)'s
corruption-recovery pattern.
