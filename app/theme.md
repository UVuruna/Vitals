# Theme

**Script:** [Theme (script)](theme.py)

---

## Purpose

The single source of truth for **every color** in Vitals, and the engine that
flips the whole app between the **Dark** and **Light** palettes at runtime.

Colors used to live in [Styles](styles.md) as a frozen `Colors` table read
directly inside module-level f-strings — which froze the dark palette at
import time and made a runtime theme impossible. This module replaces that
with a **live lookup**: every widget calls `theme()` when it builds or
rebuilds a stylesheet, and re-runs that build when `theme_manager().changed`
fires.

Colors are also **computed, not enumerated** (root Rule #19). There is no
second hand-authored table of light-mode process colors: one set of hues is
re-shaded per theme by `shade_for_theme()`.

---

## Connections

### Uses

- [Persistence](persistence.md) — reads/writes the chosen theme in `last_setup.json`

### Used by

- [Styles](styles.md) — `theme()` for `context_menu_style()`
- [Color Management](color_management.md) — `theme()`, `wheel_color()`, `shade_for_theme()`, `theme_manager()`
- [Main Window](main_window.md) — `theme()` for every window stylesheet, `theme_manager().changed` to restyle
- [Settings Dialog](settings_dialog.md) — `theme()`, `theme_manager()`
- [Icons](icons.md) — `theme()` for glyph tinting
- [Day/Night Switch](theme_switch.md) — `theme_manager()` to flip and to follow other windows
- [Tray Controller](tray.md) — restyles its menu on a flip
- `process_dialog.py` — `theme()` for the kill/priority dialogs

---

## Classes

### Palette

Frozen dataclass holding one complete theme. Two instances exist: `DARK` and
`LIGHT`, registered in `THEMES`.

#### Attributes

**Surfaces** — `BACKGROUND`, `CARD`, `HEADER`, `BORDER`, `SECTION_BG`
(one shared table surface; the three sections no longer differ).

**Accent** — `ACCENT`, `ACCENT_HOVER`, plus `CONFIRM` / `CONFIRM_HOVER` for
the priority dialog's Apply button.

**Text** — `TEXT`, `TEXT_MUTED`, `TEXT_DIM`, `TEXT_FAINT`, `TEXT_DISABLED`.

**Header controls** — `ICON`, `ICON_HOVER` for the pause/play and settings
glyphs.

**Sensors** — `TEMP_WARNING`, `TEMP_CRITICAL`.

**Process coloring** — `COMPANY_TOP` (the company with the most processes:
white on dark, black on light), `COMPANY_UNKNOWN` (the reserved gray for
processes with no company info), `HUE_SATURATION` / `HUE_LIGHTNESS` (wheel
defaults for that theme), `VALUE_LIGHTNESS` (target lightness for usage
colors).

#### Palette values

| Token | Dark | Light |
|-------|------|-------|
| `BACKGROUND` | `#1e1e2e` | `#eceef6` |
| `CARD` | `#2a2a3e` | `#ffffff` |
| `HEADER` | `#3a3a4e` | `#dfe2ee` |
| `BORDER` | `#4a4a5e` | `#c7cbdd` |
| `SECTION_BG` | `#2d2d42` | `#f7f8fc` |
| `ACCENT` / `ACCENT_HOVER` | `#e94560` / `#ff6b6b` | `#d1274a` / `#e94560` |
| `CONFIRM` / `CONFIRM_HOVER` | `#3a6a3a` / `#4a8a4a` | `#2e7d32` / `#388e3c` |
| `TEXT` … `TEXT_DISABLED` | `#ffffff` … `#555555` | `#16161f` … `#a9aec0` |
| `ICON` / `ICON_HOVER` | `#b9bcd0` / `#ffffff` | `#4c5162` / `#16161f` |
| `TEMP_WARNING` / `TEMP_CRITICAL` | `#ffa500` / `#ff4444` | `#b26a00` / `#c62828` |
| `COMPANY_TOP` | `#ffffff` | `#000000` |
| `COMPANY_UNKNOWN` | `#9a9aa8` | `#6b7280` |
| `HUE_SATURATION` / `HUE_LIGHTNESS` | `0.84` / `0.84` | `0.84` / `0.34` |
| `VALUE_LIGHTNESS` | `0.60` | `0.36` |

Light mode is **darker everywhere text is concerned** and dark mode lighter —
the contrast rule the owner set for every color in the app.

### ThemeManager

`QObject` singleton owning the active palette. Reached through
`theme_manager()`; never constructed directly.

#### Attributes

- `changed`: `Signal()` — emitted **after** the palette swaps, so a slot can
  simply re-read `theme()`
- `palette`: the active `Palette`
- `name`: `"dark"` or `"light"`

#### Methods

- `is_dark()`: True when the dark palette is active
- `set_theme(name)`: activate, persist to `last_setup.json`, emit `changed`.
  A no-op if that theme is already active, so a switch reflecting someone
  else's flip cannot loop
- `toggle()`: flip dark ↔ light, returns the new name

---

## Functions

| Function | Description |
|----------|-------------|
| `theme_manager()` | The process-wide `ThemeManager`, created on first use. |
| `theme()` | The **active** `Palette`. Call at paint/restyle time, never at import. |
| `wheel_hue(slot, slots)` | Hue in degrees for one slot of the company wheel. |
| `wheel_color(slot, slots, saturation, lightness)` | The `QColor` for one wheel slot. |
| `shade_for_theme(color, palette)` | Re-shade an authored hue to the theme's readable lightness (hue and saturation preserved). |

### The color wheel

`HUE_START_DEG` = 240° (blue), `HUE_END_DEG` = 0° (red). The ramp runs
**counter-clockwise on the HSL circle**, so it passes through cyan, green and
yellow and deliberately skips the magenta-purple arc — one cool-to-warm scale
instead of a full rainbow.

```
FUNCTION wheel_hue(slot, slots):
    IF slots <= 1 → RETURN 240        # a lone slot is simply blue
    span = 240 - 0
    RETURN 240 - span * (slot / (slots - 1))
```

### Re-shading

```
FUNCTION shade_for_theme(color, palette):
    (hue, saturation, lightness, alpha) = color AS HSL
    RETURN color FROM HSL(hue, saturation, palette.VALUE_LIGHTNESS, alpha)
```

Only lightness moves. One authored hue therefore yields a light tint on dark
surfaces and a deep tint on light ones, with no second table to maintain.

---

## Design Decisions

**Why a live `theme()` call and not a module constant.** The old `Colors`
dataclass was read inside module-level f-strings (`CONTEXT_MENU_STYLE`) and
even inside default arguments (`color: str = Colors.TEXT`). Both evaluate
once, at import — a theme flip could never reach them. Every such site is now
either a function or resolves its default at call time.

**Why the palette carries data tokens.** `COMPANY_TOP`, `COMPANY_UNKNOWN`,
`HUE_*` and `VALUE_LIGHTNESS` are process-coloring inputs, not window chrome —
but they must flip with the theme, so they live with the palette rather than
in [Color Management](color_management.md).

**Persistence.** The chosen theme is stored as `"theme"` in
`last_setup.json`, so a restart comes back in the same mode.
