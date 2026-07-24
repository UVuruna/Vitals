# Icons

**Script:** [Icons (script)](icons.py)

---

## Purpose

Renders every SVG in `assets/icons/` and tints it for the active theme.

Each icon is **one master file**; size and color variants are computed on
demand and cached, never shipped as separate assets (root Rule #19). A glyph
authored as solid white becomes the theme's `ICON` color through one
composition pass — there is no `pause-dark.svg` / `pause-light.svg` pair.

Two kinds of art live here:

| Kind | Files | Treatment |
|------|-------|-----------|
| **Glyphs** | `pause.svg`, `play.svg`, `settings.svg` | Solid white masters, re-tinted per theme |
| **Art** | `switch_night.svg`, `switch_day.svg`, `moon.svg`, `sun.svg` | Full-color illustrations, rendered as-is |

The switch art is the owner's own website switch, shared with PromptPainter
rather than re-authored (root Rule #5).

---

## Connections

### Uses

- [Theme](theme.md) — `theme()` for the tint color, `theme_manager()` to re-tint on a flip
- [Persistence](persistence.md) — `get_base_path()` to locate `assets/icons/` frozen or from source

### Used by

- [Main Window](main_window.md) — `IconButton` for the header's pause/play and settings controls, `swatch()` for the context-menu company color chip
- [Day/Night Switch](theme_switch.md) — `art()` for the track pills and sun/moon knobs

---

## Classes

### IconButton

Flat, borderless icon button that re-tints itself whenever the theme flips.
Used for the two header controls that replaced the old menu bar.

#### Methods

- `set_glyph(name)`: swap the displayed glyph, so one button toggles between
  pause and play
- `apply_theme()`: re-tint the glyph and rebuild the hover surface from the
  active palette (connected to `theme_manager().changed`)

---

## Functions

| Function | Description |
|----------|-------------|
| `icon_path(name)` | Absolute path to `assets/icons/<name>.svg`, frozen or from source. |
| `glyph(name, size, color)` | Cached single-color pixmap of a glyph master, tinted to `color`. |
| `art(name, width, height)` | Cached full-color pixmap of an illustration at a size. |
| `swatch(color, size, radius)` | A rounded color-chip `QIcon` — the legend/menu color square. |

### Tinting

```
FUNCTION glyph(name, size, color):
    pixmap = rasterize the master SVG at size x size (transparent background)
    paint over pixmap using SOURCE-IN composition with a solid fill of `color`
    # SOURCE-IN keeps the glyph's anti-aliased alpha and replaces only its RGB
    RETURN pixmap
```

Results are cached by `(name, size, color)`, so a theme flip and the switch
animation only blit already-rasterized pixmaps.

---

## Design Decisions

**Why filled glyphs rather than stroked ones.** The header controls render at
18 px. At that size a 2 px stroke on a 4 px-wide bar reads as a hollow
outline; solid shapes with rounded corners stay crisp. All three glyphs share
that one style, so the control row is a single icon family
([DESIGN.md](../../../DESIGN.md) — never mix icon styles).

**Why the switch art is rendered, not drawn.** Qt renders these SVGs
faithfully (verified against the real files), so the pill keeps the exact
starfield/sky artwork from the owner's website instead of an approximation
redrawn with `QPainter`.
