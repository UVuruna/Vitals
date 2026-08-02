# Layout Store

**Script:** [Layout Store (script)](../layout_store.py)

## Purpose

Reads and writes one window's layout slot in `last_setup.json`. Geometry,
splitter sizes, the bottom-page choice, the font size and every column width
live under `windows.<key>` — the SAME slot that also holds the window's
remembered THEME (owned by its `ThemeScope`), which is why the entry is
always UPDATED and never replaced wholesale.

The saved x/y/width/height are CLIENT coordinates. Judging whether such a
position is still usable is deliberately NOT done here — [Placement](placement.md)
owns that judgment, and it is the only code that can, because the answer
lives in FRAME coordinates this module never looks at.

## Connections

### Uses

- [Persistence](../../__about/persistence.md) — `load_last_setup()`, `save_last_setup()`

### Used by

- [Base Window](base_window.md) — `_save_window_layout()`/`_restore_window_layout()` call `save(self)`/`restore(self)` directly; `_rebuild_tables()` calls `apply_col_widths()` to reapply saved widths after a row-count change

## Functions

### `apply_col_widths(table, widths) -> None`
Applies saved widths to a table's interactive columns (column 2 onward — the
row-number and Process columns are never saved).

### `save(window) -> None`
Writes geometry, font size, splitter sizes, the bottom-page choice and every
table's column widths into the window's slot. A window whose layout was
never restored (`window._layout_restored` is `False`) writes NOTHING: until
the first show it still carries Qt's default `640x480` at the origin, and
persisting that would both overwrite a real saved layout and store a
position whose caption lands above the screen.

### `restore(window) -> None`
Reads the window's slot and applies geometry via `setGeometry()` (CLIENT
coordinates in, CLIENT coordinates out — no conversion needed), font size,
splitter sizes, bottom-page choice and column widths. Missing or malformed
fields are simply skipped, never raised.
