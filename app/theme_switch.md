# Day/Night Switch

**Script:** [Day/Night Switch (script)](theme_switch.py)

---

## Purpose

The Day/Night theme toggle in each window header — an image pill ported from
the owner's website switch, the same control PromptPainter uses.

- **OFF / left** — the MOON on a dark starfield track → dark theme
- **ON / right** — the SUN on a sky-and-clouds track → light theme

A click runs the flip it was built with; the knob then slides as an eased
flourish, and the track pill hard-swaps night ↔ day as the knob passes the
midpoint.

**The switch is deliberately dumb about reach.** It renders and animates one
[ThemeScope](theme.md) and delegates the actual flip to a callable. That is
what lets the identical widget be:

| Where | Scope | Flip | Reach |
|-------|-------|------|-------|
| A monitor window header | `window_theme(key)` | `flip_window_theme()` | that window only |
| The setup screen | `app_theme()` | `flip_app_theme()` | every window at once |

Each switch follows **its own** scope's `changed`, so a global flip slides
all four knobs while a window flip slides only that window's.

---

## Connections

### Uses

- [Icons](icons.md) — `art()` for the two track pills and the sun/moon knobs
- [Styles](styles.md) — `Switch` geometry constants
- [Theme](theme.md) — the `ThemeScope` it renders and whose `changed` it follows

### Used by

- [Main Window](main_window.md) — one per window header, under the pause/settings icons, wired to that window's flip
- [Settings Dialog](settings_dialog.md) — one on the setup screen beside the app name, wired to the global flip
- [Theme Transition](transition.md) — supplies both flip callables

---

## Classes

### DayNightSwitch

`QWidget` sized entirely from `Switch.HEIGHT`, so changing that one constant
rescales the whole control.

#### Construction

- `scope`: the `ThemeScope` this switch displays
- `flip`: what a click performs — the transition that changes `scope` (and,
  for the global switch, everything else with it)

#### Geometry

| Constant | Value | Meaning |
|----------|-------|---------|
| `Switch.HEIGHT` | 22 | Pill height in px — everything else derives from it |
| `Switch.ASPECT` | 2.1539 | Track width = `HEIGHT * ASPECT` |
| `Switch.KNOB_FACTOR` | 0.85 | Knob diameter = `HEIGHT * KNOB_FACTOR` |
| `Switch.PAD` | 4 | Margin for hover growth and the sun's rays |
| `Switch.ANIM_MS` | 420 | Knob slide duration |
| `Switch.HOVER_SCALE` | 1.05 | Knob growth on hover |
| `Switch.SUN_CELL_SCALE` | 1.7 | Sun art cell = knob diameter × this, so the rays reach past the disc |

#### Methods

- `mousePressEvent()`: left click calls the configured `flip` — the whole
  covered transition; the slide is driven by the resulting `changed` signal,
  not by the click itself
- `_sync_from_theme()`: animate the knob to match this scope's now-active
  theme — the one path that moves the knob, whether this switch was clicked
  or another one changed the scope
- `paintEvent()`: blit the track pill, then the knob at its animated x

### Painting

```
ON EACH PAINT:
    day = knob_x is past the midpoint between the off and on positions
    draw the day track if `day`, else the night track
    diameter = knob diameter, grown by HOVER_SCALE while hovered
    cell = diameter, grown by SUN_CELL_SCALE when drawing the sun
    draw the sun (if `day`) or the moon, centred on the knob position
```

---

## Design Decisions

**Why the flip happens before the animation.** The theme swaps synchronously
inside the flip, so the app is coherent the moment the click returns; the
420 ms slide is pure flourish, running while the cover fades out over it.
Reversing the order would leave the window half-repainted for the length of
the animation.

**Why the slide is driven by the signal, not the click.** `_sync_from_theme`
is the only code that moves the knob. A switch moved by a global flip and one
actually clicked follow the identical path, so they can never disagree about
which side the knob is on.

**Why the flip is injected rather than branched on.** The alternative was a
`global: bool` flag inside the widget, which would put the *policy* question
("does this switch move everyone?") inside a control that should only know
how to draw a pill. Passing the callable keeps the widget reusable and puts
the reach where it is decided — in the window or dialog that builds it.

**Why the pixmaps are cached.** [Icons](icons.md) caches by size, so a 420 ms
slide at 60 fps re-blits the same two pixmaps instead of re-rasterizing SVG
paths every frame.
