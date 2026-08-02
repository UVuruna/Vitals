# Theme Transition

**Script:** [Theme Transition (script)](../transition.py) ·
**Flow:** [diagram](../__flow/transition.md)

## Purpose

Hides the theme repaint behind a snapshot cover, so a Day/Night flip reads
as one deliberate change instead of a visible cascade. A live flip cannot
repaint everything in one atomic step — window chrome, table stylesheets and
the per-cell process colors land across several paint passes — so for a
moment the window would otherwise be visibly half-converted.

The mechanism grabs the affected window(s) into a borderless, always-on-top
cover, composites the NEXT theme's sun or moon in the middle, forces the
cover painted, flips the theme hidden behind it, lets the restyle cascade
settle, then fades the cover out. It is the shape PromptPainter already uses
for the same problem (root Rule #5 — reuse, never re-author), ported to Qt.
The cover is a pure visual nicety: any failure to build one is reported and
the flip still happens instantly (root Rule #1's documented-fallback case).

## Connections

### Uses
- [Icons](icons.md) — `art()` for the big sun/moon cover icon
- [Styles](styles.md) — `Transition` timing and sizing constants
- [Theme](theme.md) — `LIGHT`, `ThemeScope`, `app_theme()`, `set_theme_everywhere()` — the flips themselves

### Used by
- [Windows (subfolder)](../windows/___windows.md) — a monitor window's header switch calls `flip_window_theme(scope, window)`
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — the setup screen's global switch calls `flip_app_theme()`

## Functions

| Function | Description |
|----------|--------------|
| `flip_window_theme(scope, window)` | Flip ONE window's theme behind a cover on that window alone. Returns the new theme name. |
| `flip_app_theme()` | Flip the app theme and force it on every monitor window, covering every visible one. Returns the new theme name. |

Coverage is exactly the flip's reach: a per-window flip covers one window —
the other two gadgets are not repainting and must not be frozen for a fade
they have no part in. A global flip changes everything, so it covers
everything.

## Classes

### _Cover
A borderless, always-on-top, click-through `QWidget` holding one window's
snapshot plus the centred next-theme icon. `WA_ShowWithoutActivating` (never
steals focus), `WA_DeleteOnClose` (the fade's `finished` signal closes it).
`fade_out()` animates `windowOpacity` 1 -> 0 on an ease-out curve — the
stale snapshot clears quickly, then settles.

The cover icon is `Transition.ICON_FRAC` (0.30) of the window's SHORTER
side, clamped between `ICON_MIN` (64px) and `ICON_MAX` (320px) — a short
gadget still gets a readable sun, a very tall one does not get a giant.

## Design Decisions

- **The cover is a nicety, never a gate.** A failed cover build is printed
  to stderr and the flip proceeds anyway — the cover must never be the
  reason the theme toggle stops working.
- **`processEvents()` rather than a timer chain.** The flip must be
  synchronous — coherent the moment it returns — so two explicit event-loop
  pumps (cover painted, then cascade settled) do that without spreading the
  flip across callbacks.
- **Two named functions, not one with a `global` flag.** The two flips
  differ in both what changes and what is covered, and those two must
  always agree; naming each combination makes a mismatch (flip one window,
  cover all three) impossible to write.
- **The animation object is held on the cover instance**, not a local
  variable — a `QPropertyAnimation` in a local is garbage-collected the
  instant the function returns and the fade would silently never run.
