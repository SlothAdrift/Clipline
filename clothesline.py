"""Screenshot Clothes Rack: a local clipboard image shelf for Windows."""
from __future__ import annotations

import hashlib
import ctypes
import json
import os
import re
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QLockFile, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QIcon, QImage, QImageReader
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from line_canvas import ClotheslineWindow

APP_NAME = "Clipline"
MAX_IMAGES = 10
CLIPBOARD_DEDUP_SECONDS = 0.5
HOTKEYS = ((0x351, 0x0008 | 0x0001, "Win + Alt + L"),
           (0x352, 0x0002 | 0x0001 | 0x0004, "Ctrl + Alt + Shift + L"))


class GlobalHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey):
        super().__init__()
        self.on_hotkey = on_hotkey
        self.registered: set[int] = set()

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_dispatcher_MSG", b"windows_generic_MSG"):
            # Qt supplies a zero-size Shiboken VoidPtr: bool(message) can be
            # false even when its address is valid. Check the address instead.
            address = int(message) if message is not None else 0
            if not address:
                return False
            native_message = wintypes.MSG.from_address(address)
            if native_message.message == 0x0312 and native_message.wParam in self.registered:
                self.on_hotkey()
                return True
        return False

    def register(self) -> list[str]:
        user32 = ctypes.windll.user32
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                           wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        failed = []
        for hotkey_id, modifiers, label in HOTKEYS:
            if user32.RegisterHotKey(None, hotkey_id, modifiers | 0x4000, ord("L")):
                self.registered.add(hotkey_id)
            else:
                failed.append(label)
        return failed

    def unregister(self):
        if not self.registered:
            return
        user32 = ctypes.windll.user32
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        for hotkey_id in self.registered:
            user32.UnregisterHotKey(None, hotkey_id)
        self.registered.clear()


def foreground_process_id() -> int | None:
    """Return the process owning the active Windows window."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    foreground = user32.GetForegroundWindow()
    if not foreground:
        return None
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
    return process_id.value or None


def process_name(process_id: int) -> str | None:
    """Return a Windows process's executable name when it can be queried."""
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, process_id)
    if not handle:
        return None
    try:
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
            return Path(path.value).name.lower()
        return None
    finally:
        kernel32.CloseHandle(handle)


def mouse_buttons_down() -> bool:
    """Read the current physical mouse state, independent of Qt's event cache."""
    if sys.platform != "win32":
        return bool(QApplication.mouseButtons())
    user32 = ctypes.windll.user32
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    return any(user32.GetAsyncKeyState(button) & 0x8000
               for button in (0x01, 0x02, 0x04, 0x05, 0x06))


def data_directory() -> Path:
    override = os.environ.get("CLOTHESLINE_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    return Path(base) / "ScreenshotClothesline"


def clipboard_sequence() -> int | None:
    """One Windows sequence number identifies one clipboard update."""
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
        return None
    sequence = int(ctypes.windll.user32.GetClipboardSequenceNumber())
    return sequence or None


def image_digest(image: QImage) -> bytes:
    normalized = image.convertToFormat(QImage.Format_RGBA8888)
    digest = hashlib.blake2b(digest_size=16)
    digest.update(normalized.width().to_bytes(4, "little"))
    digest.update(normalized.height().to_bytes(4, "little"))
    digest.update(normalized.bits())
    return digest.digest()


class ImageStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = root / "state.json"
        self.enabled = False
        self.images: list[str] = []
        if self.index.exists():
            try:
                state = json.loads(self.index.read_text(encoding="utf-8"))
                self.enabled = bool(state.get("enabled", False))
                self.images = [name for name in state.get("images", [])
                               if isinstance(name, str) and re.fullmatch(r"[0-9a-f]{32}\.png", name)
                               and (self.root / name).is_file()][:MAX_IMAGES]
            except (OSError, ValueError, TypeError):
                pass

    def save_state(self) -> None:
        temp = self.index.with_suffix(".tmp")
        temp.write_text(json.dumps({"enabled": self.enabled, "images": self.images},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.index)

    def add(self, image: QImage) -> Path | None:
        if image.isNull() or not self.enabled:
            return None
        name = f"{uuid.uuid4().hex}.png"
        path = self.root / name
        if not image.save(str(path), "PNG"):
            return None
        self.images.insert(0, name)
        for old in self.images[MAX_IMAGES:]:
            (self.root / old).unlink(missing_ok=True)
        self.images = self.images[:MAX_IMAGES]
        self.save_state()
        return path

    def remove(self, name: str) -> None:
        if name not in self.images:
            return
        self.images.remove(name)
        (self.root / name).unlink(missing_ok=True)
        self.save_state()

    def clear(self) -> None:
        for name in self.images:
            (self.root / name).unlink(missing_ok=True)
        self.images.clear()
        self.save_state()


class ClotheslineApp:
    def __init__(self, app: QApplication, store: ImageStore):
        self.app = app
        self.store = store
        self.window = ClotheslineWindow()
        self.window.set_enabled(store.enabled)
        self.window.set_images(store.root, store.images)
        self.window.toggle_requested.connect(self.toggle)
        self.window.quit_requested.connect(self.confirm_quit)
        self.window.copied.connect(self.copy_image)
        self.window.removed.connect(self.remove_image)
        self.window.clear_requested.connect(self.clear_images)
        self.window.edit_requested.connect(self.edit_image)
        self.clipboard = app.clipboard()
        self.clipboard.dataChanged.connect(self.receive_clipboard)
        self.skip_next_clipboard = False
        self.recent_image_digests: dict[bytes, float] = {}
        self.pending_image_digests: set[bytes] = set()
        self.last_clipboard_sequence: int | None = None
        self.hover_origin: QPoint | None = None
        self.hover_since = 0.0
        self.edit_waiting_since: float | None = None
        self.edit_process_id: int | None = None
        self.edit_paint_seen = False

        icon_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        icon = QIcon(str(icon_base / "assets" / "app_icon.png"))
        app.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, app)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        self.enabled_action = QAction("开启 Clipline 功能", menu)
        self.enabled_action.setCheckable(True)
        self.enabled_action.setChecked(store.enabled)
        self.enabled_action.triggered.connect(self.toggle)
        menu.addAction(self.enabled_action)
        show_action = menu.addAction("显示晾衣绳")
        show_action.triggered.connect(self.show)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(app.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_clicked)
        self.tray.show()

        self.hotkeys: GlobalHotkeyFilter | None = None
        if sys.platform == "win32" and QGuiApplication.platformName() == "windows":
            self.hotkeys = GlobalHotkeyFilter(self.show_from_hotkey)
            app.installNativeEventFilter(self.hotkeys)
            failed = self.hotkeys.register()
            app.aboutToQuit.connect(self.hotkeys.unregister)
            if failed:
                QTimer.singleShot(0, lambda: self.tray.showMessage(
                    APP_NAME, "快捷键已被占用：" + "、".join(failed),
                    QSystemTrayIcon.Warning, 4000))

        self.timer = QTimer(app)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.file_times: dict[str, int] = {}

    def toggle(self, *_):
        self.store.enabled = not self.store.enabled
        self.store.save_state()
        self.window.set_enabled(self.store.enabled)
        self.window.update_mask()
        self.enabled_action.setChecked(self.store.enabled)
        if not self.store.enabled:
            self.window.hide()
        else:
            self.show()

    def receive_clipboard(self):
        observed_at = time.monotonic()
        sequence = clipboard_sequence()
        if self.skip_next_clipboard:
            self.skip_next_clipboard = False
            self.last_clipboard_sequence = sequence
            return
        if not self.store.enabled:
            return
        if sequence is not None and sequence == self.last_clipboard_sequence:
            return
        self.last_clipboard_sequence = sequence
        mime = self.clipboard.mimeData()
        if mime.hasUrls():
            # Explorer copies files as paths (CF_HDROP), not decoded image data.
            paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
            loaded = False
            for path in reversed(paths[:MAX_IMAGES]):
                if path.is_file():
                    reader = QImageReader(str(path))
                    if reader.canRead():
                        self.add_clipboard_image(reader.read(), observed_at=observed_at)
                        loaded = True
            if not loaded and mime.hasImage():
                self.add_clipboard_image(self.clipboard.image(), observed_at=observed_at)
        elif mime.hasImage():
            self.add_clipboard_image(self.clipboard.image(), observed_at=observed_at)

    def add_clipboard_image(self, image: QImage, *, observed_at: float | None = None):
        if image.isNull():
            return
        # Reading/decoding/hashing a large clipboard image may itself be slow.
        # Judge the notification's age before doing that work.
        if observed_at is None:
            observed_at = time.monotonic()
        digest = image_digest(image)
        if digest in self.pending_image_digests:
            return
        self.recent_image_digests = {
            value: stamp for value, stamp in self.recent_image_digests.items()
            if observed_at - stamp < CLIPBOARD_DEDUP_SECONDS
        }
        if digest in self.recent_image_digests:
            return
        self.pending_image_digests.add(digest)
        path = None
        try:
            path = self.store.add(image)
            if path:
                if not self.window.isVisible():
                    self.window.place()
                self.window.set_images(self.store.root, self.store.images, added=True)
                self.window.show_animated()
        finally:
            self.pending_image_digests.discard(digest)
            if path:
                # Start the grace period AFTER PNG encoding, disk I/O and UI
                # loading; otherwise a stalled GUI consumes the entire window.
                self.recent_image_digests[digest] = time.monotonic()

    def copy_image(self, name: str):
        image = QImage(str(self.store.root / name))
        if image.isNull():
            return
        self.recent_image_digests[image_digest(image)] = time.monotonic()
        self.skip_next_clipboard = True
        self.clipboard.setImage(image)
        self.window.show_copy_feedback(name)
        QTimer.singleShot(500, self.clear_skip)
        self.tray.showMessage(APP_NAME, "图片已复制，可以粘贴", QSystemTrayIcon.Information, 1200)

    def clear_skip(self):
        self.skip_next_clipboard = False

    def remove_image(self, name: str):
        self.store.remove(name)
        self.window.set_images(self.store.root, self.store.images)

    def clear_images(self):
        count = len(self.store.images)
        if not count:
            return
        answer = QMessageBox.question(
            self.window, "清空晾衣绳",
            f"清空晾衣绳上的图片（共{count}张）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.store.clear()
        self.file_times.clear()
        self.window.set_images(self.store.root, [])
        self.window.note_action()

    def confirm_quit(self):
        answer = QMessageBox.question(
            self.window, "退出应用", "退出 Clipline 并停止程序运行？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.app.quit()

    def edit_image(self, name: str):
        if name not in self.store.images:
            return
        path = (self.store.root / name).resolve()
        if not path.is_file():
            QMessageBox.warning(self.window, "无法编辑图片", "图片文件已不存在。")
            return
        try:
            process = subprocess.Popen(["mspaint.exe", str(path)])
            self.edit_waiting_since = time.monotonic()
            self.edit_process_id = process.pid if isinstance(process.pid, int) else None
            self.edit_paint_seen = False
            self.window.note_action()
        except OSError:
            QMessageBox.warning(self.window, "无法打开画图",
                                "未找到或无法启动 Windows 画图。请在系统中安装或重新安装“画图”。")

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.window.isVisible():
                self.window.hide_animated()
            else:
                self.show()

    def show(self):
        self.window.show_animated()

    def show_from_hotkey(self):
        self.show()
        self.window.restore_topmost()

    def tick(self):
        if self.edit_waiting_since is not None:
            foreground_pid = foreground_process_id()
            paint_foreground = (foreground_pid is not None and
                                (foreground_pid == self.edit_process_id or
                                 (foreground_pid != os.getpid() and
                                  process_name(foreground_pid) == "mspaint.exe")))
            if paint_foreground:
                self.edit_paint_seen = True
            elif self.edit_paint_seen or time.monotonic() - self.edit_waiting_since >= 8:
                if self.edit_paint_seen:
                    self.window.restore_topmost()
                    QTimer.singleShot(250, self.window.restore_topmost)
                self.edit_waiting_since = None
                self.edit_process_id = None
                self.edit_paint_seen = False
            self.window.note_action()
        if self.store.enabled and not self.window.isVisible():
            cursor = QCursor.pos()
            screen = QGuiApplication.screenAt(cursor)
            if screen:
                rect = screen.availableGeometry()
                within_x = rect.x() + .30 * rect.width() <= cursor.x() <= rect.x() + .70 * rect.width()
                within_y = rect.y() + 25 <= cursor.y() <= rect.y() + 55
                if within_x and within_y and not mouse_buttons_down():
                    if self.hover_origin is None or (cursor - self.hover_origin).manhattanLength() > 6:
                        self.hover_origin = cursor
                        self.hover_since = time.monotonic()
                    elif time.monotonic() - self.hover_since >= .6:
                        self.show()
                        self.hover_origin = None
                else:
                    self.hover_origin = None
        for name in self.store.images:
            path = self.store.root / name
            try:
                stamp = path.stat().st_mtime_ns
            except OSError:
                continue
            if name in self.file_times and self.file_times[name] != stamp:
                self.window.refresh_image(name)
            self.file_times[name] = stamp


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    root = data_directory()
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root / "app.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "Clipline 已在运行，请查看系统托盘。")
        return 0
    store = ImageStore(root)
    controller = ClotheslineApp(app, store)
    controller.show()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.information(controller.window, APP_NAME,
                                "未检测到系统托盘，可使用窗口中的功能开关。")
    try:
        return app.exec()
    finally:
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
