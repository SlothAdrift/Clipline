"""Render the release icon SVG to PNG and a multi-resolution Windows ICO."""

from pathlib import Path
from io import BytesIO

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


root = Path(__file__).resolve().parent
source = root / "assets" / "app_icon.svg"
renderer = QSvgRenderer(str(source))
if not renderer.isValid():
    raise RuntimeError(f"Invalid SVG: {source}")

canvas = QImage(1024, 1024, QImage.Format_ARGB32)
canvas.fill(Qt.transparent)
painter = QPainter(canvas)
renderer.render(painter)
painter.end()

png = root / "assets" / "app_icon.png"
if not canvas.save(str(png)):
    raise RuntimeError(f"Could not save {png}")

with Image.open(png) as image:
    image.save(root / "assets" / "app_icon.ico", format="ICO",
               sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                      (64, 64), (128, 128), (256, 256)])
