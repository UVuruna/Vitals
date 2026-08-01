"""Reading and writing one window's layout slot in last_setup.json.

Geometry, splitter sizes, the bottom-page choice, the font size and every
column width live under `windows.<key>` — the same slot that holds the
window's remembered THEME, which is why the entry is always UPDATED and never
replaced.

The saved x/y/width/height are CLIENT coordinates. Judging whether such a
position is usable is deliberately NOT done here: `placement.py` owns that,
and it is the only code that can, because the answer lives in frame
coordinates this module never sees.
"""

from PySide6.QtWidgets import QTableWidget

from ..persistence import load_last_setup, save_last_setup


# ══════════════════════════════ COLUMN WIDTHS ══════════════════════════════

def apply_col_widths(table: QTableWidget, widths: list[int]) -> None:
    """Apply saved widths to interactive columns (col 2 onward)."""
    for i, w in enumerate(widths):
        col = i + 2
        if col < table.columnCount():
            table.setColumnWidth(col, w)


# ═══════════════════════════════ SAVE / RESTORE ═══════════════════════════════

def save(window) -> None:
    """Save window geometry, splitter sizes, and column widths to last_setup.json.

    The entry is UPDATED, never replaced: the same slot also holds this
    window's remembered theme, which is owned by its ThemeScope and would
    be wiped by a wholesale assignment.

    A window whose layout was never restored writes NOTHING. Until the
    first show it still carries Qt's default 640x480 at the origin, and
    persisting that would both overwrite a real saved layout and store the
    position whose caption lands above the screen.
    """
    if not window._layout_restored:
        return
    data = load_last_setup()
    entry = data.setdefault("windows", {}).setdefault(window._get_window_key(), {})
    geo = window.geometry()
    entry.update({
        "x": geo.x(), "y": geo.y(),
        "width": geo.width(), "height": geo.height(),
        "font_size": window._font_base,
        "splitter": window.splitter.sizes(),
        "bottom_page": window._bottom_page,
        "current_cols": [
            window.current_table.columnWidth(c)
            for c in range(2, window.current_table.columnCount())
        ],
        "history_cols": [
            window.history_table.columnWidth(c)
            for c in range(2, window.history_table.columnCount())
        ],
        "rolling_cols": [
            window.rolling_table.columnWidth(c)
            for c in range(2, window.rolling_table.columnCount())
        ],
    })
    save_last_setup(data)


def restore(window) -> None:
    """Restore window geometry, splitter sizes, and column widths from last_setup.json.

    The saved x/y/width/height are CLIENT coordinates (what `save()` wrote
    from `geometry()`), so they go back through `setGeometry()` unchanged —
    the units match and nothing drifts. Judging whether that position is
    usable is NOT done here: `place_on_screen()` owns it, and it is the only
    code that can, because the answer lives in frame coordinates this
    function never sees.
    """
    data = load_last_setup()
    layout = data.get("windows", {}).get(window._get_window_key())
    if not layout:
        return
    x, y, w, h = layout.get("x"), layout.get("y"), layout.get("width"), layout.get("height")
    if all(v is not None for v in [x, y, w, h]):
        window.setGeometry(x, y, w, h)
    saved_font = layout.get("font_size")
    if saved_font is not None and saved_font != window._font_base:
        window._font_base = int(saved_font)
        window._apply_fonts()
    splitter_sizes = layout.get("splitter")
    if isinstance(splitter_sizes, list) and len(splitter_sizes) == 2:
        window.splitter.setSizes(splitter_sizes)
    bottom_page = layout.get("bottom_page", 0)
    if bottom_page in (0, 1):
        window._show_bottom_page(bottom_page)
    current_cols = layout.get("current_cols")
    if isinstance(current_cols, list):
        window._saved_col_widths_current = current_cols
        apply_col_widths(window.current_table, current_cols)
    history_cols = layout.get("history_cols")
    if isinstance(history_cols, list):
        window._saved_col_widths_history = history_cols
        apply_col_widths(window.history_table, history_cols)
    rolling_cols = layout.get("rolling_cols")
    if isinstance(rolling_cols, list):
        window._saved_col_widths_rolling = rolling_cols
        apply_col_widths(window.rolling_table, rolling_cols)
