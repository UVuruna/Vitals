# Styles

**Script:** [styles.py (script)](styles.py)

---

## Purpose

Config home for every tunable value that is **not** a color: dimensions,
switch geometry, fonts, defaults, unit tables and the shared formatters.

Colors are **not** here. They must flip at runtime between the dark and light
palettes, so they live in [Theme](theme.md) and are read through `theme()` at
restyle time. The one thing this module still builds from a palette is
`context_menu_style()` — a function, not a constant, precisely so it cannot
freeze whichever theme was active at import.

---

## Connections

### Uses

- [Theme](theme.md) — `theme()`, for `context_menu_style()` only

### Used by

- [Main Window](main_window.md) — `Defaults`, `Dimensions`, `Fonts`, `FontScale`, `context_menu_style`, `format_speed`, `format_bytes_total`
- [Settings Dialog](settings_dialog.md) — `Defaults`, `FontScale`, `MEMORY_UNITS`, `NETWORK_UNITS`
- [Day/Night Switch](theme_switch.md) — `Switch` geometry
- [Monitor](monitor.md) — `Defaults`, `MEMORY_UNITS`, `format_pct`, `format_speed`, `get_process_display_name`
- [Tray Controller](tray.md) — `context_menu_style`
- `process_actions.py` — `get_process_display_name`
- `process_dialog.py` — `Fonts`

---

## Constants

### Dimensions

`WINDOW_WIDTH` (500), `WINDOW_MIN_HEIGHT` (400), `MARGIN` (10), `SPACING` (8),
`TABLE_ROW_HEIGHT` (28), `HEADER_HEIGHT` (50), `SETTINGS_WIDTH` (450),
`SETTINGS_HEIGHT` (400), `MENU_LINE_CHARS` (34 — popup menus cannot wrap, so
a long company name is split into rows of this many characters).

### Switch

Day/Night switch geometry, all derived from one height: `HEIGHT` (22),
`ASPECT` (2.1539), `KNOB_FACTOR` (0.85), `PAD` (4), `ANIM_MS` (420),
`HOVER_SCALE` (1.05), `SUN_CELL_SCALE` (1.7). See
[Day/Night Switch](theme_switch.md).

### Fonts / FontScale

`Fonts` holds the base family (`"Segoe UI"`) and three fixed sizes used by
plain dialogs (`SIZE_HEADER`/`SIZE_BODY`/`SIZE_SMALL`).

`FontScale` is the proportional system used by the monitor windows — every
size is an **offset from the user's chosen base size** (like `em`/`rem`):
`TITLE` (+5), `SECTION` (+2), `SUBTITLE` (+1), `BODY` (0), `SMALL` (-1),
`TINY` (-2), clamped to `MIN_SIZE` (6pt). `FontScale.size(base, offset)`
computes the final pt size; `FontScale.row_height(base)` scales table row
height proportionally (`28 * base / 11`, so the default 11pt base reproduces
the original hardcoded 28px rows).

### Defaults

`CURRENT_ROWS` (7), `HISTORY_ROWS` (4), `MAX_ROWS` (30), `REFRESH_RATE_MS`
(1000), `RETENTION_MINUTES` (120), `MEMORY_UNIT` ("MB"), `NETWORK_UNIT`
("MB/s"), `FONT_SIZE` (11), `NETWORK_MAX_DOWNLOAD_MBPS` / `NETWORK_MAX_UPLOAD_MBPS`
(0 = auto-detect from link speed), `NETWORK_SORT_MODE` ("total"),
`COLLECTOR_SLEEP_CHUNK_MS` (100 — see [Monitor](monitor.md)'s chunked-sleep
design decision), `ROLLING_BUCKET_SECONDS` (60 — see [Monitor](monitor.md)'s
`RollingWindow` bucketed-expiry design decision).

### MEMORY_UNITS / NETWORK_UNITS

Byte-divisor lookup tables: `{"KB": 1024, "MB": 1024**2, "GB": 1024**3}` and
`{"KB/s": 1024, "MB/s": 1024**2}`.

### PROCESS_ALIASES

Prefix-match table used by `get_process_display_name()` to group related
processes under one display name (e.g. `"Code"`/`"code"` →
`"Visual Studio Code"`, `"chrome"` → `"Chrome"`, `"msedge"` → `"Microsoft Edge"`).

### context_menu_style()

Shared QSS **function** for every right-click/tray context menu, built from
the ACTIVE palette so menus always match the current theme. It is a function
rather than a constant because a module-level f-string would freeze the
palette that happened to be active at import time.

---

## Functions

| Function | Description |
|----------|-------------|
| `format_speed(bytes_per_sec, unit)` | Formats a bytes/sec value in `"KB/s"` or `"MB/s"`, adaptive decimals for MB/s (`≥100` → 0 decimals, else 2). |
| `format_bytes_total(total_bytes, unit)` | Formats a cumulative byte count, auto-picking GB (≥1 GB) or MB. |
| `format_pct(value)` | Adaptive-precision percentage: `≥100` → integer, `≥10` → 1 decimal, `<10` → 2 decimals. Keeps output at ≤3 significant digits before `%`. |
| `get_process_display_name(name)` | `@lru_cache`d: strips `.exe`, applies `PROCESS_ALIASES` prefix match. |
