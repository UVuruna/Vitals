"""
Generate ICO file from assets/icon.svg.

Renders with anti-aliased QPainter + supersampled downscale (Lanczos)
for crisp results at every size.

Called automatically by build.py. Can also be run standalone:
    python setup/svg_to_ico.py

Requires: PySide6, Pillow.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image

SETUP_DIR = Path(__file__).parent
PROJECT_DIR = SETUP_DIR.parent

SVG_PATH = PROJECT_DIR / "assets" / "icon.svg"
ICO_PATH = PROJECT_DIR / "assets" / "icon.ico"

# Standard Windows ICO sizes
ICO_SIZES = [16, 32, 48, 64, 128, 256]


def _render_svg_to_pil(renderer: QSvgRenderer, size: int) -> Image.Image:
    """Render SVG at the given size and return a Pillow RGBA Image.

    Uses supersampling for small sizes: renders at a higher resolution
    then downscales with Lanczos for maximum sharpness.
    """
    # Supersample factor — higher for small icons where detail matters most
    if size <= 64:
        factor = 4
    elif size <= 128:
        factor = 2
    else:
        factor = 1

    render_size = size * factor

    qimage = QImage(QSize(render_size, render_size), QImage.Format.Format_ARGB32)
    qimage.fill(Qt.GlobalColor.transparent)

    painter = QPainter(qimage)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()

    buf = qimage.bits().tobytes()
    img = Image.frombytes("RGBA", (render_size, render_size), buf, "raw", "BGRA")

    if factor > 1:
        img = img.resize((size, size), Image.Resampling.LANCZOS)

    return img


def generate_ico() -> Path:
    """Generate ICO from SVG. Returns path to the ICO file."""
    # QSvgRenderer needs a QGuiApplication
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv)

    if not SVG_PATH.exists():
        raise FileNotFoundError(f"SVG not found: {SVG_PATH}")

    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        raise RuntimeError(f"Failed to load SVG: {SVG_PATH}")

    frames = []
    for size in ICO_SIZES:
        img = _render_svg_to_pil(renderer, size)
        if img.getextrema()[3] == (0, 0):
            print(f"  WARNING: {size}x{size} frame is fully transparent!")
        frames.append(img)

    # Largest frame first (Windows uses it as the primary)
    frames.reverse()
    frames[0].save(
        str(ICO_PATH),
        format="ICO",
        append_images=frames[1:],
    )

    size_kb = ICO_PATH.stat().st_size / 1024
    print(f"  {ICO_PATH.name} ({size_kb:.0f} KB) <- icon.svg")

    return ICO_PATH


def main():
    print("Generating ICO from SVG:")
    generate_ico()
    print(f"Sizes: {', '.join(f'{s}x{s}' for s in ICO_SIZES)}")


if __name__ == "__main__":
    main()
