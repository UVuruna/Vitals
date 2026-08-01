"""Window placement — the single authority on where a gadget may sit.

This is the ONE module that reasons in FRAME coordinates rather than CLIENT
coordinates, and that distinction is the whole bug it exists to prevent. It is
called on every show and by the tray's "Reset window positions".
"""

from PySide6.QtCore import QMargins
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QWidget

from ..styles import Dimensions


# ══════════════════════════════ SCREEN LOOKUP ══════════════════════════════

def target_screen(window: QWidget) -> QScreen:
    """The screen a window belongs to, even when it sits fully off-screen.

    `QApplication.screenAt()` returns None for a point no screen contains, so
    it cannot be the only answer — a stranded window must still be rescued
    onto something.
    """
    frame = window.frameGeometry()
    screen = QApplication.screenAt(frame.center())
    if screen is not None:
        return screen
    best, best_area = None, 0
    for candidate in QApplication.screens():
        overlap = candidate.availableGeometry().intersected(frame)
        area = overlap.width() * overlap.height()
        if area > best_area:
            best, best_area = candidate, area
    return best or window.screen() or QApplication.primaryScreen()


# ═════════════════════════════ THE CLAMP ═════════════════════════════

def place_on_screen(window: QWidget) -> None:
    """Clamp a window so a grabbable strip of its TITLE BAR stays reachable.

    This is the ONLY authority on window placement, and it is the one place
    that thinks in FRAME coordinates. That distinction is the whole bug it
    exists to prevent (owner 2026-07-26):

      - `geometry()` / `setGeometry()` address the CLIENT rect — the caption
        and borders are NOT in it.
      - `pos()` / `move()` / `frameGeometry()` address the FRAME rect, which
        on Windows starts one caption height ABOVE the client.

    So `setGeometry(0, 0, w, h)` — a perfectly ordinary saved position —
    leaves `frameGeometry() == (0, -30, w, h + 30)`: the entire title bar, its
    drag strip and its close button sit above the screen. The old guard asked
    "does the frame touch a screen?", which is true here, so it did nothing
    and the window was stranded: `Qt.Tool` means no taskbar button and no
    Alt-Tab entry, and Windows only rescues a window the user can focus.

    A window merely hanging off an edge is left exactly where it was put — a
    gadget deliberately parked half off-screen is a valid layout. Only an
    unreachable caption is corrected.
    """
    available = target_screen(window).availableGeometry()
    handle = window.windowHandle()
    margins = handle.frameMargins() if handle is not None else QMargins()

    # Size first, so the position clamp sees the frame it will actually move.
    # resize() is client space, matching what the saved width/height mean.
    max_width = available.width() - margins.left() - margins.right()
    max_height = available.height() - margins.top() - margins.bottom()
    width = max(Dimensions.WINDOW_MIN_WIDTH, min(window.width(), max_width))
    height = max(Dimensions.WINDOW_MIN_HEIGHT, min(window.height(), max_height))
    if (width, height) != (window.width(), window.height()):
        window.resize(width, height)

    frame = window.frameGeometry()
    # frameMargins() is empty until the native window exists; fall back to the
    # strut the frame itself reveals so a pre-show call still clamps sanely.
    caption = margins.top() or max(0, frame.height() - window.height())

    # Fully stranded — no screen shows a single pixel of it, so there is no
    # position worth preserving (a monitor was unplugged, or the saved layout
    # came from a machine with a different desktop). Centre it and let the
    # clamp below finish the job.
    if not any(
        screen.availableGeometry().intersects(frame)
        for screen in QApplication.screens()
    ):
        window.move(
            available.x() + (available.width() - frame.width()) // 2,
            available.y() + (available.height() - frame.height()) // 2,
        )
        frame = window.frameGeometry()

    # The caption must clear the top edge, and stay above the taskbar.
    top = min(
        max(frame.y(), available.top()),
        max(available.top(), available.bottom() - caption + 1),
    )
    # Horizontally, keep a real strip of the window on the screen either way.
    grab = min(Dimensions.MIN_GRAB_WIDTH, frame.width())
    left = min(
        max(frame.x(), available.left() - frame.width() + grab),
        available.right() - grab + 1,
    )

    if (left, top) != (frame.x(), frame.y()):
        window.move(left, top)
