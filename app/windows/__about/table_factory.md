# Table Factory

**Script:** [Table Factory (script)](../table_factory.py)

## Purpose

All three tables in a monitor window (current, peak/history, rolling) are the
same table with a different column set, so ONE factory builds them:
`create_table()` decides the columns from the mode, sets the resize modes,
applies the window's palette and font, and installs the Σ-row delegate and
the values-not-title auto-fit header. The QSS builders (`style_table()`,
`header_css()`) are kept separate from `create_table()` on purpose — a theme
flip must be able to restyle a LIVE table without rebuilding it.

## Connections

### Uses

- [Table Widgets](table_widgets.md) — `ContentWidthHeader`, `TotalRowDelegate`
- [Theme](../../__about/theme.md) — `Palette`, `ThemeScope`
- [Styles](../../__about/styles.md) — `FontScale`, `Fonts`, `scaled_font`

### Used by

- [Base Window](base_window.md) — `_create_table()` calls `create_table()`; `_apply_theme()`/`_apply_fonts()` call `style_table()`/`header_css()` to restyle live tables

## Functions

### `header_css(palette, font_base) -> str`
QSS for a table's horizontal header, in a window's theme and font.

### `style_table(table, palette, font_base) -> None`
Applies a window's palette as QSS to one process table. All three sections
share one surface color (`palette.SECTION_BG`) — per-section tints used to
make the same data look like three unrelated kinds of table (owner
2026-07-24). Also re-applies `header_css()` directly to the header widget: a
per-widget stylesheet wins over the parent table's, so the header needs its
own refresh or a theme flip leaves the column headers in the old palette.

### `create_table(rows, scope, font_base, mode_cols, has_time, has_total_row, has_uptime) -> QTableWidget`
Builds one table. `mode_cols` selects the extra columns (`"cpu"` → Parallel +
Threads, `"mem"` → Commit, `"net"` → replaces Usage with Download and adds
Upload, `"none"` → nothing extra); `has_time`/`has_uptime` add the History and
Rolling Average columns; `has_total_row` reserves one extra row for the Σ
totals. Installs `ContentWidthHeader` as the header BEFORE any header
configuration (double-click auto-fit must already be the header's own class),
sets per-column resize modes (row-number and Process are automatic, all data
columns are `Interactive`), applies `style_table()`, and installs
`TotalRowDelegate(table, scope)` as the item delegate.
