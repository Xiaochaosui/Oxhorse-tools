"""
LifeLog 后台监控线程
- WindowMonitor  : 监测活跃窗口切换 → 截图
- ClipboardMonitor: 监测剪贴板变化 → 存文字 / 图片
"""
import re, time, hashlib, subprocess
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from modules.lifelog_db import SHOTS_DIR, CLIPS_DIR


# ── 系统工具函数 ─────────────────────────────────────────────────────────

def get_active_window() -> tuple[str, str]:
    """返回 (app_name, window_title)"""
    try:
        wid   = subprocess.check_output(["xdotool", "getactivewindow"],     stderr=subprocess.DEVNULL).decode().strip()
        title = subprocess.check_output(["xdotool", "getwindowname",  wid], stderr=subprocess.DEVNULL).decode().strip()
        pid   = subprocess.check_output(["xdotool", "getwindowpid",   wid], stderr=subprocess.DEVNULL).decode().strip()
        app   = subprocess.check_output(["ps", "-p", pid, "-o", "comm="],   stderr=subprocess.DEVNULL).decode().strip()
        return app, title
    except Exception:
        return "", ""


def take_screenshot(app_name: str) -> str:
    """截全屏保存为 JPEG，返回文件路径，失败返回空串"""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QScreen
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


# ── 窗口监控线程 ─────────────────────────────────────────────────────────

class WindowMonitor(QThread):
    window_changed = pyqtSignal(str, str, str)   # app, title, shot_path

    def __init__(self):
        super().__init__()
        self._stop = False
        self._last = ""

    def run(self):
        while not self._stop:
            try:
                app, title = get_active_window()
                if title and title != self._last:
                    self._last = title
                    shot = take_screenshot(app)
                    self.window_changed.emit(app, title, shot)
            except Exception:
                pass
            time.sleep(1.2)

    def stop(self):
        self._stop = True
        self.wait(3000)


# ── 剪贴板监控线程 ────────────────────────────────────────────────────────

class ClipboardMonitor(QThread):
    new_clip = pyqtSignal(str, str)   # 'text' / 'image', content_or_path

    def __init__(self, clipboard):
        super().__init__()
        self._stop      = False
        self._last_hash = ""
        self._cb        = clipboard

    def run(self):
        while not self._stop:
            try:
                self._check()
            except Exception:
                pass
            time.sleep(0.8)

    def _check(self):
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

    def stop(self):
        self._stop = True
        self.wait(3000)
