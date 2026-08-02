# Day/Night Switch

**Script:** [Day/Night Switch (script)](../theme_switch.py)

## Purpose

The Day/Night theme toggle shown in each window header and on the setup
screen — an image pill ported from the owner's website switch, the same
control PromptPainter uses (root Rule #5 — reuse, never re-author). OFF/left
is the MOON on a dark starfield track; ON/right is the SUN on a
sky-and-clouds track. A click flips the theme synchronously, then the knob
slides as an eased flourish.

The switch is deliberately dumb about REACH: it renders and animates one
`ThemeScope` and delegates the actual flip to the callable it was built
with. That is what lets the identical widget be a per-window toggle in a
monitor header (wired to `flip_window_theme`) and the global toggle on the
setup screen (wired to `flip_app_theme`) with no branch inside it.

## Connections

### Uses
- [Icons](icons.md) — `art()` for the two track pills and the sun/moon knobs
- [Styles](styles.md) — `Switch` geometry constants
- [Theme](theme.md) — the `ThemeScope` it renders and whose `changed` it follows

### Used by
- [Theme Transition (flow)](../__flow/transition.md) — supplies the two flip callables (`flip_window_theme`, `flip_app_theme`) this widget is built with
- [Windows (subfolder)](../windows/___windows.md) — one switch per monitor window header, wired to that window's own flip
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — one switch on the setup screen, wired to the global flip

## Classes

### DayNightSwitch
`QWidget` sized entirely from `Switch.HEIGHT`, so changing that one constant
rescales the whole control.

`DayNightSwitch(scope, flip, parent=None)` — `scope` is the `ThemeScope`
this switch displays; `flip` is what a click performs (the transition that
changes `scope`, and for the global switch, everything else with it).

| Method | Description |
|--------|--------------|
| `mousePressEvent()` | Left click calls the configured `flip` — the whole covered transition. The slide is driven by the resulting `changed` signal, not by the click itself. |
| `_sync_from_theme()` | Animates the knob to match this scope's now-active theme — the ONE path that moves the knob, whether this switch was clicked or another one changed the scope. |
| `_on_anim_value(value)` | `QVariantAnimation` callback — updates the knob x position and repaints. |
| `paintEvent()` | Blits the track pill (day/night hard-swap at the knob's midpoint crossing), then the knob at its animated x, with `HOVER_SCALE` growth and `SUN_CELL_SCALE` extra room for the sun's rays. |

## Design Decisions

- **The flip happens before the animation.** The theme swaps synchronously
  inside `flip()`, so the app is coherent the moment the click returns; the
  420ms slide is pure flourish, running while the cover fades out over it.
- **The slide is driven by the `changed` signal, not the click.**
  `_sync_from_theme()` is the only code that moves the knob, so a switch
  moved by a global flip and one actually clicked follow the identical path
  and can never disagree about which side the knob is on.
- **The flip is injected rather than branched on.** A `global: bool` flag
  inside the widget would put the reach question ("does this switch move
  everyone?") inside a control that should only know how to draw a pill.
  Passing the callable keeps the widget reusable and puts that decision
  where it is made — in the window or dialog that builds it.
