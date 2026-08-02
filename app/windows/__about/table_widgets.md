# Table Widgets

**Script:** [Table Widgets (script)](../table_widgets.py)

## Purpose

Three small overrides of Qt behavior that the process tables and the
current/history splitter depend on. They are classes rather than settings
because each redefines a paint or an input gesture Qt gives no hook for:
painting one specific row differently under a stylesheet, redefining what
"fit to contents" means for a double-clicked column, and resetting a splitter
to an equal split.

## Connections

### Uses

- [Theme](../../__about/theme.md) — `ThemeScope`, read by `TotalRowDelegate` at paint time

### Used by

- [Table Factory](table_factory.md) — `create_table()` installs `ContentWidthHeader` as the table's header and `TotalRowDelegate` as its item delegate
- [Base Window](base_window.md) — `_setup_ui()` builds the current/history splitter as a `DoubleClickSplitter`; `_make_total_item()` tags Σ-row items with `TotalRowDelegate.ROLE`

## Classes

### TotalRowDelegate (QStyledItemDelegate)
Paints the Σ total row with a distinct background. QSS-styled
`QTableWidget`s ignore `QTableWidgetItem.setBackground()`, so this delegate
bypasses the style engine and paints the background, text, font and alignment
directly for any item flagged with `TotalRowDelegate.ROLE`. Colors are read
from the owning window's `ThemeScope` at PAINT time, so a theme flip needs no
delegate rebuild, and a table in one window keeps painting that window's
theme while another window flips.

### ContentWidthHeader (QHeaderView)
Redefines ONE gesture: double-clicking a column's resize handle fits that
column to its ROW VALUES, never to its title (owner 2026-07-26). Qt's own
auto-fit resizes to `sectionSizeHint()` — the larger of the column contents
and the header label — which in a gadget with short numeric columns
("Parallel", "Threads") leaves the column much wider than the data needs.
`_handle_at()` mirrors Qt's own private hit test (the grip on a section's
left edge resizes the PREVIOUS section, the grip on its right edge resizes
itself); everything that is not a handle on an `Interactive` section falls
through to Qt unchanged.

### DoubleClickSplitterHandle (QSplitterHandle) / DoubleClickSplitter (QSplitter)
A splitter whose handle resets to an equal 50/50 split on double-click.
`DoubleClickSplitter.createHandle()` is the only override — it swaps in the
custom handle class.
