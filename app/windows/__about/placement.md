# Placement

**Script:** [Placement (script)](../placement.py) ·
**Flow:** [diagram](../__flow/placement.md)

## Purpose

The single authority on where a gadget window may sit. It is the ONE module
in the whole app that reasons in FRAME coordinates rather than CLIENT
coordinates, and that distinction is the whole bug it exists to prevent
(owner 2026-07-26) — see the [flow doc](../__flow/placement.md) for the full
clamp algorithm. It runs on every `showEvent()` (screens can change while a
window sits hidden in the tray) and is called directly by the Window
Manager's window cascading and its "Reset window positions" action.

## Connections

### Uses

- [Styles](../../__about/styles.md) — `Dimensions.WINDOW_MIN_WIDTH`/`WINDOW_MIN_HEIGHT` (size floor), `Dimensions.MIN_GRAB_WIDTH` (horizontal clamp)

### Used by

- [Base Window](base_window.md) — `showEvent()` calls `place_on_screen()` on every show
- [Window Manager](../../__about/window_manager.md) — `_create()` and `reset_positions()` call `target_screen()`/`place_on_screen()` directly to cascade new windows and to recover stranded ones

## Functions

### `target_screen(window) -> QScreen`
The screen a window belongs to, even when it sits fully off-screen.
`QApplication.screenAt()` returns `None` for a point no screen contains, so it
cannot be the only answer; falls back to the screen with the largest overlap
with the window's frame, then `window.screen()`, then the primary screen.

### `place_on_screen(window) -> None`
Clamps a window so a grabbable strip of its title bar stays reachable. Resizes
to fit the target screen first, recentres a fully stranded window, then clamps
vertically (caption clears the top edge and stays above the taskbar) and
horizontally (keeps at least `Dimensions.MIN_GRAB_WIDTH` on screen). A window
merely hanging off an edge is left exactly where it was put — only an
UNREACHABLE caption is corrected. Full algorithm: [flow](../__flow/placement.md).
