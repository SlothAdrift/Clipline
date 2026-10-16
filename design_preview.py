"""Render the proposed clothesline artwork in one, two, and three-card states.

Run: python design_preview.py
The PNGs in design_previews are visual prototypes, not screenshots of the app.
"""

from pathlib import Path
import math
import random
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter,
    QPainterPath, QPen, QRadialGradient,
)


WIDTH, HEIGHT = 1440, 390
OUT = Path(__file__).with_name("design_previews")


def color(value: str, alpha: int = 255) -> QColor:
    c = QColor(value)
    c.setAlpha(alpha)
    return c


def rounded(p: QPainter, rect: QRectF, radius: float, fill, stroke=None, sw=1):
    p.setPen(QPen(stroke, sw) if stroke else Qt.NoPen)
    p.setBrush(fill)
    p.drawRoundedRect(rect, radius, radius)


def backdrop(p: QPainter):
    g = QLinearGradient(0, 0, WIDTH, HEIGHT)
    g.setColorAt(0, QColor("#c9d6f0"))
    g.setColorAt(0.47, QColor("#aaa6df"))
    g.setColorAt(1, QColor("#eac8d7"))
    p.fillRect(0, 0, WIDTH, HEIGHT, g)
    for x, y, r, hue in [(90, 355, 410, "#a48cde"),
                         (1160, 70, 390, "#f4b8c6"),
                         (630, 270, 370, "#909bdb")]:
        glow = QRadialGradient(x, y, r)
        glow.setColorAt(0, color(hue, 70))
        glow.setColorAt(1, color(hue, 0))
        p.fillRect(0, 0, WIDTH, HEIGHT, glow)


def rope_y(x: float) -> float:
    t = x / WIDTH
    return 51 + 20 * math.sin(math.pi * t)


def rope(p: QPainter):
    # Multiple continuous strokes suggest a lit silver cord. An alpha mask
    # fades the complete cord at both ends without visible segment seams.
    layer = QImage(WIDTH, 100, QImage.Format_ARGB32_Premultiplied)
    layer.fill(Qt.transparent)
    lp = QPainter(layer)
    lp.setRenderHint(QPainter.Antialiasing)
    for offset, width, shade, strength in [
        (3.1, 6.3, "#303e57", 43),
        (1.3, 4.5, "#65758d", 142),
        (0.0, 3.4, "#bac4d1", 242),
        (-1.05, 1.15, "#f8fbff", 200),
    ]:
        path = QPainterPath(QPointF(0, rope_y(0) + offset))
        for x in range(6, WIDTH + 6, 6):
            path.lineTo(QPointF(min(x, WIDTH), rope_y(min(x, WIDTH)) + offset))
        lp.setPen(QPen(color(shade, strength), width, Qt.SolidLine, Qt.RoundCap))
        lp.drawPath(path)
    # Sparse glints interrupt the highlight, like light catching woven fibers.
    for x in range(135, WIDTH - 130, 28):
        lp.setPen(QPen(color("#ffffff", 58), .8, Qt.SolidLine, Qt.RoundCap))
        lp.drawLine(QPointF(x, rope_y(x) - 1.7), QPointF(x + 7, rope_y(x + 7) - 1.7))
    lp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    fade = QLinearGradient(0, 0, WIDTH, 0)
    for stop, alpha in [(0, 0), (.035, 20), (.1, 175), (.16, 255),
                        (.84, 255), (.9, 175), (.965, 20), (1, 0)]:
        fade.setColorAt(stop, color("#ffffff", alpha))
    lp.fillRect(layer.rect(), fade)
    lp.end()
    p.drawImage(0, 0, layer)


def clip(p: QPainter, cx: float, top: float):
    p.save()
    p.translate(cx, top)
    # Cast shadow under the metallic head and at the card contact point.
    rounded(p, QRectF(-11, 3, 24, 35), 5, color("#31394a", 55))
    metal = QLinearGradient(-11, 0, 11, 0)
    for stop, c in [(0, "#84919f"), (.15, "#f8fbff"), (.38, "#d6dce2"),
                    (.69, "#ffffff"), (1, "#909eac")]:
        metal.setColorAt(stop, QColor(c))
    rounded(p, QRectF(-10, 0, 20, 34), 4.2, metal, color("#a6afb9", 210), .8)
    rounded(p, QRectF(-8, -5, 16, 9), 3.1, metal, color("#aab3bf", 200), .7)
    # The opening is deliberately vertical and dark, with a thin edge highlight.
    rounded(p, QRectF(-1.45, 9, 2.9, 20), 1.2, color("#222b36", 235))
    p.setPen(QPen(color("#ffffff", 175), .8))
    p.drawLine(QPointF(2.6, 9), QPointF(2.6, 28))
    p.setPen(QPen(color("#7c8796", 135), .8))
    p.drawLine(QPointF(-6, 31), QPointF(-6, 34))
    p.drawLine(QPointF(6, 31), QPointF(6, 34))
    p.restore()


def card(p: QPainter, cx: float, top: float, style: int):
    w, h = 216, 154
    r = QRectF(cx - w / 2, top, w, h)
    for dx, dy, alpha in [(0, 13, 14), (0, 8, 15), (0, 4, 22)]:
        rounded(p, r.translated(dx, dy), 13, color("#26304d", alpha))
    rounded(p, r, 13, color("#fbfcff", 244), color("#ffffff", 190), 1)
    p.save()
    p.setClipRect(r.adjusted(1, 1, -1, -1))
    rounded(p, QRectF(r.left(), top, w, 27), 12, color("#eef0f6", 245))
    p.setPen(Qt.NoPen)
    for i, c in enumerate(["#d7a8a7", "#dec79a", "#9cceb9"]):
        p.setBrush(color(c, 225))
        p.drawEllipse(QPointF(r.left() + 14 + i * 11, top + 13), 2.6, 2.6)
    p.setPen(color("#788397"))
    f = QFont("Microsoft YaHei", 8)
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    titles = ["截图 01 · 页面概览", "截图 02 · 笔记片段", "截图 03 · 设计参考"]
    p.drawText(QRectF(r.left() + 58, top + 3, 128, 20), Qt.AlignCenter, titles[style])

    if style == 0:
        p.setPen(color("#465574"))
        f.setPointSize(10)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 14, top + 41, w - 28, 20), "本周概览")
        for i, label in enumerate(["248", "31", "0"]):
            x = r.left() + 14 + i * 64
            rounded(p, QRectF(x, top + 66, 57, 37), 5, color("#eff2f9"))
            p.setPen(color("#45516d"))
            p.drawText(QRectF(x + 7, top + 73, 49, 22), label)
        wave = QPainterPath(QPointF(r.left() + 14, top + 128))
        for i in range(1, 39):
            x = r.left() + 14 + i * 4.9
            y = top + 130 - i * .36 - 4 * math.sin(i * .31)
            wave.lineTo(x, y)
        p.setPen(QPen(color("#6d83c4"), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(wave)
    elif style == 1:
        p.setPen(color("#465574"))
        f.setPointSize(10)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 14, top + 40, w - 28, 22), "灵感备忘")
        for i, (dot, length) in enumerate([("#d6b866", 153), ("#9aa7da", 133),
                                            ("#a6c2ae", 163), ("#c9a5b8", 112)]):
            y = top + 75 + i * 18
            p.setBrush(QColor(dot)); p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(r.left() + 18, y), 3, 3)
            rounded(p, QRectF(r.left() + 29, y - 2.5, length, 5), 2, color("#b6becd", 155))
    else:
        art = QRectF(r.left() + 12, top + 39, w - 24, 101)
        g = QLinearGradient(art.topLeft(), art.bottomRight())
        g.setColorAt(0, QColor("#a9c2d9")); g.setColorAt(1, QColor("#e9ccba"))
        rounded(p, art, 7, g)
        p.setBrush(color("#fbf1df", 220)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(art.right() - 36, art.top() + 28), 15, 15)
        hill = QPainterPath(QPointF(art.left(), art.bottom()))
        hill.cubicTo(art.left() + 45, art.top() + 46,
                     art.left() + 100, art.top() + 86, art.right(), art.top() + 59)
        hill.lineTo(art.bottomRight()); hill.closeSubpath()
        p.fillPath(hill, color("#768fa2", 195))
        hill2 = QPainterPath(QPointF(art.left(), art.bottom()))
        hill2.cubicTo(art.left() + 62, art.top() + 84,
                      art.left() + 146, art.top() + 71, art.right(), art.top() + 97)
        hill2.lineTo(art.bottomRight()); hill2.closeSubpath()
        p.fillPath(hill2, color("#4d7885", 180))
    p.restore()


def card_angles(count: int) -> list[float]:
    """Sample up to 3 degrees, with larger expected tilt toward the edges.

    At normalized distance d from the center, the magnitude is sampled from
    3 * Beta(1+3d, 4-3d). Its expectation is 0.6+1.8d degrees. The exact
    center of an odd count stays horizontal. A fixed seed keeps previews stable.
    """
    if count < 1:
        raise ValueError("count must be positive")
    rng = random.Random(20261013 + count)
    angles = []
    midpoint = (count - 1) / 2
    for i in range(count):
        if i == midpoint:
            angles.append(0.0)
            continue
        distance = abs(i - midpoint) / midpoint
        magnitude = round(3.0 * rng.betavariate(1 + 3 * distance,
                                                4 - 3 * distance), 1)
        if i < midpoint:
            angles.append(magnitude)  # Qt's positive angle is clockwise onscreen.
        else:
            angles.append(-magnitude)
    return angles


def render(count: int):
    image = QImage(WIDTH, HEIGHT, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    backdrop(p)
    rope(p)
    spacing = 244
    centers = [WIDTH / 2 + (i - (count - 1) / 2) * spacing for i in range(count)]
    for i, (cx, angle) in enumerate(zip(centers, card_angles(count))):
        top = rope_y(cx) + 29
        p.save()
        p.translate(cx, top)
        p.rotate(angle)
        p.translate(-cx, -top)
        card(p, cx, top, i)
        p.restore()
        clip(p, cx, rope_y(cx) - 8)
    p.end()
    OUT.mkdir(exist_ok=True)
    image.save(str(OUT / f"{count}_images.png"))
    return image


def main():
    app = QGuiApplication(sys.argv)
    images = [render(n) for n in (1, 2, 3)]
    sheet = QImage(WIDTH, HEIGHT * 3, QImage.Format_ARGB32_Premultiplied)
    sheet.fill(Qt.transparent)
    p = QPainter(sheet)
    for i, image in enumerate(images):
        p.drawImage(0, i * HEIGHT, image)
    p.end()
    sheet.save(str(OUT / "comparison.png"))
    print(OUT.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
