# Theme Transition

**Script:** [Theme Transition (script)](transition.py)

---

## Purpose

Hides the theme repaint behind a snapshot cover, so a Day/Night flip reads as
one deliberate change instead of a cascade.

A live flip cannot repaint everything in one atomic step: window chrome,
table stylesheets and the per-cell process colors land across several paint
passes. The owner saw exactly that — a **partially converted window**, light
chrome behind dark-theme process names.

Two fixes, both needed:

1. **The cause** — table cell colors are per-item brushes, not stylesheet
   properties, so restyling cannot reach them; they used to be corrected only
   by the next collector tick. [Main Window](main_window.md) now re-renders
   its last tick inside `_apply_theme()`, so every color is right immediately.
2. **The polish** — this module. Even an instant flip repaints visibly; the
   cover makes it a fade with the incoming theme's sun or moon on it.

The mechanism is the one PromptPainter uses (root Rule #5 — reuse the shape
that already works), ported to Qt.

---

## Connections

### Uses

- [Icons](icons.md) — `art()` for the big sun/moon cover icon
- [Styles](styles.md) — `Transition` timing and sizing constants
- [Theme](theme.md) — `theme_manager().set_theme()` — the flip itself

### Used by

- [Day/Night Switch](theme_switch.md) — a click calls `flip_theme()`

---

## Functions

| Function | Description |
|----------|-------------|
| `flip_theme()` | Flip Dark ↔ Light behind a cover on EVERY visible window. Returns the new theme name. |

### The transition

```
FUNCTION flip_theme():
    next = the theme we are switching TO
    icon = SUN if next is light, else MOON

    FOR EACH visible top-level window:
        cover = a frozen snapshot of that window, with `icon` drawn centred
        show the cover on top of it

    process pending events        # FORCE the covers actually painted first
    switch the active theme        # the whole cascade happens hidden
    process pending events         # let the restyle settle, still hidden
    fade every cover's opacity 1 -> 0, then destroy it
```

The ORDER is what removes the visible jump: the covers must be painted
**before** anything under them changes, and the flip must settle **before**
the fade starts. Otherwise the cascade shows through.

Every visible window is covered, not just the one that was clicked — the
three gadgets and any open dialog flip together, so one uncovered window
would show the very cascade the cover exists to hide.

---

## Classes

### _Cover

A borderless, always-on-top, click-through widget holding one window's
snapshot plus the centred icon. It is `WA_ShowWithoutActivating` (never
steals focus) and `WA_DeleteOnClose` (the fade's `finished` signal closes it).

`fade_out()` animates `windowOpacity` 1 → 0 on an **ease-out** curve, so the
stale snapshot clears quickly and then settles — the new theme is readable
well before the animation ends.

### Sizing

The cover icon is `Transition.ICON_FRAC` (0.30) of the window's SHORTER side,
clamped between `ICON_MIN` (64 px) and `ICON_MAX` (320 px) — a short gadget
window still gets a readable sun, and a very tall one does not get a giant.

---

## Design Decisions

**The cover is a nicety, never a gate.** If a cover cannot be built the
failure is printed and the flip happens anyway (root Rule #1's
documented-fallback case). The cover must never be the reason the theme
toggle stops working.

**`processEvents()` rather than a timer chain.** The flip has to be
synchronous — the app must be coherent the moment `flip_theme()` returns, so
the switch's knob animation and the cover fade both start from a settled
state. Two explicit event-loop pumps do that without spreading the flip
across callbacks.

**The animation object is held on the cover.** A `QPropertyAnimation` in a
local variable is garbage-collected the instant the function returns, and the
fade silently never runs.
