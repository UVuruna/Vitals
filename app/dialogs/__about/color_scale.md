# Color Scale

**Script:** [Color Scale (script)](../color_scale.py)

## Purpose

`ColorScaleWidget` paints the five usage-color zones of one color mode as a
gradient bar with four draggable diamond handles marking the boundaries
between them. Dragging a handle moves that threshold; the owning settings
dialog reads `.thresholds` back on Apply/accept and hands them to
`ProcessColorManager.update_value_thresholds()`. The widget never touches
`ProcessColorManager` itself — it only tracks its own local state while
dragging, which is what lets canceling a dialog leave persisted thresholds
untouched.

## Connections

### Uses
- [Theme](../../__about/theme.md) — `ThemeScope`, which decides the handle outline color and the percentage labels' color

### Used by
- [Base Settings Dialog](base_dialog.md) — built and returned by `_build_color_section()`, one instance per color-settings section on every settings dialog

## Classes

### ColorScaleWidget (QWidget)
`ColorScaleWidget(colors, thresholds, scope, parent=None, scale_max=100)` —
`colors` is the 5 zone `QColor`s, `thresholds` the 4 ascending boundary
values, `scope` the `ThemeScope` its outline/labels follow.

| Member | Description |
|--------|-------------|
| `thresholds_changed` (Signal) | Emitted with the current 4-int threshold list on every drag move. |
| `paintEvent(event)` | Draws the 5 color segments, the 4 diamond handles (each colored with the zone it ends), and the percentage labels below them. |
| `mousePressEvent` / `mouseMoveEvent` / `mouseReleaseEvent` | Hit-tests the nearest handle within a tolerance, clamps a drag between its two neighbors, repaints and emits `thresholds_changed`. |
| `thresholds` (property) | Current threshold list, read by the owning dialog on accept. |
| `set_thresholds(thresholds)` | Overwrites the displayed thresholds (e.g. from saved settings) and repaints. |
