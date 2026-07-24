# Day/Night Switch

**Script:** [Day/Night Switch (script)](theme_switch.py)

---

## Purpose

The Day/Night theme toggle in each window header — an image pill ported from
the owner's website switch, the same control PromptPainter uses.

- **OFF / left** — the MOON on a dark starfield track → dark theme
- **ON / right** — the SUN on a sky-and-clouds track → light theme

A click flips the app theme immediately; the knob then slides as an eased
flourish, and the track pill hard-swaps night ↔ day as the knob passes the
midpoint.

Every monitor window carries its own switch. All of them listen to
`theme_manager().changed`, so flipping the theme in the CPU window slides the
Memory and Network switches too — the three gadgets are never out of sync.

---

## Connections

### Uses

- [Icons](icons.md) — `art()` for the two track pills and the sun/moon knobs
- [Styles](styles.md) — `Switch` geometry constants
- [Theme](theme.md) — `theme_manager()` to flip the theme and to follow another window's flip

### Used by

- [Main Window](main_window.md) — one instance in each window header, stacked above the total value

---

## Classes

### DayNightSwitch

`QWidget` sized entirely from `Switch.HEIGHT`, so changing that one constant
rescales the whole control.

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

- `mousePressEvent()`: left click flips the theme; the slide is driven by the
  resulting `changed` signal, not by the click itself
- `_sync_from_theme()`: animate the knob to match the now-active theme —
  the one path that moves the knob, whichever window was clicked
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
on click, so the app is coherent instantly; the 420 ms slide is pure
flourish. Reversing the order would leave the window half-repainted for the
length of the animation.

**Why the slide is driven by the signal, not the click.** `_sync_from_theme`
is the only code that moves the knob. A switch in another window and the one
actually clicked follow the identical path, so they can never disagree about
which side the knob is on.

**Why the pixmaps are cached.** [Icons](icons.md) caches by size, so a 420 ms
slide at 60 fps re-blits the same two pixmaps instead of re-rasterizing SVG
paths every frame.
