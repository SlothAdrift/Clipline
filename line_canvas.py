"""Transparent, animated clothesline canvas for the Windows desktop."""

from __future__ import annotations

import ctypes
import math
import random
import sys
import time
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor, QCursor, QDrag, QFont, QFontMetrics, QGuiApplication, QImage,
    QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRegion,
)
from PySide6.QtWidgets import QWidget


VISIBLE = 5
CARD_W, CARD_H = 176, 132
SHADOW_MARGIN = 30
EDGE_SHADOW_SPREAD = 8
CONTROL_SIZE = 30
ARROW_MASK_MARGIN = 1
CARD_CLIP_OVERHANG = 14
CAT_SIZE = 54
MOVE_TIME = 0.40
SETTLE_TIME = 1.0
DROP_TIME = 0.45
CARD_FADE_TIME = 0.30
RETRACT_TIME = 0.40
IDLE_TIME = 10.0
COPY_FEEDBACK_TIME = 1.0
COPY_FEEDBACK_FADE = 0.25


class ClotheslineWindow(QWidget):
    toggle_requested = Signal()
    quit_requested = Signal()
    clear_requested = Signal()
    copied = Signal(str)
    removed = Signal(str)
    edit_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clipline")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.resize(1200, 270)
        self.enabled = False
        self.images: list[str] = []
        self.root = Path()
        self.pixmaps: dict[str, QPixmap] = {}
        self.card_shadow = self._make_card_shadow()
        self.offset = 0
        self.angles: dict[str, float] = {}
        self.single_card_wobble = False
        self.from_centers: dict[str, float] = {}
        self.to_centers: dict[str, float] = {}
        self.transition_mask = QRegion()
        self.previous_image_count = 0
        self.move_started = -100.0
        self.settle_started = -100.0
        self.phase = "steady"
        self.phase_started = -100.0
        self.vertical_shift = 0.0
        self.sag_fraction = 1.0
        self.rope_opacity = 1.0
        self.cards_opacity = 1.0
        self.phase_start_shift = 0.0
        self.phase_start_sag = 1.0
        self.phase_start_rope_opacity = 1.0
        self.phase_start_cards_opacity = 1.0
        self.last_action = time.monotonic()
        self.hovered: str | None = None
        self.hovered_control: str | None = None
        self.cat_hover_progress = 0.0
        self.cat_hover_updated = time.monotonic()
        self.copy_feedback_name: str | None = None
        self.copy_feedback_started = -100.0
        self.pressed: tuple[str, str | None] | None = None
        self.press_pos = QPoint()
        self.dragging = False
        self.long_pressed = False
        self.pending_edit: str | None = None
        self.long_press = QTimer(self)
        self.long_press.setSingleShot(True)
        self.long_press.timeout.connect(self._long_press)
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.advance)
        self.frame_timer.start(16)

    def place(self, cursor: QPoint | None = None):
        screen = QGuiApplication.screenAt(cursor or QCursor.pos()) or QGuiApplication.primaryScreen()
        rect = screen.availableGeometry()
        self.setGeometry(rect.x(), rect.y() + 70, rect.width(), 270)

    def set_enabled(self, enabled: bool):
        was_enabled = self.enabled
        self.enabled = enabled
        self.last_action = time.monotonic()
        if enabled and not was_enabled and self.isVisible():
            self.vertical_shift = -12.0
            self.sag_fraction = 0.0
            self.rope_opacity = 1.0
            self.cards_opacity = 0.0
            self._start_drop()
        self.update()

    def max_offset(self) -> int:
        return max(0, len(self.images) - VISIBLE)

    def slot_centers(self, count: int) -> list[float]:
        shown = min(count, VISIBLE)
        spacing = min(224.0, (self.width() - 160) / max(1, VISIBLE - 1))
        return [self.width() / 2 + (i - (shown - 1) / 2) * spacing
                for i in range(shown)]

    def center_for(self, index: int, offset: int, count: int) -> float:
        slots = self.slot_centers(count)
        if count <= VISIBLE:
            return slots[index]
        spacing = slots[1] - slots[0]
        return slots[0] + (index - offset) * spacing

    def _random_angles(self):
        shown = min(len(self.images), VISIBLE)
        midpoint = (shown - 1) / 2
        for i, name in enumerate(self.images):
            visual_slot = i - self.offset
            if shown % 2 == 1 and visual_slot == midpoint:
                self.angles[name] = 0.0
            else:
                distance = min(1.0, abs(visual_slot - midpoint) / max(0.5, midpoint))
                magnitude = 3.0 * random.betavariate(1 + 3 * distance, 4 - 3 * distance)
                self.angles[name] = magnitude if visual_slot < midpoint else -magnitude

    def set_images(self, root: Path, images: list[str], added: bool = False):
        old = self.images[:]
        old_centers = {name: self._center(name, i) for i, name in enumerate(old)}
        old_mask = self.mask()
        self.previous_image_count = len(old)
        self.root = root
        self.images = images[:]
        if self.copy_feedback_name not in self.images:
            self.copy_feedback_name = None
        self.single_card_wobble = added and not old and len(self.images) == 1
        self.pixmaps = {name: self.pixmaps.get(name) or self._load_preview(name)
                        for name in self.images}
        self.offset = 0 if added else min(self.offset, self.max_offset())
        if old != self.images and (old or added):
            self.from_centers = old_centers
            self.to_centers = {name: self.center_for(i, self.offset, len(self.images))
                               for i, name in enumerate(self.images)}
            self.move_started = time.monotonic()
            self.settle_started = (self.move_started if self.single_card_wobble
                                   else self.move_started + MOVE_TIME)
            self._random_angles()
            self.transition_mask = old_mask
            viewport = QRegion(self._viewport().toRect())
            for name in self.images:
                start = self.from_centers.get(name, self.to_centers[name] - 190)
                finish = self.to_centers[name]
                left = min(start, finish) - CARD_W / 2 - SHADOW_MARGIN - 9
                right = max(start, finish) + CARD_W / 2 + SHADOW_MARGIN + 9
                top = min(self.rope_y(start), self.rope_y(finish)) - 13
                bottom = max(self.rope_y(start), self.rope_y(finish)) + CARD_H + 68
                swept = QRectF(left, top, right - left, bottom - top)
                self.transition_mask |= QRegion(swept.toRect()).intersected(viewport)
        else:
            self.from_centers = {}
            self.to_centers = {}
            self.transition_mask = QRegion()
            self._random_angles()
        if self.isVisible():
            if old != self.images:
                # Refresh the whole layered backing store before exposing a new
                # window region; otherwise Windows can show pixels from a prior
                # card position for a frame at the edge of the expanded mask.
                self.clearMask()
                self.repaint()
            self.update_mask()
        self.update()

    def _load_preview(self, name: str) -> QPixmap:
        return QPixmap(str(self.root / name)).scaled(CARD_W - 14, CARD_H - 14,
                                                      Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def refresh_image(self, name: str):
        if name in self.images:
            self.pixmaps[name] = self._load_preview(name)
            self.update()

    def navigate(self, direction: int):
        remaining = self.max_offset() - self.offset if direction > 0 else self.offset
        if remaining <= 0:
            return
        old_offset = self.offset
        self.offset += direction * min(2, remaining)
        self.from_centers = {name: self.center_for(i, old_offset, len(self.images))
                             for i, name in enumerate(self.images)}
        self.to_centers = {name: self.center_for(i, self.offset, len(self.images))
                           for i, name in enumerate(self.images)}
        self.move_started = time.monotonic()
        self.settle_started = self.move_started + MOVE_TIME
        viewport = QRegion(self._viewport().toRect())
        self.transition_mask = self.mask()
        for name in self.images:
            start = self.from_centers[name]
            finish = self.to_centers[name]
            left = min(start, finish) - CARD_W / 2 - SHADOW_MARGIN - 9
            right = max(start, finish) + CARD_W / 2 + SHADOW_MARGIN + 9
            top = min(self.rope_y(start), self.rope_y(finish)) - 13
            bottom = max(self.rope_y(start), self.rope_y(finish)) + CARD_H + 68
            swept = QRectF(left, top, right - left, bottom - top)
            self.transition_mask |= QRegion(swept.toRect()).intersected(viewport)
        self._random_angles()
        self.note_action()
        if self.isVisible():
            self.update_mask()
            self.repaint()
        else:
            self.update_mask()
        self.update()

    def note_action(self):
        self.last_action = time.monotonic()

    def show_copy_feedback(self, name: str):
        if name not in self.images:
            return
        self.copy_feedback_name = name
        self.copy_feedback_started = time.monotonic()
        self.update()

    def show_animated(self):
        if self.isVisible():
            if self.phase == "retract":
                self._start_drop(from_current=True)
            self.note_action()
            return
        self.place()
        if self.enabled:
            self.vertical_shift = -12.0
            self.sag_fraction = 0.0
            self.rope_opacity = 1.0
            self.cards_opacity = 0.0
            self._start_drop()
        else:
            self.phase = "steady"
            self.vertical_shift = 0.0
            self.sag_fraction = 1.0
            self.rope_opacity = 1.0
            self.cards_opacity = 1.0
        self.note_action()
        self.update_mask()
        self.show()
        self.raise_()

    def restore_topmost(self):
        """Restore the overlay's native z-order without activating it."""
        if not self.isVisible() or sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        # HWND_TOPMOST; preserve position, size, focus, and owner z-order.
        user32.SetWindowPos(int(self.winId()), -1, 0, 0, 0, 0,
                            0x0001 | 0x0002 | 0x0010 | 0x0200)

    def _start_drop(self, from_current: bool = False):
        if not from_current:
            self._random_angles()
        self.single_card_wobble = len(self.images) == 1
        self.phase = "drop"
        self.phase_started = time.monotonic()
        self.phase_start_shift = self.vertical_shift
        self.phase_start_sag = self.sag_fraction
        self.phase_start_rope_opacity = self.rope_opacity
        self.cards_opacity = 0.0

    def hide_animated(self):
        if self.isVisible() and self.phase != "retract":
            self.phase = "retract"
            self.phase_started = time.monotonic()
            self.phase_start_shift = self.vertical_shift
            self.phase_start_sag = self.sag_fraction
            self.phase_start_rope_opacity = self.rope_opacity
            self.phase_start_cards_opacity = self.cards_opacity

    def advance(self):
        now = time.monotonic()
        active = False
        if self.copy_feedback_name is not None:
            if now - self.copy_feedback_started < COPY_FEEDBACK_TIME:
                active = True
            else:
                self.copy_feedback_name = None
                active = True
        target = 1.0 if self.hovered_control == "clear" else 0.0
        step = min(1.0, (now - self.cat_hover_updated) / 0.24)
        self.cat_hover_updated = now
        if target != self.cat_hover_progress:
            previous = self.cat_hover_progress
            self.cat_hover_progress = (min(target, previous + step) if target > previous
                                       else max(target, previous - step))
            active = active or self.cat_hover_progress != previous
        if (self.isVisible() and self.enabled and self.cards_opacity > 0
                and (self.hovered is not None or self.hovered_control in ("clear", "exit"))):
            self.last_action = now
        if self.phase == "drop":
            fraction = min(1.0, (now - self.phase_started) / DROP_TIME)
            smooth = fraction * fraction * (3 - 2 * fraction)
            self.vertical_shift = self.phase_start_shift * (1 - smooth)
            self.sag_fraction = self.phase_start_sag + (1 - self.phase_start_sag) * smooth
            self.rope_opacity = self.phase_start_rope_opacity + (1 - self.phase_start_rope_opacity) * smooth
            active = True
            if fraction >= 1.0:
                self.phase = "reveal"
                self.phase_started = now
                self.vertical_shift = 0.0
                self.sag_fraction = 1.0
                self.rope_opacity = 1.0
                self.cards_opacity = 0.0
                if self.single_card_wobble:
                    self.settle_started = now
        elif self.phase == "reveal":
            fraction = min(1.0, (now - self.phase_started) / CARD_FADE_TIME)
            self.cards_opacity = fraction * fraction * (3 - 2 * fraction)
            active = True
            if fraction >= 1.0:
                self.phase = "steady"
                self.cards_opacity = 1.0
                if not self.single_card_wobble:
                    self.settle_started = now
        elif self.phase == "retract":
            fraction = min(1.0, (now - self.phase_started) / RETRACT_TIME)
            smooth = fraction * fraction * (3 - 2 * fraction)
            self.vertical_shift = self.phase_start_shift + (-12 - self.phase_start_shift) * smooth
            self.sag_fraction = self.phase_start_sag * (1 - smooth)
            self.rope_opacity = self.phase_start_rope_opacity * (1 - smooth)
            self.cards_opacity = self.phase_start_cards_opacity * (1 - smooth)
            active = True
            if fraction >= 1.0:
                self.phase = "steady"
                self.hovered = None
                self.hide()
        if self.isVisible() and self.enabled and self.phase == "steady" and now - self.last_action >= IDLE_TIME:
            self.hide_animated()
            active = True
        if now - self.move_started < MOVE_TIME or now - self.settle_started < SETTLE_TIME:
            active = True
        if active and self.isVisible():
            self.update_mask()
            self.update()

    def rope_y(self, x: float) -> float:
        return 44 + self.vertical_shift + 20 * self.sag_fraction * math.sin(
            math.pi * max(0, min(1, x / max(1, self.width()))))

    def _center(self, name: str, index: int) -> float:
        destination = self.center_for(index, self.offset, len(self.images))
        elapsed = time.monotonic() - self.move_started
        if elapsed >= MOVE_TIME or name not in self.to_centers:
            return destination
        start = self.from_centers.get(name, self.to_centers[name] - 190)
        t = max(0.0, elapsed / MOVE_TIME)
        smooth = t * t * (3 - 2 * t)
        return start + (self.to_centers[name] - start) * smooth

    def _angle(self, name: str) -> float:
        target = self.angles.get(name, 0)
        if target == 0:
            elapsed = time.monotonic() - self.settle_started
            if (self.single_card_wobble and len(self.images) == 1
                    and self.images[0] == name and 0 <= elapsed < SETTLE_TIME):
                fade = (1 - elapsed / SETTLE_TIME) ** 2
                return 1.6 * fade * math.sin(18 * elapsed)
            return 0.0
        elapsed = time.monotonic() - self.settle_started
        if elapsed < 0 or elapsed >= SETTLE_TIME:
            return target
        amplitude = min(0.7, abs(target) * 0.5, 3.0 - abs(target))
        wobble = amplitude * math.exp(-4 * elapsed) * math.sin(14 * elapsed)
        return target + wobble

    def _card_rect(self, name: str, index: int) -> QRectF:
        cx = self._center(name, index)
        return QRectF(cx - CARD_W / 2, self.rope_y(cx) + 30, CARD_W, CARD_H)

    def _viewport(self) -> QRectF:
        slots = self.slot_centers(len(self.images))
        if not slots:
            current = QRectF()
        else:
            current = QRectF(slots[0] - CARD_W / 2 - SHADOW_MARGIN, 0,
                             slots[-1] - slots[0] + CARD_W + 2 * SHADOW_MARGIN,
                             self.height())
        if (time.monotonic() - self.move_started < MOVE_TIME
                and self.previous_image_count > len(self.images)):
            old_slots = self.slot_centers(self.previous_image_count)
            if old_slots:
                previous = QRectF(old_slots[0] - CARD_W / 2 - SHADOW_MARGIN, 0,
                                  old_slots[-1] - old_slots[0] + CARD_W + 2 * SHADOW_MARGIN,
                                  self.height())
                return current.united(previous) if not current.isEmpty() else previous
        return current

    def _card_clip(self) -> QRectF:
        viewport = self._viewport()
        if self.max_offset() == 0:
            return viewport
        slots = self.slot_centers(len(self.images))
        left = slots[0] - CARD_W / 2 - CARD_CLIP_OVERHANG
        right = slots[-1] + CARD_W / 2 + CARD_CLIP_OVERHANG
        return viewport.intersected(QRectF(left, 0, right - left, self.height()))

    def update_mask(self):
        if not self.enabled:
            self.setMask(QRegion(QRect(int(self.width() / 2 - 120), 74, 240, 56)))
            return
        region = QRegion()
        for x in range(0, self.width(), 12):
            region |= QRegion(QRect(x, int(self.rope_y(x)) - 6, 13, 13))
        card_clip = QRegion(self._card_clip().toRect())
        if self.cards_opacity > 0.05:
            for i, name in enumerate(self.images):
                rect = self._card_rect(name, i).adjusted(
                    -SHADOW_MARGIN, -35, SHADOW_MARGIN, SHADOW_MARGIN)
                region |= QRegion(rect.toRect()).intersected(card_clip)
        if time.monotonic() - self.move_started < MOVE_TIME:
            region |= self.transition_mask.intersected(card_clip)
        if self.cards_opacity > 0.05:
            for action, rect in self._buttons().items():
                if action in ("left", "right"):
                    region |= QRegion(rect.adjusted(
                        -ARROW_MASK_MARGIN, -ARROW_MASK_MARGIN,
                        ARROW_MASK_MARGIN, ARROW_MASK_MARGIN).toRect(), QRegion.Ellipse)
                else:
                    region |= QRegion(rect.adjusted(-3, -3, 3, 3).toRect())
            if self.cat_hover_progress > 0.05:
                region |= QRegion(self._cat_dialogue_rect().adjusted(-4, -4, 4, 6).toRect())
            if self.hovered_control == "exit":
                region |= QRegion(self._exit_dialogue_rect().adjusted(-4, -2, 4, 4).toRect())
        if region != self.mask():
            self.setMask(region)

    def _buttons(self) -> dict[str, QRectF]:
        mid = self.width() / 2
        up_top = min(26 + self.vertical_shift,
                     self.rope_y(mid) - CONTROL_SIZE - 7)
        buttons = {"up": QRectF(mid - CONTROL_SIZE / 2, up_top,
                                CONTROL_SIZE, CONTROL_SIZE),
                   "exit": QRectF(mid - CONTROL_SIZE / 2 - CONTROL_SIZE - 14,
                                  up_top, CONTROL_SIZE, CONTROL_SIZE)}
        cat_left = mid + 38
        cat_top = min(2 + self.vertical_shift,
                      self.rope_y(cat_left + CAT_SIZE / 2) - CAT_SIZE - 7)
        buttons["clear"] = QRectF(cat_left, cat_top, CAT_SIZE, CAT_SIZE)
        slots = self.slot_centers(len(self.images))
        left_edge = slots[0] - CARD_W / 2 if slots else mid
        right_edge = slots[-1] + CARD_W / 2 if slots else mid
        if self.offset > 0:
            buttons["left"] = QRectF(left_edge - 20 - CONTROL_SIZE,
                                     133 + self.vertical_shift, CONTROL_SIZE, CONTROL_SIZE)
        if self.offset < self.max_offset():
            buttons["right"] = QRectF(right_edge + 20,
                                      133 + self.vertical_shift, CONTROL_SIZE, CONTROL_SIZE)
        return buttons

    def _cat_dialogue_rect(self) -> QRectF:
        cat = self._buttons().get("clear")
        if cat is None:
            return QRectF()
        message = self._cat_dialogue_text()
        width = QFontMetrics(self._cat_dialogue_font()).horizontalAdvance(message) + 22
        right_x = cat.right() + 8
        left = right_x if right_x + width <= self.width() - 8 else cat.left() - width - 10
        return QRectF(max(8, left), max(2, cat.top() + 6), width, 42)

    def _exit_dialogue_rect(self) -> QRectF:
        button = self._buttons()["exit"]
        width = QFontMetrics(self._cat_dialogue_font()).horizontalAdvance("退出应用") + 22
        return QRectF(button.center().x() - width / 2, 0, width, 24)

    def _cat_dialogue_text(self) -> str:
        if not self.images:
            return "请通过截图或复制将图片挂上晾衣绳"
        return f"清空晾衣绳上的图片（共{len(self.images)}张）"

    def _copy_feedback_rect(self) -> QRectF:
        name = self.copy_feedback_name
        if name not in self.images:
            return QRectF()
        card = self._card_rect(name, self.images.index(name))
        text_width = QFontMetrics(self._cat_dialogue_font()).horizontalAdvance("已复制")
        width = text_width + 22
        return QRectF(card.center().x() - width / 2, card.bottom() - 52, width, 42)

    @staticmethod
    def _cat_dialogue_font() -> QFont:
        font = QFont("Microsoft YaHei")
        font.setPixelSize(17)
        font.setWeight(QFont.Medium)
        return font

    def _hit(self, pos: QPointF) -> tuple[str, str | None] | None:
        if not self.enabled:
            rect = QRectF(self.width() / 2 - 116, 78, 232, 48)
            return ("toggle", None) if rect.contains(pos) else None
        if self.cards_opacity <= 0.05 or self.phase == "retract":
            return None
        for action, rect in self._buttons().items():
            if rect.contains(pos):
                return action, None
        for index, name in reversed(list(enumerate(self.images))):
            rect = self._card_rect(name, index)
            if not self._card_clip().intersects(rect):
                continue
            if rect.contains(pos):
                if self.hovered == name and QRectF(rect.right() - 26, rect.top() + 5, 22, 22).contains(pos):
                    return "remove", name
                return "card", name
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if not self.enabled:
            self._draw_disabled(painter)
            return
        painter.setOpacity(self.rope_opacity)
        self._draw_rope(painter)
        if self.cards_opacity <= 0:
            return
        painter.save()
        painter.setOpacity(self.cards_opacity)
        card_clip = self._card_clip()
        painter.setClipRect(card_clip)
        for i, name in enumerate(self.images):
            rect = self._card_rect(name, i)
            if not card_clip.intersects(rect):
                continue
            painter.save()
            if name in self.to_centers and name not in self.from_centers:
                t = min(1.0, max(0.0, (time.monotonic() - self.move_started) / MOVE_TIME))
                painter.setOpacity(self.cards_opacity * t)
            self._draw_card(painter, name, rect)
            painter.restore()
        painter.restore()
        painter.setOpacity(self.cards_opacity)
        self._draw_controls(painter)
        if self.copy_feedback_name is not None:
            remaining = COPY_FEEDBACK_TIME - (time.monotonic() - self.copy_feedback_started)
            if remaining > 0:
                fade = min(1.0, remaining / COPY_FEEDBACK_FADE)
                self._draw_dialogue(painter, self._copy_feedback_rect(), "已复制", fade)
        if not self.images:
            painter.setPen(QColor("#758096"))
            painter.drawText(QRectF(0, 106, self.width(), 40), Qt.AlignCenter,
                             "复制图片或按 Win+Shift+S 截图")

    def _draw_rope(self, p: QPainter):
        path = QPainterPath(QPointF(0, self.rope_y(0)))
        for x in range(5, self.width() + 5, 5):
            path.lineTo(QPointF(min(x, self.width()), self.rope_y(x)))
        gradient = QLinearGradient(0, 0, self.width(), 0)
        for stop, alpha in ((0, 0), (.08, 170), (.18, 240), (.82, 240), (.92, 170), (1, 0)):
            c = QColor("#9caaba")
            c.setAlpha(alpha)
            gradient.setColorAt(stop, c)
        p.setPen(QPen(gradient, 4.3, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.save()
        p.translate(0, -1.3)
        p.setPen(QPen(QColor(246, 250, 255, 140), 1.0))
        p.drawPath(path)
        p.restore()

    @staticmethod
    @lru_cache(maxsize=1)
    def _make_card_shadow() -> QImage:
        """Cache a continuous soft shadow instead of drawing a hard offset outline."""
        width = CARD_W + 2 * SHADOW_MARGIN
        height = CARD_H + 2 * SHADOW_MARGIN
        shadow = QImage(width, height, QImage.Format_ARGB32)
        shadow.fill(Qt.transparent)
        colors = [QColor(38, 47, 69, alpha).rgba() for alpha in range(81)]
        cx = SHADOW_MARGIN + CARD_W / 2
        radius = 12.0

        def distance(x: float, y: float, down: float) -> float:
            cy = SHADOW_MARGIN + CARD_H / 2 + down
            dx = abs(x - cx) - (CARD_W / 2 - radius)
            dy = abs(y - cy) - (CARD_H / 2 - radius)
            return math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0) - radius

        for y in range(height):
            for x in range(width):
                broad = max(0.0, distance(x + .5, y + .5, 9.0))
                close = max(0.0, distance(x + .5, y + .5, 4.0))
                alpha = round(39 * math.exp(-.5 * (broad / 11) ** 2)
                              + 31 * math.exp(-.5 * (close / 4.5) ** 2))
                if alpha:
                    shadow.setPixel(x, y, colors[min(alpha, 80)])
        return shadow

    @staticmethod
    @lru_cache(maxsize=4)
    def _make_edge_card_shadow(side: str, spread: int) -> QImage:
        shadow = ClotheslineWindow._make_card_shadow().copy()
        if side == "left":
            columns = range(SHADOW_MARGIN)
        else:
            columns = range(SHADOW_MARGIN + CARD_W, shadow.width())
        for x in columns:
            outward = (SHADOW_MARGIN - x if side == "left"
                       else x - SHADOW_MARGIN - CARD_W + 1)
            remaining = max(0.0, 1.0 - outward / spread)
            fade = remaining * remaining
            for y in range(shadow.height()):
                pixel = shadow.pixel(x, y)
                alpha = round((pixel >> 24) * fade)
                shadow.setPixel(x, y, (pixel & 0x00ffffff) | (alpha << 24))
        return shadow

    def _draw_card(self, p: QPainter, name: str, rect: QRectF):
        cx = rect.center().x()
        peg_y = self.rope_y(cx)
        p.save()
        p.translate(cx, peg_y + 22)
        p.rotate(self._angle(name))
        p.translate(-cx, -(peg_y + 22))
        shadow_pos = QPointF(rect.left() - SHADOW_MARGIN,
                             rect.top() - SHADOW_MARGIN)
        edge_side = None
        edge_strength = 0.0
        edge_spread = EDGE_SHADOW_SPREAD
        if len(self.images) >= VISIBLE:
            card_clip = self._card_clip()
            left_distance = rect.left() - card_clip.left()
            right_distance = card_clip.right() - rect.right()
            if min(left_distance, right_distance) <= SHADOW_MARGIN:
                edge_side = "left" if left_distance < right_distance else "right"
                distance = min(left_distance, right_distance)
                if self.max_offset() == 0:
                    edge_spread = SHADOW_MARGIN - 6
                    edge_strength = 1.0
                else:
                    edge_strength = min(1.0, max(0.0, (SHADOW_MARGIN - distance)
                                                 / (SHADOW_MARGIN - CARD_CLIP_OVERHANG)))
        if edge_side is None or edge_strength == 0:
            p.drawImage(shadow_pos, self.card_shadow)
        else:
            original_opacity = p.opacity()
            if edge_strength < 1:
                p.setOpacity(original_opacity * (1 - edge_strength))
                p.drawImage(shadow_pos, self.card_shadow)
            p.setOpacity(original_opacity * edge_strength)
            p.drawImage(shadow_pos, self._make_edge_card_shadow(edge_side, edge_spread))
            p.setOpacity(original_opacity)
        frame = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        frame.setColorAt(0, QColor("#ffffff"))
        frame.setColorAt(.55, QColor("#fbfcff"))
        frame.setColorAt(1, QColor("#edf1f8"))
        p.setPen(QPen(QColor(112, 126, 151, 75), 1))
        p.setBrush(frame)
        p.drawRoundedRect(rect, 12, 12)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 205), 1))
        p.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 10.5, 10.5)
        image = self.pixmaps.get(name, QPixmap())
        if not image.isNull():
            target = QRectF(rect.left() + 7, rect.top() + 7, rect.width() - 14, rect.height() - 14)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#f1f3f8"))
            p.drawRoundedRect(target, 5, 5)
            scaled = image.scaled(target.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(target, 5, 5)
            # Preserve the outer viewport clip while rounding the image.
            # ReplaceClip would let sliding pixels bleed under the translucent
            # navigation buttons, whose regions are included in the window mask.
            p.setClipPath(clip, Qt.IntersectClip)
            p.drawPixmap(QPointF(target.center().x() - scaled.width() / 2,
                                 target.center().y() - scaled.height() / 2), scaled)
            p.restore()
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(72, 87, 114, 38), 1))
            p.drawRoundedRect(target, 5, 5)
        if self.hovered == name:
            close = QRectF(rect.right() - 26, rect.top() + 5, 22, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(250, 251, 255, 235))
            p.drawEllipse(close)
            p.setPen(QPen(QColor("#4b5363"), 1.5))
            p.drawLine(close.left() + 7, close.top() + 7, close.right() - 7, close.bottom() - 7)
            p.drawLine(close.right() - 7, close.top() + 7, close.left() + 7, close.bottom() - 7)
        p.restore()
        self._draw_clip(p, cx, peg_y)

    def _draw_clip(self, p: QPainter, cx: float, top: float):
        p.save()
        p.translate(cx, top)
        metal = QLinearGradient(-9, 0, 9, 0)
        for at, color in ((0, "#8996a5"), (.2, "#ffffff"), (.5, "#cbd3dd"),
                          (.8, "#fafcff"), (1, "#8492a1")):
            metal.setColorAt(at, QColor(color))
        p.setPen(QPen(QColor("#8996a5"), .8))
        p.setBrush(metal)
        p.drawRoundedRect(QRectF(-9, 0, 18, 32), 4, 4)
        p.drawRoundedRect(QRectF(-7, -5, 14, 9), 3, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#202936"))
        p.drawRoundedRect(QRectF(-1.5, 9, 3, 19), 1, 1)
        p.restore()

    def _draw_controls(self, p: QPainter):
        for action, rect in self._buttons().items():
            if action == "clear":
                self._draw_cat(p, rect)
                continue
            p.setPen(QPen(QColor(235, 239, 247, 215), 1))
            p.setBrush(QColor(251, 252, 255, 210))
            p.drawEllipse(rect)
            p.setPen(QPen(QColor("#45516d"), 2.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            mid = rect.center()
            if action == "up":
                p.drawLine(QPointF(mid.x() - 8, mid.y() + 4), QPointF(mid.x(), mid.y() - 5))
                p.drawLine(QPointF(mid.x(), mid.y() - 5), QPointF(mid.x() + 8, mid.y() + 4))
            elif action == "exit":
                p.drawLine(QPointF(mid.x() - 6, mid.y() - 6), QPointF(mid.x() + 6, mid.y() + 6))
                p.drawLine(QPointF(mid.x() + 6, mid.y() - 6), QPointF(mid.x() - 6, mid.y() + 6))
            else:
                sign = -1 if action == "left" else 1
                p.drawLine(QPointF(mid.x() - sign * 4, mid.y() - 8), QPointF(mid.x() + sign * 5, mid.y()))
                p.drawLine(QPointF(mid.x() + sign * 5, mid.y()), QPointF(mid.x() - sign * 4, mid.y() + 8))
        if self.cat_hover_progress > 0.02:
            self._draw_cat_dialogue(p)
        if self.hovered_control == "exit":
            self._draw_dialogue(p, self._exit_dialogue_rect(), "退出应用", 1.0)

    def _draw_cat(self, p: QPainter, rect: QRectF):
        p.save()
        p.translate(rect.topLeft())
        p.scale(rect.width() / 100, rect.height() / 100)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(33, 42, 60, 34))
        p.drawEllipse(QRectF(18, 91, 66, 7))

        outline = QPen(QColor("#242831"), 4.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        tail = QPainterPath(QPointF(37, 72))
        tail.cubicTo(15, 72, 14, 95, 30, 96)
        tail.cubicTo(40, 99, 46, 91, 41, 84)
        p.setPen(outline)
        p.setBrush(QColor("#d8dce3"))
        p.drawPath(tail)

        body = QPainterPath(QPointF(37, 58))
        body.cubicTo(27, 63, 27, 74, 27, 84)
        body.cubicTo(27, 94, 39, 98, 46, 91)
        body.cubicTo(50, 100, 58, 100, 62, 91)
        body.cubicTo(70, 99, 78, 92, 77, 81)
        body.cubicTo(77, 70, 73, 62, 64, 58)
        body.closeSubpath()
        body_fill = QLinearGradient(48, 58, 55, 97)
        body_fill.setColorAt(0, QColor("#ffffff"))
        body_fill.setColorAt(1, QColor("#e3e7ee"))
        p.setBrush(body_fill)
        p.drawPath(body)

        look = self.cat_hover_progress
        look = look * look * (3 - 2 * look)
        p.translate(50 + 4 * look, 69 - 3 * look)
        p.rotate(11 * look)
        p.translate(-50, -69)

        for right in (False, True):
            p.save()
            if right:
                p.translate(100, 0)
                p.scale(-1, 1)
            ear = QPainterPath(QPointF(19, 30))
            ear.cubicTo(22, 16, 29, 2, 36, 3)
            ear.cubicTo(43, 4, 47, 16, 47, 29)
            ear.closeSubpath()
            p.setPen(outline)
            p.setBrush(QColor("#e3e6eb"))
            p.drawPath(ear)
            inner = QPainterPath(QPointF(26, 26))
            inner.cubicTo(28, 17, 32, 10, 35, 10)
            inner.cubicTo(39, 12, 41, 19, 42, 27)
            inner.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#f7b8d0"))
            p.drawPath(inner)
            p.restore()

        head = QPainterPath(QPointF(50, 22))
        head.cubicTo(27, 20, 12, 30, 11, 49)
        head.cubicTo(10, 65, 20, 74, 35, 75)
        head.cubicTo(44, 78, 56, 78, 65, 75)
        head.cubicTo(81, 74, 91, 65, 89, 48)
        head.cubicTo(87, 31, 72, 21, 50, 22)
        face_fill = QLinearGradient(49, 20, 52, 77)
        face_fill.setColorAt(0, QColor("#e7e9ed"))
        face_fill.setColorAt(.65, QColor("#f3f4f7"))
        face_fill.setColorAt(1, QColor("#ffffff"))
        p.setPen(outline)
        p.setBrush(face_fill)
        p.drawPath(head)

        for x in (21, 54):
            p.setPen(QPen(QColor("#16191e"), 2))
            p.setBrush(QColor("#15171b"))
            p.drawEllipse(QRectF(x, 38, 26, 29))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#edf089"))
            p.drawEllipse(QRectF(x + 3, 43, 20, 21))
            p.setBrush(QColor("#111316"))
            p.drawEllipse(QRectF(x + 3 + 2 * look, 39 - look, 20, 21))
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QRectF(x + 6 + 2 * look, 41 - look, 6, 6))
            p.drawEllipse(QRectF(x + 18 + 2 * look, 56 - look, 2, 2))

        p.restore()

    def _draw_cat_dialogue(self, p: QPainter):
        self._draw_dialogue(p, self._cat_dialogue_rect(),
                            self._cat_dialogue_text(), self.cat_hover_progress)

    def _draw_dialogue(self, p: QPainter, rect: QRectF, message: str, opacity: float):
        p.save()
        p.setOpacity(p.opacity() * opacity)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(19, 38, 71, 22))
        radius = min(16, rect.height() / 2)
        p.drawRoundedRect(rect.translated(0, 2), radius, radius)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(234, 243, 253))
        p.drawRoundedRect(rect, radius, radius)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._cat_dialogue_font())
        p.setPen(QColor(19, 38, 71))
        p.drawText(rect.adjusted(11, 0, -11, 0), Qt.AlignVCenter | Qt.AlignLeft, message)
        p.restore()

    def _draw_disabled(self, p: QPainter):
        rect = QRectF(self.width() / 2 - 116, 78, 232, 48)
        p.setPen(QPen(QColor("#cbd4e8"), 1))
        p.setBrush(QColor(246, 249, 255, 240))
        p.drawRoundedRect(rect, 16, 16)
        p.setPen(QColor("#33486f"))
        p.drawText(rect, Qt.AlignCenter, "开启 Clipline 功能")

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        control = hit[0] if hit and hit[0] in ("clear", "exit") else None
        if control != self.hovered_control:
            self.hovered_control = control
            self.update_mask()
            self.update()
        hovered = hit[1] if hit and hit[0] in ("card", "remove") else None
        if hovered != self.hovered:
            self.hovered = hovered
            self.update()
        if hovered is not None or control in ("clear", "exit"):
            self.note_action()
        if self.pressed and self.pressed[0] == "card" and event.buttons() & Qt.LeftButton:
            if (event.position().toPoint() - self.press_pos).manhattanLength() > 10 and not self.dragging:
                self.long_press.stop()
                self.dragging = True
                name = self.pressed[1]
                if name:
                    drag = QDrag(self)
                    mime = QMimeData()
                    mime.setUrls([QUrl.fromLocalFile(str(self.root / name))])
                    drag.setMimeData(mime)
                    drag.setPixmap(self.pixmaps.get(name, QPixmap()))
                    drag.exec(Qt.CopyAction)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered = None
        self.hovered_control = None
        self.update_mask()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pending_edit = None
            self.pressed = self._hit(event.position())
            self.press_pos = event.position().toPoint()
            self.dragging = False
            self.long_pressed = False
            if self.pressed and self.pressed[0] == "card":
                self.long_press.start(650)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.long_press.stop()
        pending_edit = self.pending_edit if event.button() == Qt.LeftButton else None
        self.pending_edit = None
        if event.button() == Qt.LeftButton and self.pressed:
            action, name = self.pressed
            hit = self._hit(event.position())
            if hit == self.pressed and not self.dragging and not self.long_pressed:
                if action == "toggle":
                    self.toggle_requested.emit()
                elif action == "up":
                    self.hide_animated()
                elif action == "exit":
                    self.quit_requested.emit()
                elif action == "clear" and self.images:
                    self.note_action()
                    self.hovered_control = None
                    self.clear_requested.emit()
                elif action == "left":
                    self.navigate(-1)
                elif action == "right":
                    self.navigate(1)
                elif action == "remove" and name:
                    self.note_action()
                    self.removed.emit(name)
                elif action == "card" and name:
                    self.note_action()
                    self.copied.emit(name)
        self.pressed = None
        super().mouseReleaseEvent(event)
        if pending_edit:
            QTimer.singleShot(0, lambda name=pending_edit: self.edit_requested.emit(name))

    def mouseDoubleClickEvent(self, event):
        hit = self._hit(event.position())
        if hit and hit[0] == "card" and hit[1]:
            self.long_press.stop()
            self.pressed = None
            self.pending_edit = None
            self.dragging = False
            self.long_pressed = True
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _long_press(self):
        if self.pressed and self.pressed[0] == "card" and self.pressed[1]:
            name = self.pressed[1]
            self.long_pressed = True
            self.pending_edit = name
            self.pressed = None
            self.note_action()
