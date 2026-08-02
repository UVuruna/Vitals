# Icons

**Script:** [Icons (script)](../icons.py)

## Purpose

Renders every SVG in `assets/icons/` and tints it for the caller's theme.
Each icon is ONE master file; size and color variants are computed on
demand and cached, never shipped as separate per-theme/per-size assets
(root Rule #19). Two kinds of art live here: GLYPHS (`pause`, `play`,
`settings`) authored as solid white shapes and re-tinted at render time to
follow a scope's `ICON` token, and full-color ART (the Day/Night switch
track and its sun/moon knobs) rendered as-is, shared with the owner's
website switch.

## Connections

### Uses
- [Persistence](persistence.md) — `get_base_path()` to locate `assets/icons/`, frozen or from source
- [Theme](theme.md) — `ThemeScope`, the type `IconButton` binds to for its tint color and `changed` signal

### Used by
- [Day/Night Switch](theme_switch.md) — `art()` for the track pills and the sun/moon knobs
- [Theme Transition](transition.md) — `art()` for the big sun/moon cover icon
- [Windows (subfolder)](../windows/___windows.md) — `IconButton` for the header's pause/play and settings controls, `swatch()` for a process context-menu color chip

## Classes

### IconButton
Flat, borderless icon button that re-tints itself whenever ITS scope's
theme flips. The scope is passed in rather than looked up: a button belongs
to one window, and that window's `ThemeScope` is the only one it may
follow.

`IconButton(name, tooltip, scope, size=18, parent=None)`

| Method | Description |
|--------|--------------|
| `set_glyph(name)` | Swaps the displayed glyph, so one button can toggle between pause and play. |
| `apply_theme()` | Re-tints the glyph and rebuilds the hover-surface stylesheet from the bound scope's palette; connected to that scope's `changed`. |

## Functions

| Function | Description |
|----------|--------------|
| `icon_path(name)` | Absolute path to `assets/icons/<name>.svg`, frozen or from source. |
| `glyph(name, size, color)` | Cached single-color pixmap of a glyph master, tinted to `color` via SOURCE-IN composition (keeps the anti-aliased alpha edges, replaces only the fill). |
| `art(name, width, height)` | Cached full-color pixmap of an illustration at a size. |
| `swatch(color, size=12, radius=3)` | A rounded color-chip `QIcon` — the legend/menu color square. |

## Design Decisions

- **Filled glyphs, not stroked ones.** The header controls render at 18px;
  at that size a thin stroke on a narrow bar reads as a hollow outline,
  where solid rounded shapes stay crisp.
- **The switch art is rendered, not redrawn with `QPainter`.** Qt renders
  these SVGs faithfully, so the pill keeps the exact starfield/sky artwork
  from the owner's website switch instead of an approximation.
- **Both rasterizers are `@lru_cache`d.** The same `(name, size[, color])` is
  rendered once per process, so a theme flip and the switch's 420ms slide
  only blit already-rasterized pixmaps.
