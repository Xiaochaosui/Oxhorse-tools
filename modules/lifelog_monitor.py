"""
LifeLog 后台监控
- WindowMonitor  : 后台线程探测窗口切换（跨平台，纯 subprocess / ctypes，线程安全）
                   截图通过信号派发回主线程执行（Qt GUI 操作必须在主线程）
- ClipboardMonitor: 纯主线程 QObject，连接 QClipboard.dataChanged 信号
"""
import re, hashlib
from datetime import datetime

from PyQt6.QtCore import QThread, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication

from modules.lifelog_db import SHOTS_DIR, CLIPS_DIR
from cross_platform_utils import get_active_window


def take_screenshot(app_name: str) -> str:
    """截全屏保存为 JPEG，必须在主线程调用"""
    try:
        screen = QApplication.primaryScreen()
        if screen is None:
            return ""
        pixmap = screen.grabWindow(0)
        name = (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
            f"{re.sub(r'[^a-zA-Z0-9]', '_', app_name)[:20]}.jpg"
        )
        path = SHOTS_DIR / name
        pixmap.save(str(path), "JPEG", 65)
        return str(path)
    except Exception:
        return ""


# ── 窗口监控：后台线程轮询活动窗口 ──────────────────────────────────────

class _WindowPoller(QThread):
    """轮询活动窗口（跨平台），检测到标题变化时 emit 信号（不碰 Qt GUI）"""
    title_changed = pyqtSignal(str, str)   # app, title

    def __init__(self):
        super().__init__()
        self._stop = False
        self._last = ""

    def run(self):
        import time
        while not self._stop:
            try:
                app, title = get_active_window()
                if title and title != self._last:
                    self._last = title
                    self.title_changed.emit(app, title)
            except Exception:
                pass
            time.sleep(1.2)

    def stop(self):
        self._stop = True
        self.wait(3000)


class WindowMonitor(QObject):
    """主线程对象：收到 _WindowPoller 信号后在主线程截图，再 emit 最终结果"""
    window_changed = pyqtSignal(str, str, str)   # app, title, shot_path

    def __init__(self):
        super().__init__()
        self._poller = _WindowPoller()
        self._poller.title_changed.connect(self._on_title_changed)

    def _on_title_changed(self, app: str, title: str):
        shot = take_screenshot(app)   # 主线程执行，安全
        self.window_changed.emit(app, title, shot)

    def start(self):
        self._poller.start()

    def stop(self):
        self._poller.stop()


# ── 剪贴板监控：纯主线程 QObject ─────────────────────────────────────────

class ClipboardMonitor(QObject):
    """连接 QClipboard.dataChanged，全程在主线程，不启动任何子线程"""
    new_clip = pyqtSignal(str, str)   # 'text' / 'image', content_or_path

    def __init__(self, clipboard):
        super().__init__()
        self._cb        = clipboard
        self._last_hash = ""
        self._cb.dataChanged.connect(self._on_data_changed)

    def _on_data_changed(self):
        try:
            mime = self._cb.mimeData()
            if mime is None:
                return

            if mime.hasImage():
                img: QImage = self._cb.image()
                if img.isNull():
                    return
                raw = img.bits().asarray(img.sizeInBytes())
                h   = hashlib.md5(bytes(raw)).hexdigest()
                if h == self._last_hash:
                    return
                self._last_hash = h
                path = CLIPS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{h[:8]}.png"
                QPixmap.fromImage(img).save(str(path))
                self.new_clip.emit("image", str(path))

            elif mime.hasText():
                text = self._cb.text().strip()
                if not text:
                    return
                h = hashlib.md5(text.encode()).hexdigest()
                if h == self._last_hash:
                    return
                self._last_hash = h
                self.new_clip.emit("text", text)
        except Exception:
            pass

    def stop(self):
        self._cb.dataChanged.disconnect(self._on_data_changed)
