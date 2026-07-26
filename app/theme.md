# Theme

**Script:** [Theme (script)](theme.py)

---

## Purpose

The single source of truth for **every color** in Vitals, and the engine that
flips a **scope** between the **Dark** and **Light** palettes at runtime.

Colors used to live in [Styles](styles.md) as a frozen `Colors` table read
directly inside module-level f-strings — which froze the dark palette at
import time and made a runtime theme impossible. This module replaces that
with a **live lookup**: every widget reads `scope.palette` when it builds or
rebuilds a stylesheet, and re-runs that build when `scope.changed` fires.

**Themes are per scope, not per app** (owner 2026-07-26). Each monitor
window owns a `ThemeScope`, so the Day/Night switch in the CPU header flips
the CPU window **alone** — Memory and Network keep theirs. The app-wide
scope styles the tray and the setup screen, and the setup screen's switch is
the GLOBAL one: `set_theme_everywhere()` forces its choice on all three.

Colors are also **computed, not enumerated** (root Rule #19). There is no
second hand-authored table of light-mode process colors: one set of hues is
re-shaded per theme by `shade_for_theme()`.

---

## Scopes at a glance

| Scope | Reached by | Styles | Flipped by |
|-------|-----------|--------|-----------|
| App-wide | `app_theme()` | tray menu, setup screen; the default for a window with no remembered theme | the setup screen's switch (global) |
| `cpu` / `memory` / `network` | `window_theme(key)` | that monitor window and everything it opens (settings dialog, legend, kill/priority dialogs, context menu) | that window's header switch — **and** a global flip |

Each scope remembers its own choice: the app-wide one in `theme`, a window's
in `windows.<key>.theme`.

---

## Connections

### Uses

- [Persistence](persistence.md) — reads/writes each scope's theme in `last_setup.json`

### Used by

- [Styles](styles.md) — takes a `Palette` in `context_menu_style()`
- [Color Management](color_management.md) — `Palette`, `THEMES`, `wheel_color()`, `shade_for_theme()`
- [Main Window](main_window.md) — `window_theme()`; every window stylesheet reads its own scope, `scope.changed` restyles
- [Settings Dialog](settings_dialog.md) — `app_theme()` for the setup screen; a window's scope for the per-mode dialogs
- [Icons](icons.md) — a scope per `IconButton`, for glyph tinting
- [Day/Night Switch](theme_switch.md) — the scope it renders and follows
- [Theme Transition](transition.md) — `app_theme()`, `set_theme_everywhere()`
- [Tray Controller](tray.md) — `app_theme()`; restyles its menu on a global flip
- `process_dialog.py` — takes the calling window's `Palette`

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

### ThemeScope

`QObject` owning the palette of **one** surface. Reached through
`app_theme()` or `window_theme(key)`; never constructed directly, so the same
window always gets the same scope object.

#### Attributes

- `changed`: `Signal()` — emitted **after** the palette swaps, so a slot can
  simply re-read `scope.palette`
- `palette`: this scope's active `Palette`
- `name`: `"dark"` or `"light"`

#### Methods

- `is_dark()`: True when the dark palette is active
- `next_name()`: the name of the OTHER theme — what a flip would activate
- `set_theme(name)`: activate, remember in this scope's `last_setup.json`
  slot, emit `changed`. A no-op if that theme is already active, so a global
  flip that matches a window costs nothing and a switch reflecting someone
  else's flip cannot loop

#### Initial theme

```
FUNCTION initial theme of a scope:
    IF this is the app scope  → last_setup["theme"]
    ELSE                      → last_setup["windows"][key]["theme"]
                                OR last_setup["theme"] if the window has none
    fall back to DARK if neither is a known theme name
```

---

## Functions

| Function | Description |
|----------|-------------|
| `app_theme()` | The app-wide `ThemeScope`, created on first use. |
| `window_theme(key)` | The scope for one monitor window (`'cpu'` / `'memory'` / `'network'`), created on first use and kept for the app's lifetime. |
| `set_theme_everywhere(name)` | Force one theme on the app scope, every live window scope, and the remembered choice of a window that is not open yet. |
| `wheel_hue(slot, slots)` | Hue in degrees for one slot of the company wheel. |
| `wheel_color(slot, slots, saturation, lightness)` | The `QColor` for one wheel slot. |
| `shade_for_theme(color, palette)` | Re-shade an authored hue to the theme's readable lightness (hue and saturation preserved). |

### The global flip

```
FUNCTION set_theme_everywhere(name):
    app scope → set_theme(name)                # persists last_setup["theme"]
    FOR EACH live window scope:
        scope → set_theme(name)                # persists windows.<key>.theme
    FOR EACH saved window entry with a different theme:
        overwrite its theme with `name`        # a closed window must not
    save                                       # resurrect its old choice
```

That last step is the non-obvious one: a monitor that has never been opened
this session has no live scope, only a saved entry. Without rewriting it, a
global flip to light would be silently undone the moment the user opened
that window.

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

**Why a live palette read and not a module constant.** The old `Colors`
dataclass was read inside module-level f-strings (`CONTEXT_MENU_STYLE`) and
even inside default arguments (`color: str = Colors.TEXT`). Both evaluate
once, at import — a theme flip could never reach them. Every such site is now
either a function taking a `Palette` or resolves its default at call time.

**Why scopes replaced a single global theme.** A global `theme()` lookup
made per-window themes impossible to express: any widget could reach the one
active palette, so flipping one window necessarily flipped the rest. The
global accessor was therefore **removed outright** (root Rule #6 — no
compatibility shim) rather than kept beside the scopes. That was deliberate:
every one of the ~120 call sites had to be revisited and given the scope it
belongs to, and a site that was missed fails loudly at import instead of
silently painting the wrong window's theme.

**Why the palette is passed down instead of looked up.** `IconButton`,
`ColorScaleWidget`, `TotalRowDelegate` and the dialogs all take their scope
(or a plain `Palette`) at construction. A widget cannot ask "what is the
theme?" any more — only "what is MY window's theme?" — which is what makes a
one-window flip provably contained.

**Why the palette carries data tokens.** `COMPANY_TOP`, `COMPANY_UNKNOWN`,
`HUE_*` and `VALUE_LIGHTNESS` are process-coloring inputs, not window chrome —
but they must flip with the theme, so they live with the palette rather than
in [Color Management](color_management.md).

**Persistence.** Each scope owns one slot: the app-wide theme is `"theme"`,
a window's is `windows.<key>.theme`. [Main Window](main_window.md)'s layout
save **updates** its window entry rather than replacing it, so saving
geometry can never wipe the theme the scope wrote there.
