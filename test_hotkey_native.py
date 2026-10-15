"""Run separately on Windows: exercises Qt's real native-message bridge.

Posts only to this test's own thread; does not reserve global shortcuts or
send keyboard input to the desktop. No application window is created.
"""
import ctypes
import sys
import unittest
from ctypes import wintypes

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from clothesline import GlobalHotkeyFilter


@unittest.skipUnless(sys.platform == "win32", "Windows native message test")
class NativeHotkeyTests(unittest.TestCase):
    def test_hotkeys_arrive_through_qt_native_bridge_once_each(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        calls = []
        hotkeys = GlobalHotkeyFilter(lambda: calls.append(True))
        hotkeys.registered = {0x351, 0x352}
        app.installNativeEventFilter(hotkeys)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                            wintypes.WPARAM, wintypes.LPARAM]
        user32.PostThreadMessageW.restype = wintypes.BOOL
        thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        loop = QEventLoop()
        posted = []

        def post():
            for ident in (0x351, 0x352, 0x999):
                posted.append(bool(user32.PostThreadMessageW(thread_id, 0x0312, ident, 0)))

        try:
            QTimer.singleShot(0, post)
            QTimer.singleShot(200, loop.quit)
            loop.exec()
            self.assertEqual(posted, [True, True, True])
            self.assertEqual(len(calls), 2)
        finally:
            app.removeNativeEventFilter(hotkeys)


if __name__ == "__main__":
    unittest.main()
