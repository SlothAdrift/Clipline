import ctypes
import os
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from shiboken6 import VoidPtr

from clothesline import ClotheslineApp, GlobalHotkeyFilter, ImageStore, MAX_IMAGES
from line_canvas import (CARD_FADE_TIME, COPY_FEEDBACK_TIME, DROP_TIME,
                         MOVE_TIME, RETRACT_TIME, ClotheslineWindow)


class ClotheslineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def finish_entrance(window):
        window.phase_started = time.monotonic() - DROP_TIME
        window.advance()
        window.phase_started = time.monotonic() - CARD_FADE_TIME
        window.advance()

    def test_ten_image_limit_and_originals(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            original = root / "original.png"
            image = QImage(8, 8, QImage.Format_ARGB32)
            image.fill("red")
            image.save(str(original))
            store = ImageStore(root / "managed")
            store.enabled = True
            first = store.add(image)
            for _ in range(MAX_IMAGES):
                store.add(image)
            self.assertEqual(len(store.images), MAX_IMAGES)
            self.assertFalse(first.exists())
            self.assertTrue(original.exists())
            reloaded = ImageStore(root / "managed")
            self.assertEqual(len(reloaded.images), MAX_IMAGES)
            reloaded.remove(reloaded.images[0])
            self.assertTrue(original.exists())

    def test_switch_controls_clipboard_capture(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = ImageStore(Path(directory))
            controller = ClotheslineApp(self.app, store)
            controller.show()
            controller.tick()
            self.assertTrue(controller.window.isVisible(), "关闭状态下启动也必须显示开关")
            image = QImage(9, 9, QImage.Format_ARGB32)
            image.fill("blue")
            self.app.clipboard().setImage(image)
            self.app.processEvents()
            self.assertEqual(store.images, [])
            controller.toggle()
            self.assertEqual(controller.window.phase, "drop")
            self.app.clipboard().setImage(image)
            self.app.processEvents()
            self.assertEqual(len(store.images), 1)
            self.app.clipboard().setImage(image)
            self.app.processEvents()
            self.assertEqual(len(store.images), 1, "连续剪贴板通知不能重复挂同一张图片")
            controller.copy_image(store.images[0])
            self.app.processEvents()
            controller.receive_clipboard()
            self.assertEqual(len(store.images), 1)
            controller.timer.stop()
            controller.tray.hide()
            controller.window.close()

    def test_same_image_can_be_copied_again_after_half_second(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = ImageStore(Path(directory))
            store.enabled = True
            controller = ClotheslineApp(self.app, store)
            image = QImage(9, 9, QImage.Format_ARGB32)
            image.fill("blue")
            controller.add_clipboard_image(image)
            self.assertEqual(len(store.images), 1)
            controller.recent_image_digests = {
                digest: stamp - 0.3 for digest, stamp in controller.recent_image_digests.items()
            }
            controller.add_clipboard_image(image)
            self.assertEqual(len(store.images), 1)
            controller.recent_image_digests = {
                digest: stamp - 0.6 for digest, stamp in controller.recent_image_digests.items()
            }
            controller.add_clipboard_image(image)
            self.assertEqual(len(store.images), 2)
            controller.timer.stop()
            controller.window.frame_timer.stop()
            controller.tray.hide()
            controller.window.close()

    def test_copy_feedback_appears_on_copied_card_and_expires(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = ImageStore(Path(directory))
            store.enabled = True
            image = QImage(16, 16, QImage.Format_ARGB32)
            image.fill("blue")
            store.add(image)
            controller = ClotheslineApp(self.app, store)
            window = controller.window
            controller.show()
            self.finish_entrance(window)
            window.frame_timer.stop()
            name = store.images[0]
            card = window._card_rect(name, 0)
            QTest.mouseClick(window, Qt.LeftButton, pos=card.center().toPoint())
            self.assertEqual(window.copy_feedback_name, name)
            self.assertFalse(self.app.clipboard().image().isNull())
            bubble = window._copy_feedback_rect()
            self.assertTrue(card.contains(bubble))
            self.assertAlmostEqual(bubble.center().x(), card.center().x())
            self.assertAlmostEqual(bubble.bottom(), card.bottom() - 10)
            window.repaint()
            bubble_pixel = window.grab().toImage().pixelColor(
                int(bubble.left() + 12), int(bubble.top() + 8))
            self.assertGreater(bubble_pixel.red(), 200)
            self.assertGreater(bubble_pixel.green(), 220)
            window.copy_feedback_started = time.monotonic() - COPY_FEEDBACK_TIME
            window.advance()
            self.assertIsNone(window.copy_feedback_name)
            controller.timer.stop()
            controller.tray.hide()
            window.close()

    def test_copied_image_files_from_explorer_are_hung(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source_a = root / "桌面图片.png"
            source_b = root / "second.jpg"
            other = root / "note.txt"
            for path, color in ((source_a, "red"), (source_b, "green")):
                image = QImage(16, 16, QImage.Format_ARGB32)
                image.fill(color)
                self.assertTrue(image.save(str(path)))
            other.write_text("not an image", encoding="utf-8")
            store = ImageStore(root / "managed")
            store.enabled = True
            controller = ClotheslineApp(self.app, store)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))
                          for path in (source_a, other, source_b)])
            self.app.clipboard().setMimeData(mime)
            self.app.processEvents()
            self.assertEqual(len(store.images), 2)
            # Some Windows clipboard providers emit another notification for the
            # same batch. Both files must be recognized as already captured.
            controller.receive_clipboard()
            self.assertEqual(len(store.images), 2)
            self.assertTrue(source_a.exists())
            self.assertTrue(source_b.exists())
            controller.timer.stop()
            controller.window.frame_timer.stop()
            controller.tray.hide()
            controller.window.close()

    def test_five_slots_navigation_and_new_image_return(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            image = QImage(8, 8, QImage.Format_ARGB32)
            image.fill("green")
            names = []
            for i in range(10):
                name = f"{i}.png"
                image.save(str(root / name))
                names.append(name)
            window = ClotheslineWindow()
            window.set_enabled(True)
            window.set_images(root, names)
            self.assertEqual(window.max_offset(), 5)
            self.assertEqual(len(window.slot_centers(10)), 5)
            window.navigate(1)
            self.assertEqual(window.offset, 2)
            buttons = window._buttons()
            slots = window.slot_centers(len(window.images))
            self.assertAlmostEqual((slots[0] - 176 / 2) - buttons["left"].right(), 20)
            self.assertAlmostEqual(buttons["right"].left() - (slots[-1] + 176 / 2), 20)
            self.assertEqual(buttons["up"].top(), 26)
            self.assertEqual(buttons["clear"].top(), 2)
            self.assertEqual(buttons["up"].size().width(), 30)
            self.assertEqual(buttons["up"].size().height(), 30)
            self.assertEqual(buttons["exit"].size(), buttons["up"].size())
            self.assertAlmostEqual(buttons["up"].left() - buttons["exit"].right(), 14)
            self.assertEqual(buttons["left"].size(), buttons["up"].size())
            self.assertEqual(buttons["right"].size(), buttons["up"].size())
            self.assertEqual(buttons["clear"].size().width(), 54)
            self.assertEqual(buttons["clear"].size().height(), 54)
            self.assertAlmostEqual(buttons["up"].center().x(), window.width() / 2)
            self.assertGreater(window.rope_y(window.width() / 2) - buttons["up"].bottom(), 5)
            self.assertGreater(window.rope_y(buttons["clear"].center().x()) - buttons["clear"].bottom(), 5)
            window.navigate(1)
            self.assertEqual(window.offset, 4)
            window.navigate(1)
            self.assertEqual(window.offset, 5)
            self.assertNotIn("right", window._buttons())
            window.set_images(root, ["new.png", *names[:9]], added=True)
            self.assertEqual(window.offset, 0)
            window.set_images(root, names[:2])
            self.assertAlmostEqual(sum(window.slot_centers(2)) / 2, window.width() / 2)
            self.assertGreater(window.angles[names[0]], 0)
            self.assertLess(window.angles[names[1]], 0)
            for count in (1, 3, 5):
                window.set_images(root, names[:count])
                self.assertEqual(window.angles[names[count // 2]], 0.0)
            window.frame_timer.stop()
            window.close()

    def test_exit_button_tooltip_and_quit_signal(self):
        window = ClotheslineWindow()
        window.set_enabled(True)
        window.show()
        window.frame_timer.stop()
        exit_button = window._buttons()["exit"]
        up_button = window._buttons()["up"]
        self.assertEqual(exit_button.size(), up_button.size())
        self.assertEqual(exit_button.top(), up_button.top())
        tooltip = window._exit_dialogue_rect()
        self.assertLessEqual(tooltip.bottom(), exit_button.top())
        QTest.mouseMove(window, exit_button.center().toPoint())
        self.assertEqual(window.hovered_control, "exit")
        self.assertTrue(window.mask().contains(tooltip.center().toPoint()))
        quit_spy = QSignalSpy(window.quit_requested)
        QTest.mouseClick(window, Qt.LeftButton, pos=exit_button.center().toPoint())
        self.assertEqual(quit_spy.count(), 1)
        window.close()

    def test_exit_confirmation_cancels_or_quits(self):
        controller = SimpleNamespace(window=None, app=Mock())
        with patch("clothesline.QMessageBox.question", return_value=QMessageBox.No) as question:
            ClotheslineApp.confirm_quit(controller)
            self.assertEqual(question.call_args.args[1], "退出应用")
            controller.app.quit.assert_not_called()
        with patch("clothesline.QMessageBox.question", return_value=QMessageBox.Yes):
            ClotheslineApp.confirm_quit(controller)
            controller.app.quit.assert_called_once_with()

    def test_removed_card_does_not_leave_old_pixels_behind(self):
        window = ClotheslineWindow()
        window.resize(1200, 270)
        window.set_enabled(True)
        names = [f"card-{i}.png" for i in range(5)]
        window.set_images(Path.cwd(), names)
        window.show()
        window.update_mask()
        window.frame_timer.stop()
        window.repaint()
        old_frame = window.grab().toImage()
        self.assertGreater(old_frame.pixelColor(600, 145).alpha(), 200)
        self.assertGreater(old_frame.pixelColor(1040, 145).alpha(), 200)

        window.set_images(Path.cwd(), [names[0], names[1], names[3], names[4]])
        window.move_started = time.monotonic()
        window.update_mask()
        window.repaint()
        moving_frame = window.grab().toImage()
        self.assertGreater(moving_frame.pixelColor(1100, 145).alpha(), 200)
        self.assertLess(moving_frame.pixelColor(600, 145).alpha(), 100)
        moving_mask = window.mask()
        window.move_started = time.monotonic() - MOVE_TIME / 2
        window.update_mask()
        self.assertEqual(window.mask(), moving_mask)
        window.move_started = time.monotonic() - 1
        window.settle_started = time.monotonic() - 1
        window.update_mask()
        window.repaint()
        new_frame = window.grab().toImage()
        self.assertLess(new_frame.pixelColor(600, 145).alpha(), 100)
        self.assertLess(new_frame.pixelColor(1040, 145).alpha(), 100)

        window.set_images(Path.cwd(), ["new.png", names[0], names[1], names[3], names[4]], added=True)
        self.assertLess(window._center("new.png", 0), window.to_centers["new.png"])
        window.move_started = time.monotonic()
        window.update_mask()
        window.repaint()
        self.assertLess(window.grab().toImage().pixelColor(1100, 145).alpha(), 100)
        entering_mask = window.mask()
        window.move_started = time.monotonic() - MOVE_TIME / 2
        window.update_mask()
        self.assertEqual(window.mask(), entering_mask)
        window.frame_timer.stop()
        window.close()

    def test_navigation_keeps_arrow_edges_clear_during_card_motion(self):
        window = ClotheslineWindow()
        window.resize(1200, 270)
        window.set_enabled(True)
        window.set_images(Path.cwd(), [f"card-{i}.png" for i in range(8)])
        window.show()
        window.frame_timer.stop()
        window.repaint()
        window.navigate(1)
        first_mask = window.mask()
        clip = window._card_clip()
        arrows = window._buttons()
        self.assertLess(arrows["left"].right(), clip.left())
        self.assertLess(clip.right(), arrows["right"].left())
        for action in ("left", "right"):
            arrow = arrows[action]
            self.assertTrue(first_mask.contains(arrow.center().toPoint()))
            self.assertTrue(first_mask.contains(QPoint(int(arrow.center().x()), int(arrow.top()) - 1)))
            self.assertFalse(first_mask.contains(QPoint(int(arrow.center().x()), int(arrow.top()) - 2)))
            self.assertFalse(first_mask.contains(arrow.topLeft().toPoint()))
        window.move_started = time.monotonic() - MOVE_TIME / 2
        window.update_mask()
        self.assertEqual(window.mask(), first_mask)
        window.repaint()
        frame = window.grab().toImage()
        for action in ("left", "right"):
            corner = arrows[action].topLeft().toPoint()
            self.assertLess(frame.pixelColor(corner).alpha(), 100)
        for x in (int(clip.left()) - 1, int(clip.right()) + 1):
            for y in (190, 235):
                self.assertFalse(window.mask().contains(QPoint(x, y)))
                self.assertLess(frame.pixelColor(x, y).alpha(), 100)
        for action in ("left", "right"):
            self.assertTrue(window.mask().contains(arrows[action].center().toPoint()))
        for arrow in (window._buttons()["left"], window._buttons()["right"]):
            x = int(arrow.left() - 8 if arrow.center().x() < window.width() / 2
                    else arrow.right() + 8)
            y = int(arrow.center().y())
            self.assertLess(frame.pixelColor(x, y).alpha(), 100)
        window.move_started = time.monotonic() - MOVE_TIME * .25
        window.update_mask()
        window.repaint()
        frame = window.grab().toImage()
        self.assertGreater(frame.pixelColor(int(clip.left()) + 3, 150).alpha(), 100)
        self.assertLess(frame.pixelColor(int(clip.left()) - 1, 150).alpha(), 100)
        window.move_started = time.monotonic() - MOVE_TIME * .75
        window.update_mask()
        window.repaint()
        frame = window.grab().toImage()
        self.assertGreater(frame.pixelColor(int(clip.right()) - 3, 150).alpha(), 100)
        self.assertLess(frame.pixelColor(int(clip.right()) + 1, 150).alpha(), 100)
        window.close()

    def test_outer_shadows_fade_only_with_five_visible_cards(self):
        windows = []
        try:
            for count in (4, 5, 8):
                window = ClotheslineWindow()
                windows.append(window)
                window.resize(1200, 270)
                window.set_enabled(True)
                names = [f"card-{i}.png" for i in range(count)]
                window.set_images(Path.cwd(), names)
                window.angles = {name: 0 for name in names}
                window.move_started = -100
                window.settle_started = -100
                window.show()
                window.frame_timer.stop()
                window.update_mask()
                window.repaint()
                frame = window.grab().toImage()
                first = window._card_rect(names[0], 0)
                y = int(first.center().y())
                if count == 4:
                    self.assertEqual(window._card_clip(), window._viewport())
                    self.assertGreater(frame.pixelColor(int(first.left()) - 13, y).alpha(), 0)
                elif count == 5:
                    clip = window._card_clip()
                    self.assertEqual(clip, window._viewport())
                    self.assertLess(frame.pixelColor(int(clip.left()) + 1, y).alpha(), 5)
                    self.assertGreater(frame.pixelColor(int(clip.left()) + 21, y).alpha(), 0)
                    self.assertLess(frame.pixelColor(int(clip.right()) - 2, y).alpha(), 5)
                    self.assertGreater(frame.pixelColor(int(clip.right()) - 22, y).alpha(), 0)
                else:
                    clip = window._card_clip()
                    self.assertLess(frame.pixelColor(int(clip.left()) + 1, y).alpha(), 5)
                    self.assertGreater(frame.pixelColor(int(clip.left()) + 11, y).alpha(), 0)
                    self.assertLess(frame.pixelColor(int(clip.right()) - 2, y).alpha(), 5)
                    self.assertGreater(frame.pixelColor(int(clip.right()) - 12, y).alpha(), 0)
        finally:
            for window in windows:
                window.close()

    def test_idle_hide_and_navigation_reset(self):
        window = ClotheslineWindow()
        window.set_enabled(True)
        window.set_images(Path.cwd(), [str(i) for i in range(6)])
        window.show_animated()
        self.finish_entrance(window)
        window.last_action = time.monotonic() - 9
        window.advance()
        self.assertEqual(window.phase, "steady")
        window.last_action = time.monotonic() - 11
        window.advance()
        self.assertEqual(window.phase, "retract")
        window.show_animated()
        self.finish_entrance(window)
        window.hovered = "0"
        window.last_action = time.monotonic() - 11
        window.advance()
        self.assertEqual(window.phase, "steady")
        self.assertLess(time.monotonic() - window.last_action, 1)
        window.hovered = None
        window.navigate(1)
        self.assertLess(time.monotonic() - window.last_action, 1)
        self.assertEqual(window.offset, 1)
        window.frame_timer.stop()
        window.close()

    def test_hover_reveals_remove_button(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = ImageStore(Path(directory))
            store.enabled = True
            image = QImage(20, 20, QImage.Format_ARGB32)
            image.fill("magenta")
            store.add(image)
            controller = ClotheslineApp(self.app, store)
            controller.show()
            self.finish_entrance(controller.window)
            self.app.processEvents()
            name = store.images[0]
            rect = controller.window._card_rect(name, 0)
            point = QPoint(int(rect.right() - 15), int(rect.top() + 15))
            QTest.mouseMove(controller.window, point)
            self.assertEqual(controller.window.hovered, name)
            self.assertEqual(controller.window._hit(point), ("remove", name))
            QTest.mouseClick(controller.window,  Qt.LeftButton, pos=point)
            self.assertEqual(store.images, [])
            controller.timer.stop()
            controller.window.frame_timer.stop()
            controller.tray.hide()
            controller.window.close()

    def test_double_click_does_not_open_and_long_press_edits_in_paint(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = ImageStore(Path(directory))
            store.enabled = True
            image = QImage(20, 20, QImage.Format_ARGB32)
            image.fill("yellow")
            store.add(image)
            controller = ClotheslineApp(self.app, store)
            name = store.images[0]
            controller.show()
            self.finish_entrance(controller.window)
            rect = controller.window._card_rect(name, 0)
            point = rect.center().toPoint()
            with (patch("clothesline.subprocess.Popen") as launch_paint,
                  patch("clothesline.os.startfile") as startfile):
                QTest.mouseDClick(controller.window, Qt.LeftButton, pos=point)
                QTest.mouseRelease(controller.window, Qt.LeftButton, pos=point)
                QTest.qWait(700)
                launch_paint.assert_not_called()
                startfile.assert_not_called()
                self.assertFalse(controller.window.long_press.isActive())

                QTest.mousePress(controller.window, Qt.LeftButton, pos=point)
                QTest.qWait(700)
                launch_paint.assert_not_called()
                QTest.mouseRelease(controller.window, Qt.LeftButton, pos=point)
                self.app.processEvents()
                launch_paint.assert_called_once_with(
                    ["mspaint.exe", str((store.root / name).resolve())])
                startfile.assert_not_called()
            with (patch("clothesline.subprocess.Popen", side_effect=OSError),
                  patch.object(QMessageBox, "warning") as warning):
                controller.edit_image(name)
                warning.assert_called_once()
            controller.timer.stop()
            controller.window.frame_timer.stop()
            controller.tray.hide()
            controller.window.close()

    def test_paint_foreground_keeps_rack_visible_until_editor_is_minimized(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = ImageStore(Path(directory))
            store.enabled = True
            image = QImage(20, 20, QImage.Format_ARGB32)
            image.fill("yellow")
            store.add(image)
            controller = ClotheslineApp(self.app, store)
            controller.show()
            self.finish_entrance(controller.window)
            controller.timer.stop()
            controller.window.frame_timer.stop()
            with (patch("clothesline.subprocess.Popen") as launch_paint,
                  patch("clothesline.foreground_process_id",
                        side_effect=[os.getpid(), 12345, 43210, 43210, 12345]),
                  patch("clothesline.process_name",
                        side_effect=["explorer.exe", "mspaint.exe", "mspaint.exe", "explorer.exe"]),
                  patch.object(controller.window, "restore_topmost") as restore_topmost):
                launch_paint.return_value.pid = 98765
                controller.edit_image(store.images[0])
                controller.tick()  # Paint is still opening.
                controller.tick()  # Another application briefly gains focus.
                self.assertFalse(controller.edit_paint_seen)
                controller.tick()  # Paint gains the foreground.
                self.assertTrue(controller.edit_paint_seen)
                controller.window.last_action = time.monotonic() - 11
                controller.tick()
                controller.window.advance()
                self.assertEqual(controller.window.phase, "steady")
                controller.tick()  # Paint is minimized; another window gains focus.
                self.assertIsNone(controller.edit_waiting_since)
                self.assertLess(time.monotonic() - controller.window.last_action, 1)
                restore_topmost.assert_called_once()
                QTest.qWait(300)
                self.assertEqual(restore_topmost.call_count, 2)
                controller.window.last_action = time.monotonic() - 11
                controller.window.advance()
                self.assertEqual(controller.window.phase, "retract")
                controller.window.phase_started = time.monotonic() - RETRACT_TIME
                controller.window.advance()
                self.assertFalse(controller.window.isVisible())
                screen = self.app.primaryScreen().availableGeometry()
                hover = QPoint(screen.x() + screen.width() // 2, screen.y() + 40)
                with (patch("clothesline.QCursor.pos", return_value=hover),
                      patch("clothesline.mouse_buttons_down", return_value=False),
                      patch("clothesline.QApplication.mouseButtons", return_value=Qt.LeftButton)):
                    controller.tick()
                    controller.hover_since = time.monotonic() - 1
                    controller.tick()
                self.assertTrue(controller.window.isVisible())
            controller.tray.hide()
            controller.window.close()

    def test_both_global_hotkeys_expand_and_refresh_the_rack(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = ImageStore(Path(directory))
            store.enabled = True
            controller = ClotheslineApp(self.app, store)
            controller.window.hide()
            hotkeys = GlobalHotkeyFilter(controller.show_from_hotkey)
            user32 = SimpleNamespace(RegisterHotKey=Mock(return_value=True),
                                     UnregisterHotKey=Mock(return_value=True))
            with patch("clothesline.ctypes.windll", SimpleNamespace(user32=user32)):
                self.assertEqual(hotkeys.register(), [])
                self.assertEqual(len(hotkeys.registered), 2)
                for hotkey_id, event_type in (
                    (ident, kind) for ident in (0x351, 0x352)
                    for kind in (b"windows_dispatcher_MSG", b"windows_generic_MSG")
                ):
                    message = wintypes.MSG()
                    message.message = 0x0312  # WM_HOTKEY
                    message.wParam = hotkey_id
                    with patch.object(controller.window, "restore_topmost") as restore:
                        self.assertTrue(hotkeys.nativeEventFilter(
                            event_type, VoidPtr(ctypes.addressof(message), 0)))
                        restore.assert_called_once()
                    self.assertTrue(controller.window.isVisible())
                    self.assertLess(time.monotonic() - controller.window.last_action, 1)
                    controller.window.hide()
                hotkeys.unregister()
                self.assertEqual(user32.UnregisterHotKey.call_count, 2)
                user32.RegisterHotKey.side_effect = [False, True]
                self.assertEqual(hotkeys.register(), ["Win + Alt + L"])
                self.assertEqual(hotkeys.registered, {0x352})
                hotkeys.unregister()
                self.assertEqual(user32.UnregisterHotKey.call_count, 3)
            controller.timer.stop()
            controller.window.frame_timer.stop()
            controller.tray.hide()
            controller.window.close()

    def test_hotkey_filter_ignores_null_unrelated_and_unregistered_messages(self):
        callback = Mock()
        hotkeys = GlobalHotkeyFilter(callback)
        hotkeys.registered = {0x351}
        for pointer in (None, 0, VoidPtr(0, 0)):
            self.assertFalse(hotkeys.nativeEventFilter(b"windows_dispatcher_MSG", pointer))
        message = wintypes.MSG()
        message.message = 0x0312
        message.wParam = 0x999
        pointer = VoidPtr(ctypes.addressof(message), 0)
        self.assertFalse(hotkeys.nativeEventFilter(b"windows_generic_MSG", pointer))
        message.wParam = 0x351
        self.assertFalse(hotkeys.nativeEventFilter(b"unrelated", pointer))
        message.message = 0x0400
        self.assertFalse(hotkeys.nativeEventFilter(b"windows_dispatcher_MSG", pointer))
        callback.assert_not_called()

    def test_clear_button_cancels_or_removes_all_including_hidden_images(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            original = root / "original.png"
            image = QImage(20, 20, QImage.Format_ARGB32)
            image.fill("cyan")
            image.save(str(original))
            store = ImageStore(root / "managed")
            store.enabled = True
            for _ in range(7):
                store.add(image)
            saved_paths = [store.root / name for name in store.images]
            controller = ClotheslineApp(self.app, store)
            controller.show()
            self.finish_entrance(controller.window)
            controller.window.navigate(1)
            self.assertEqual(controller.window.offset, 2)
            clear_rect = controller.window._buttons()["clear"]
            point = clear_rect.center().toPoint()
            self.assertEqual(controller.window._hit(point), ("clear", None))

            with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as question:
                QTest.mouseClick(controller.window, Qt.LeftButton, pos=point)
                question.assert_called_once()
            self.assertEqual(len(store.images), 7)
            self.assertTrue(all(path.exists() for path in saved_paths))

            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question:
                QTest.mouseClick(controller.window, Qt.LeftButton, pos=point)
                question.assert_called_once()
            self.assertEqual(store.images, [])
            self.assertEqual(controller.window.images, [])
            self.assertIn("clear", controller.window._buttons())
            self.assertEqual(controller.window._cat_dialogue_text(),
                             "请通过截图或复制将图片挂上晾衣绳")
            self.assertTrue(all(not path.exists() for path in saved_paths))
            self.assertTrue(original.exists())
            self.assertEqual(ImageStore(store.root).images, [])
            controller.timer.stop()
            controller.window.frame_timer.stop()
            controller.tray.hide()
            controller.window.close()

    def test_cat_hover_lifts_and_returns_after_pointer_leaves(self):
        window = ClotheslineWindow()
        window.set_enabled(True)
        window.set_images(Path.cwd(), ["picture.png"])
        window.show_animated()
        self.finish_entrance(window)
        window.frame_timer.stop()
        self.assertEqual(window._cat_dialogue_text(), "清空晾衣绳上的图片（共1张）")
        cat = window._buttons()["clear"]
        window.last_action = time.monotonic() - 11
        QTest.mouseMove(window, cat.center().toPoint())
        self.assertEqual(window.hovered_control, "clear")
        self.assertLess(time.monotonic() - window.last_action, 1)
        window.last_action = time.monotonic() - 11
        window.cat_hover_updated = time.monotonic() - 0.12
        window.advance()
        self.assertEqual(window.phase, "steady")
        self.assertLess(time.monotonic() - window.last_action, 1)
        lifted = window.cat_hover_progress
        self.assertGreater(lifted, 0.4)
        bubble = window._cat_dialogue_rect()
        self.assertTrue(bubble.left() > cat.right() or bubble.right() < cat.left())
        self.assertLessEqual(bubble.right(), window.width())

        QTest.mouseMove(window, window._buttons()["up"].center().toPoint())
        self.assertIsNone(window.hovered_control)
        window.cat_hover_updated = time.monotonic() - 0.12
        window.advance()
        self.assertLess(window.cat_hover_progress, lifted)
        window.cat_hover_updated = time.monotonic() - 0.25
        window.advance()
        self.assertEqual(window.cat_hover_progress, 0.0)
        window.last_action = time.monotonic() - 11
        window.advance()
        self.assertEqual(window.phase, "retract")
        window.frame_timer.stop()
        window.close()

    def test_empty_rack_cat_hover_and_click(self):
        window = ClotheslineWindow()
        window.set_enabled(True)
        window.set_images(Path.cwd(), [])
        window.show_animated()
        self.finish_entrance(window)
        window.frame_timer.stop()
        self.assertEqual(window._cat_dialogue_text(),
                         "请通过截图或复制将图片挂上晾衣绳")
        cat = window._buttons()["clear"]
        cleared = []
        window.clear_requested.connect(lambda: cleared.append(True))
        QTest.mouseMove(window, cat.center().toPoint())
        window.cat_hover_updated = time.monotonic() - 0.25
        window.advance()
        self.assertEqual(window.cat_hover_progress, 1.0)
        QTest.mouseClick(window, Qt.LeftButton, pos=cat.center().toPoint())
        self.assertEqual(cleared, [])
        QTest.mouseMove(window, window._buttons()["up"].center().toPoint())
        window.cat_hover_updated = time.monotonic() - 0.25
        window.advance()
        self.assertEqual(window.cat_hover_progress, 0.0)
        window.frame_timer.stop()
        window.close()

    def test_rope_drops_empty_then_cards_reveal_and_retract_together(self):
        window = ClotheslineWindow()
        window.set_enabled(True)
        window.set_images(Path.cwd(), ["a.png", "b.png", "c.png"])
        window.show_animated()
        mid = window.width() / 2
        self.assertEqual(window.phase, "drop")
        self.assertAlmostEqual(window.rope_y(0), window.rope_y(mid))
        self.assertEqual(window.cards_opacity, 0.0)
        self.assertAlmostEqual(window.rope_y(0), 32.0)
        frame = QImage(window.size(), QImage.Format_ARGB32_Premultiplied)
        frame.fill(Qt.transparent)
        window.render(frame)

        window.phase_started = time.monotonic() - DROP_TIME
        window.advance()
        self.assertEqual(window.phase, "reveal")
        self.assertAlmostEqual(window.rope_y(0), 44.0)
        self.assertAlmostEqual(window.rope_y(mid), 64.0)
        self.assertEqual(window.cards_opacity, 0.0)
        frame.fill(Qt.transparent)
        window.render(frame)

        window.phase_started = time.monotonic() - CARD_FADE_TIME / 2
        window.advance()
        self.assertGreater(window.cards_opacity, 0.0)
        self.assertLess(window.cards_opacity, 1.0)
        window.phase_started = time.monotonic() - CARD_FADE_TIME
        window.advance()
        self.assertEqual(window.phase, "steady")
        self.assertEqual(window.cards_opacity, 1.0)
        frame.fill(Qt.transparent)
        window.render(frame)

        window.hide_animated()
        window.phase_started = time.monotonic() - RETRACT_TIME / 2
        window.advance()
        self.assertLess(window.rope_y(mid), 64.0)
        self.assertGreaterEqual(window.rope_y(mid) - window._buttons()["up"].bottom(), 7)
        self.assertLess(window.rope_opacity, 1.0)
        self.assertLess(window.cards_opacity, 1.0)
        frame.fill(Qt.transparent)
        window.render(frame)
        window.phase_started = time.monotonic() - RETRACT_TIME
        window.advance()
        self.assertFalse(window.isVisible())
        window.frame_timer.stop()
        window.close()

    def test_first_card_wobbles_while_fading_then_returns_horizontal(self):
        window = ClotheslineWindow()
        window.set_enabled(True)
        window.show_animated()
        self.finish_entrance(window)
        window.set_images(Path.cwd(), ["first.png"], added=True)
        self.assertTrue(window.single_card_wobble)
        self.assertAlmostEqual(window.settle_started, window.move_started)
        window.move_started = time.monotonic() - 0.1
        window.settle_started = time.monotonic() - 0.1
        self.assertGreater(abs(window._angle("first.png")), 0.4)
        self.assertEqual(window.angles["first.png"], 0.0)

        window.hide()
        window.show_animated()
        window.phase_started = time.monotonic() - DROP_TIME
        window.advance()
        self.assertEqual(window.phase, "reveal")
        window.phase_started = time.monotonic() - 0.1
        window.settle_started = time.monotonic() - 0.1
        window.advance()
        self.assertGreater(window.cards_opacity, 0.0)
        self.assertLess(window.cards_opacity, 1.0)
        self.assertGreater(abs(window._angle("first.png")), 0.4)
        window.settle_started = time.monotonic() - 1.1
        self.assertEqual(window._angle("first.png"), 0.0)
        window.frame_timer.stop()
        window.close()

    def test_outer_cards_have_greater_expected_tilt(self):
        window = ClotheslineWindow()
        names = [f"{i}.png" for i in range(5)]
        window.set_images(Path.cwd(), names)
        outer = inner = 0.0
        for _ in range(500):
            window._random_angles()
            self.assertEqual(window.angles[names[2]], 0.0)
            self.assertTrue(all(abs(angle) <= 3.0 for angle in window.angles.values()))
            self.assertGreater(window.angles[names[0]], 0.0)
            self.assertLess(window.angles[names[4]], 0.0)
            outer += abs(window.angles[names[0]]) + abs(window.angles[names[4]])
            inner += abs(window.angles[names[1]]) + abs(window.angles[names[3]])
        self.assertGreater(outer, inner)
        window.settle_started = time.monotonic() - 0.1
        self.assertEqual(window._angle(names[2]), 0.0)
        window.frame_timer.stop()
        window.close()


if __name__ == "__main__":
    unittest.main()
