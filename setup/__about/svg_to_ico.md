# SVG to ICO

**Script:** [SVG to ICO (script)](../svg_to_ico.py)

## Purpose

Renders `assets/icon.svg` into a multi-resolution `assets/icon.ico`
(16/32/48/64/128/256 px) using `QSvgRenderer` for the vector source and
Pillow's Lanczos filter for the downscale, so small taskbar/Explorer sizes
stay crisp instead of looking like a naive single-size rasterization. Called
by `build.py`'s `generate_ico()` as a subprocess step; also runnable
standalone via `python setup/svg_to_ico.py`.

## Connections

### Uses
- none — reads only `assets/icon.svg`; PySide6 (`QtCore`/`QtGui`/`QtSvg`)
  and Pillow are third-party, not project code

### Used by
- [Build Orchestrator](build.md) — `generate_ico()` runs this script as a
  subprocess (`python setup/svg_to_ico.py`), not an import

## Functions

- `_render_svg_to_pil(renderer, size) -> Image.Image` — renders one size at
  4x supersampling for `size <= 64`, 2x for `size <= 128`, or 1x for the
  256 px frame, via a `QPainter` with antialiasing and smooth-pixmap-
  transform enabled. Converts the resulting `QImage` (BGRA) to a Pillow RGBA
  image and Lanczos-downscales it back to the target size whenever it was
  supersampled.
- `generate_ico() -> Path` — creates a `QGuiApplication` if none exists yet
  (`QSvgRenderer` needs one), renders every size in `ICO_SIZES`, warns if
  any frame comes out fully transparent, reverses the frame order (largest
  first — Windows uses the first frame as the primary icon), and saves them
  all as one multi-frame `.ico` via Pillow.
- `main()` — CLI entry point: calls `generate_ico()` and prints the
  rendered size list.
