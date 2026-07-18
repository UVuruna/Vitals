# Styles

**Script:** [styles.py (script)](styles.py)

---

## Purpose

Single source of truth for the application's dark-theme palette, dimensions,
fonts, and every tunable default/threshold value used across the UI and
collector. `color_management.py` explicitly does **not** hold palette
constants — only value-threshold gradient data and process-coloring logic;
`Colors` here is the one place window chrome, settings dialogs, and the
shared context menu pull hex values from.

---

## Connections

### Uses

- None — standalone constants and pure functions (no imports from other `app` modules)

### Used by

- [Main Window](main_window.md) — `Colors`, `Defaults`, `Fonts`, `FontScale`, `CONTEXT_MENU_STYLE`, `format_speed`, `format_bytes_total`
- [Settings Dialog](settings_dialog.md) — `Colors`, `Defaults`, `FontScale`, `MEMORY_UNITS`, `NETWORK_UNITS`
- [Monitor](monitor.md) — `Defaults`, `MEMORY_UNITS`, `format_pct`, `format_speed`, `get_process_display_name`
- [Tray Controller](tray.md) — `CONTEXT_MENU_STYLE`
- `process_actions.py` — `get_process_display_name`
- `process_dialog.py` — `Fonts`

---

## Constants

### Colors (dark theme — single palette source)

| Attribute | Value | Usage |
|-----------|-------|-------|
| `BACKGROUND` | `#1e1e2e` | Window background |
| `CARD` | `#2a2a3e` | Card/panel background |
| `HEADER` | `#3a3a4e` | Header row / table header background |
| `BORDER` | `#4a4a5e` | Input borders |
| `ACCENT` / `ACCENT_HOVER` | `#e94560` / `#ff6b6b` | Buttons, highlights |
| `TEXT` / `TEXT_MUTED` / `TEXT_DIM` / `TEXT_FAINT` / `TEXT_DISABLED` | `#ffffff` … `#555555` | Text hierarchy, brightest to dimmest |
| `CURRENT_BG` / `HISTORY_BG` / `ROLLING_BG` | `#2d2d42` / `#2a3a3e` / `#2a382e` | Per-section table backgrounds |
| `TEMP_WARNING` / `TEMP_CRITICAL` | `#ffa500` / `#ff4444` | HWiNFO temperature thresholds |

### Dimensions

`WINDOW_WIDTH` (500), `WINDOW_MIN_HEIGHT` (400), `MARGIN` (10), `SPACING` (8),
`TABLE_ROW_HEIGHT` (28), `HEADER_HEIGHT` (50), `SETTINGS_WIDTH` (450),
`SETTINGS_HEIGHT` (400).

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

### CONTEXT_MENU_STYLE

Shared QSS string for every right-click/tray context menu, built from
`Colors` so menus always match the dark theme.

---

## Functions

| Function | Description |
|----------|-------------|
| `format_speed(bytes_per_sec, unit)` | Formats a bytes/sec value in `"KB/s"` or `"MB/s"`, adaptive decimals for MB/s (`≥100` → 0 decimals, else 2). |
| `format_bytes_total(total_bytes, unit)` | Formats a cumulative byte count, auto-picking GB (≥1 GB) or MB. |
| `format_pct(value)` | Adaptive-precision percentage: `≥100` → integer, `≥10` → 1 decimal, `<10` → 2 decimals. Keeps output at ≤3 significant digits before `%`. |
| `get_process_display_name(name)` | `@lru_cache`d: strips `.exe`, applies `PROCESS_ALIASES` prefix match. |
