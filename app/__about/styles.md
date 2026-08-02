# Styles

**Script:** [Styles (script)](../styles.py) ·
**Flow:** [diagram](../__flow/styles.md)

## Purpose

Config home for every tunable value that is **not** a color: dimensions,
switch geometry, transition timing, fonts, default settings, unit tables,
process-name aliases, and the shared QSS/formatter functions (root Rule #4).
Colors are deliberately absent — they must flip at runtime between the dark
and light palettes and each window may be on a different one, so they live
in [Theme](theme.md) and are always passed in as a `Palette` at restyle
time. The one function this module still builds from a palette,
`context_menu_style()`, takes it as a parameter for exactly that reason —
never as a frozen module-level string.

## Connections

### Uses
- [Theme](theme.md) — `Palette`, as the parameter type for `context_menu_style(palette)`

### Used by
- [Process Actions](process_actions.md) — `get_process_display_name()`
- [Settings](settings.md) — `Defaults`, the field defaults for every settings dataclass
- [Day/Night Switch](theme_switch.md) — `Switch` geometry
- [Theme Transition (flow)](../__flow/transition.md) — `Transition` timing and sizing
- [Tray](tray.md) — `context_menu_style()` for the tray menu
- [Window Manager](window_manager.md) — `Dimensions.WINDOW_GAP`, the cascade spacing between newly created windows
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — `Defaults`, `Fonts`, `MEMORY_UNITS` across the setup screen and per-mode dialogs
- [Windows (subfolder)](../windows/___windows.md) — `Defaults`, `Dimensions`, `FontScale`, `scaled_font`, `context_menu_style`, `format_speed`, `format_bytes_total` across the window chrome, tables and process context menu
- [Collect (subfolder)](../collect/___collect.md) — `Defaults`, `MEMORY_UNITS`, `format_pct`, `format_speed`, `get_process_display_name` in the collector and per-mode stat readers

## Constants

### Dimensions
`WINDOW_WIDTH` (500), `WINDOW_MIN_WIDTH` (340), `WINDOW_MIN_HEIGHT` (400),
`WINDOW_GAP` (20 — cascade spacing), `MIN_GRAB_WIDTH` (200 — the minimum
title-bar width a placement must leave clickable), `MARGIN` (10), `SPACING`
(8), `TABLE_ROW_HEIGHT` (28), `HEADER_HEIGHT` (50), `SETTINGS_WIDTH` /
`SETTINGS_HEIGHT` (450 / 400), `MENU_LINE_CHARS` (34 — popup menus cannot
wrap, so a long company name is split into rows of this many characters).

### Transition
Theme-flip cover timing/sizing: `FADE_MS` (500), `ICON_FRAC` (0.30 of the
window's shorter side), `ICON_MIN` (64), `ICON_MAX` (320). See
[Theme Transition (flow)](../__flow/transition.md).

### Switch
Day/Night switch geometry, all derived from one height: `HEIGHT` (22),
`ASPECT` (2.1539), `KNOB_FACTOR` (0.85), `PAD` (4), `ANIM_MS` (420),
`HOVER_SCALE` (1.05), `SUN_CELL_SCALE` (1.7). See
[Day/Night Switch](theme_switch.md).

### Fonts / FontScale
`Fonts` holds the base family (`"Segoe UI"`) and three fixed sizes for plain
dialogs (`SIZE_HEADER`/`SIZE_BODY`/`SIZE_SMALL`).

`FontScale` is the proportional system the monitor windows use — every size
is an offset from the user's chosen base size (like `em`/`rem`): `TITLE`
(+5), `SECTION` (+2), `SUBTITLE` (+1), `BODY` (0), `SMALL` (-1), `TINY`
(-2), clamped to `MIN_SIZE` (6pt). `FontScale.size(base, offset)` computes
the final pt size; `FontScale.row_height(base)` scales table row height
proportionally (`28 * base / 11`).

`scaled_font(base, offset, bold=False)` turns `(base, offset)` into a
`QFont` in one place, so the window chrome, the table factory and the
status banner all scale together from the same rule.

### Defaults
`CURRENT_ROWS` (7), `HISTORY_ROWS` (4), `MAX_ROWS` (30), `REFRESH_RATE_MS`
(1000), `RETENTION_MINUTES` (120), `MEMORY_UNIT` ("MB"), `NETWORK_UNIT`
("MB/s"), `FONT_SIZE` (11), `CPU_THREADS` / `RAM_GB` (`None` — auto-detect),
`NETWORK_MAX_DOWNLOAD_MBPS` / `NETWORK_MAX_UPLOAD_MBPS` (0 = auto-detect
from link speed), `NETWORK_SORT_MODE` ("total"),
`COLLECTOR_SLEEP_CHUNK_MS` (100 — bounds how long `stop()` can take to
interrupt the collector even at slow refresh rates),
`ROLLING_BUCKET_SECONDS` (60 — rolling-average expiry bucket span, ~45x
less memory than per-tick storage at 120 min retention @ 1s refresh).

### MEMORY_UNITS / NETWORK_UNITS
Byte-divisor lookup tables: `{"KB": 1024, "MB": 1024**2, "GB": 1024**3}` and
`{"KB/s": 1024, "MB/s": 1024**2}`.

### PROCESS_ALIASES
Prefix-match table used by `get_process_display_name()` to group related
processes under one display name (e.g. `"Code"`/`"code"` ->
`"Visual Studio Code"`, `"msedge"` -> `"Microsoft Edge"`, `"nv"` ->
`"NVIDIA"`).

### context_menu_style(palette)
Shared QSS function for every right-click/tray context menu, built from the
CALLER's palette so the menu matches the theme of whichever window (or the
tray's app-wide scope) opened it.

## Functions

| Function | Description |
|----------|--------------|
| `format_speed(bytes_per_sec, unit)` | Formats a bytes/sec value in `"KB/s"` or `"MB/s"`; MB/s uses 0 decimals at >= 100, else 2. |
| `format_bytes_total(total_bytes, unit)` | Formats a cumulative byte count, auto-picking GB (>= 1 GB) or MB. |
| `format_pct(value)` | Adaptive-precision percentage: >= 100 -> integer, >= 10 -> 1 decimal, < 10 -> 2 decimals. |
| `get_process_display_name(name)` | `@lru_cache`d: strips `.exe`, applies `PROCESS_ALIASES` prefix match. |
| `scaled_font(base, offset, bold=False)` | Builds a `QFont` from a base size and a `FontScale` offset. |

## Design Decisions

- **Split by kind, not by module.** Colors flip at runtime and differ per
  window; everything else is a plain constant that never needs a `Palette`
  to resolve. Keeping the color-vs-not split at the file level (this module
  vs. [Theme](theme.md)) means "should this be hardcoded?" always has a
  one-question answer: is it a color?
- **`context_menu_style()` is a function, not a constant.** A module-level
  f-string would freeze whichever palette happened to be active at import —
  exactly the bug [Theme](theme.md) exists to prevent.
- **`scaled_font()` is the one rule, used everywhere a font is built.**
  Before the split each caller re-derived a `QFont` from `FontScale.size()`
  by hand; centralizing it means a font-size change moves the window chrome,
  the table factory and the status banner together.
