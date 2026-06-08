#!/usr/bin/env python3
"""
Work Assistant - 上班族效率小工具
多独立浮窗 · 深色科技风 · 系统托盘管理
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(__file__))

# 首次运行：为缺失的 config/*.json 生成默认文件
from modules.config_manager import ensure_defaults
ensure_defaults()

WIN_POS_FILE = os.path.join(os.path.dirname(__file__), 'config', 'window_positions.json')
AUTOSTART_PATH = os.path.expanduser('~/.config/autostart/work-assistant.desktop')
SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'main.py'))

from PyQt6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu,
    QLabel, QVBoxLayout, QHBoxLayout, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QAction, QKeySequence, QShortcut, QFont

from modules.theme import DARK_TECH, NEON_COLORS as NC
from modules.salary_clock import SalaryClockWidget
from modules.reminders import RemindersWidget
from modules.stock_monitor import StockWidget
from modules.todo_feishu import TodoWidget
from modules.settings_window import SettingsWindow
from modules.health_stats import HealthStatsWindow
from modules.lifelog import LifeLogWindow
from modules.lifelog_monitor import WindowMonitor, ClipboardMonitor, get_active_window
import modules.lifelog_db as lifelog_db


# ── 窗口配置 ──────────────────────────────────────────────────────────────
WINDOWS_CONFIG = [
    {
        'id':     'clock',
        'title':  'CLOCK  //  工作时钟',
        'emoji':  '⏰',
        'width':  520,
        'height': 580,
        'widget': SalaryClockWidget,
        'offset': (0, 0),     # 相对右下角的偏移（右→左, 下→上）
    },
    {
        'id':     'remind',
        'title':  'REMIND  //  提醒',
        'emoji':  '🔔',
        'width':  500,
        'height': 680,
        'widget': RemindersWidget,
        'offset': (540, 0),
    },
    {
        'id':     'stock',
        'title':  'STOCK  //  盯盘',
        'emoji':  '📊',
        'width':  560,
        'height': 460,
        'widget': StockWidget,
        'offset': (0, 620),
    },
    {
        'id':     'todo',
        'title':  'TODO  //  飞书',
        'emoji':  '✓',
        'width':  560,
        'height': 560,
        'widget': TodoWidget,
        'offset': (580, 620),
    },
]


def _make_icon() -> QIcon:
    px = QPixmap(32, 32)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor('#4fc3f7'))
    p.setBrush(QColor('#4fc3f7'))
    p.drawEllipse(4, 4, 24, 24)
    p.setBrush(QColor('#0a0e1a'))
    p.drawEllipse(9, 9, 14, 14)
    p.end()
    return QIcon(px)


# ── 自定义标题栏 ──────────────────────────────────────────────────────────

class TitleBarBtn(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text, color, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(22, 22)
        self._fg = color
        self.setStyleSheet(f"color:{color}; font-size:14px; background:transparent;")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def enterEvent(self, e):
        self.setStyleSheet(f"color:{self._fg}; background:rgba(255,255,255,0.08); border-radius:4px; font-size:14px;")

    def leaveEvent(self, e):
        self.setStyleSheet(f"color:{self._fg}; background:transparent; font-size:14px;")


def _load_positions() -> dict:
    try:
        with open(WIN_POS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_positions(positions: dict):
    try:
        with open(WIN_POS_FILE, 'w') as f:
            json.dump(positions, f)
    except Exception:
        pass


def _setup_autostart(enable: bool):
    """创建或删除 XDG 自启动 .desktop 文件"""
    if enable:
        os.makedirs(os.path.dirname(AUTOSTART_PATH), exist_ok=True)
        content = f"""[Desktop Entry]
Type=Application
Name=Work Assistant
Exec=python3 {SCRIPT_PATH}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Work Assistant - 上班族效率小工具
"""
        with open(AUTOSTART_PATH, 'w') as f:
            f.write(content)
    else:
        try:
            os.remove(AUTOSTART_PATH)
        except FileNotFoundError:
            pass


class FloatWindow(QWidget):
    """单个独立浮窗，支持边缘拖拽调整大小 + 置顶切换"""

    _RESIZE_MARGIN = 8

    def __init__(self, config: dict, pinned: bool = True):
        super().__init__()
        self._cfg = config
        self._pinned = pinned
        self._drag_pos = None
        self._resize_dir = None
        self._resize_start_geom = None
        self._resize_start_pos  = None
        self._apply_flags(pinned, show=False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(320, 280)
        self.resize(config['width'], config['height'])
        self._build_ui()
        self.setMouseTracking(True)

    def _apply_flags(self, pinned: bool, show: bool = True):
        """设置/取消置顶 flag（需要短暂隐藏再显示）"""
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        if pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if show and was_visible:
            self.show()

    def set_pinned(self, pinned: bool):
        self._pinned = pinned
        self._apply_flags(pinned)
        # 刷新按钮样式
        if hasattr(self, '_btn_pin'):
            self._update_pin_btn()

    def _build_ui(self):
        container = QFrame(self)
        container.setObjectName("container")
        container.setGeometry(0, 0, self.width(), self.height())
        container.setStyleSheet(f"""
            QFrame#container {{
                background-color: rgba(10, 14, 26, 248);
                border: 1px solid {NC['border']};
                border-radius: 12px;
            }}
        """)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title_bar = QFrame()
        title_bar.setFixedHeight(34)
        title_bar.setStyleSheet(f"""
            QFrame {{
                background: #060d1c;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid {NC['border']};
            }}
        """)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 8, 0)
        tb_layout.setSpacing(5)

        for color in ['#ff5f57', '#febc2e', '#28c840']:
            dot = QFrame()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"QFrame {{ background:{color}; border-radius:5px; }}")
            tb_layout.addWidget(dot)
        tb_layout.addSpacing(8)

        lbl_title = QLabel(self._cfg['title'])
        lbl_title.setStyleSheet(f"color:{NC['dim']}; font-size:10px; letter-spacing:2px;")
        tb_layout.addWidget(lbl_title)
        tb_layout.addStretch()

        self._btn_pin = TitleBarBtn("📌", NC['cyan'])
        self._btn_pin.setToolTip("点击切换窗口置顶")
        self._btn_pin.clicked.connect(self._toggle_pin)
        self._update_pin_btn()

        btn_min = TitleBarBtn("－", NC['dim'])
        btn_min.clicked.connect(self.hide)
        btn_close = TitleBarBtn("×", '#ff5f57')
        btn_close.clicked.connect(self.hide)
        tb_layout.addWidget(self._btn_pin)
        tb_layout.addWidget(btn_min)
        tb_layout.addWidget(btn_close)

        title_bar.mousePressEvent   = self._tb_press
        title_bar.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
        lbl_title.mousePressEvent   = self._tb_press

        content = self._cfg['widget']()
        self._content_widget = content
        root.addWidget(title_bar)
        root.addWidget(content)

    def _toggle_pin(self):
        self.set_pinned(not self._pinned)

    def _update_pin_btn(self):
        if self._pinned:
            self._btn_pin.setStyleSheet(
                f"color:{NC['cyan']}; background:rgba(79,195,247,0.15); "
                f"border-radius:4px; font-size:12px;"
            )
            self._btn_pin.setToolTip("已置顶 — 点击取消")
        else:
            self._btn_pin.setStyleSheet(
                f"color:{NC['dim']}; background:transparent; font-size:12px;"
            )
            self._btn_pin.setToolTip("未置顶 — 点击置顶")

    # ── 拖拽移动（startSystemMove 跨平台，X11/Wayland/macOS/Windows 均可）──
    def _tb_press(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            win = self.windowHandle()
            if win:
                win.startSystemMove()
            else:
                # 兜底：手动记录坐标
                self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent_drag(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    # ── 边缘调整大小 ──
    def _get_resize_dir(self, pos):
        m = self._RESIZE_MARGIN
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        right  = (w - m) <= x <= w
        bottom = (h - m) <= y <= h
        left   = 0 <= x <= m
        if right and bottom:
            return 'rb'
        if right:
            return 'r'
        if bottom:
            return 'b'
        if left and bottom:
            return 'lb'
        return None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            d = self._get_resize_dir(e.position().toPoint())
            if d:
                self._resize_dir = d
                self._resize_start_geom = self.geometry()
                self._resize_start_pos  = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._resize_dir and e.buttons() == Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self._resize_start_pos
            g = self._resize_start_geom
            new_w, new_h = g.width(), g.height()
            if 'r' in self._resize_dir:
                new_w = max(self.minimumWidth(),  g.width()  + delta.x())
            if 'b' in self._resize_dir:
                new_h = max(self.minimumHeight(), g.height() + delta.y())
            self.resize(new_w, new_h)
        else:
            d = self._get_resize_dir(e.position().toPoint())
            cursors = {
                'rb': Qt.CursorShape.SizeFDiagCursor,
                'lb': Qt.CursorShape.SizeBDiagCursor,
                'r':  Qt.CursorShape.SizeHorCursor,
                'b':  Qt.CursorShape.SizeVerCursor,
            }
            self.setCursor(cursors.get(d, Qt.CursorShape.ArrowCursor))

    def mouseReleaseEvent(self, e):
        self._resize_dir = None
        self._resize_start_geom = None
        self._resize_start_pos  = None

    def resizeEvent(self, e):
        c = self.findChild(QFrame, "container")
        if c:
            c.setGeometry(0, 0, self.width(), self.height())


class App:
    def __init__(self):
        self._windows: dict[str, FloatWindow] = {}
        self._settings_win: SettingsWindow | None = None
        self._stats_win: HealthStatsWindow | None = None
        self._lifelog_win: LifeLogWindow | None = None
        self._lifelog_recording = True
        self._build_windows()
        self._setup_tray()
        self._start_lifelog_monitors()
        QApplication.instance().aboutToQuit.connect(self._on_quit)

    def _build_windows(self):
        screen = QApplication.primaryScreen().geometry()
        sw, sh = screen.width(), screen.height()
        saved = _load_positions()
        for wc in WINDOWS_CONFIG:
            wid   = wc['id']
            entry = saved.get(wid, {})
            pinned = entry.get('pinned', True)   # 默认置顶
            win = FloatWindow(wc, pinned=pinned)
            if entry:
                x = max(0, min(entry.get('x', 0), sw - 320))
                y = max(0, min(entry.get('y', 0), sh - 280))
                win.move(x, y)
                win.resize(entry.get('w', wc['width']), entry.get('h', wc['height']))
            else:
                ox, oy = wc['offset']
                x = sw - wc['width'] - 20 - ox
                y = sh - wc['height'] - 60 - oy
                win.move(max(0, x), max(0, y))
            self._windows[wid] = win

    def _save_all_positions(self):
        try:
            saved = _load_positions()
        except Exception:
            saved = {}
        for wid, win in self._windows.items():
            entry = saved.get(wid, {})
            entry.update({
                'x': win.x(), 'y': win.y(),
                'w': win.width(), 'h': win.height(),
                'pinned': win._pinned,
            })
            saved[wid] = entry
        _save_positions(saved)

    def _open_settings(self):
        if self._settings_win is None:
            self._settings_win = SettingsWindow()
            self._settings_win.settings_saved.connect(self._on_settings_saved)
            # 居中在主屏幕
            screen = QApplication.primaryScreen().geometry()
            sw = self._settings_win
            sw.move(screen.center().x() - sw.width() // 2,
                    screen.center().y() - sw.height() // 2)
        self._settings_win.show()
        self._settings_win.raise_()
        self._settings_win.activateWindow()
        self._settings_win._load_all()  # 每次打开刷新最新值

    def _on_settings_saved(self):
        """设置保存后：刷新各窗口尺寸（如果有变化）、重置窗口位置（如触发）"""
        saved = _load_positions()
        screen = QApplication.primaryScreen().geometry()
        sw_s, sh_s = screen.width(), screen.height()
        for wc in WINDOWS_CONFIG:
            wid = wc['id']
            win = self._windows.get(wid)
            if not win:
                continue
            entry = saved.get(wid, {})
            # 应用尺寸
            if 'w' in entry and 'h' in entry:
                win.resize(entry['w'], entry['h'])
            # 应用位置（如果有重置）
            if 'x' in entry and 'y' in entry:
                x = max(0, min(entry['x'], sw_s - win.width()))
                y = max(0, min(entry['y'], sh_s - win.height()))
                win.move(x, y)

    def show_all(self):
        for win in self._windows.values():
            win.show()

    def hide_all(self):
        for win in self._windows.values():
            win.hide()

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_make_icon())
        self._tray.setToolTip("Work Assistant")

        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background: {NC['bg_card']};
                border: 1px solid {NC['border']};
                color: {NC['text']};
                padding: 4px;
                border-radius: 6px;
            }}
            QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {NC['border']}; color: {NC['cyan']}; }}
            QMenu::separator {{ background: {NC['border']}; height: 1px; margin: 4px 8px; }}
        """)

        act_settings = QAction("⚙  打开设置", menu)
        act_settings.triggered.connect(self._open_settings)
        menu.addAction(act_settings)
        act_stats = QAction("📊  健康统计", menu)
        act_stats.triggered.connect(self._open_stats)
        menu.addAction(act_stats)
        act_lifelog = QAction("⏳  时间胶囊", menu)
        act_lifelog.triggered.connect(self._open_lifelog)
        menu.addAction(act_lifelog)
        self._lifelog_rec_action = QAction("⏸  暂停记录", menu)
        self._lifelog_rec_action.triggered.connect(self._toggle_lifelog_recording)
        menu.addAction(self._lifelog_rec_action)
        menu.addSeparator()

        # 各窗口独立显示切换
        for cfg in WINDOWS_CONFIG:
            wid = cfg['id']
            act = QAction(f"{cfg['emoji']}  {cfg['title']}", menu)
            act.setCheckable(True)
            act.setChecked(True)
            win = self._windows[wid]
            act.triggered.connect(lambda checked, w=win: w.show() if checked else w.hide())
            menu.addAction(act)

        menu.addSeparator()

        act_show_all = QAction("▣  全部显示", menu)
        act_show_all.triggered.connect(self.show_all)
        act_hide_all = QAction("▢  全部隐藏", menu)
        act_hide_all.triggered.connect(self.hide_all)
        menu.addAction(act_show_all)
        menu.addAction(act_hide_all)
        menu.addSeparator()

        act_pin_all   = QAction("📌  全部置顶", menu)
        act_unpin_all = QAction("🔓  全部取消置顶", menu)
        act_pin_all.triggered.connect(lambda: self._set_all_pinned(True))
        act_unpin_all.triggered.connect(lambda: self._set_all_pinned(False))
        menu.addAction(act_pin_all)
        menu.addAction(act_unpin_all)
        menu.addSeparator()

        act_autostart = QAction("⚡  开机自启", menu)
        act_autostart.setCheckable(True)
        act_autostart.setChecked(os.path.exists(AUTOSTART_PATH))
        act_autostart.triggered.connect(lambda checked: _setup_autostart(checked))
        menu.addAction(act_autostart)
        menu.addSeparator()

        act_quit = QAction("⏻  退出", menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_click)
        self._tray.show()

    def _open_stats(self):
        if self._stats_win is None:
            self._stats_win = HealthStatsWindow()
            screen = QApplication.primaryScreen().geometry()
            self._stats_win.move(
                screen.center().x() - self._stats_win.width() // 2,
                screen.center().y() - self._stats_win.height() // 2
            )
        self._stats_win.refresh_all()
        self._stats_win.show()
        self._stats_win.raise_()
        self._stats_win.activateWindow()

    def _open_lifelog(self):
        if self._lifelog_win is None:
            self._lifelog_win = LifeLogWindow()
            screen = QApplication.primaryScreen().geometry()
            self._lifelog_win.move(
                screen.center().x() - self._lifelog_win.width() // 2,
                screen.center().y() - self._lifelog_win.height() // 2,
            )
        self._lifelog_win.show()
        self._lifelog_win.raise_()
        self._lifelog_win.activateWindow()

    def _toggle_lifelog_recording(self):
        self._lifelog_recording = not self._lifelog_recording
        self._lifelog_rec_action.setText(
            "⏸  暂停记录" if self._lifelog_recording else "▶  继续记录"
        )
        if self._lifelog_win:
            self._lifelog_win.set_recording(self._lifelog_recording)

    def _start_lifelog_monitors(self):
        self._win_mon  = WindowMonitor()
        self._win_mon.window_changed.connect(self._on_window_change)
        self._win_mon.start()

        self._clip_mon = ClipboardMonitor(QApplication.instance().clipboard())
        self._clip_mon.new_clip.connect(self._on_clipboard)
        self._clip_mon.start()

    def _on_window_change(self, app: str, title: str, shot: str):
        if self._lifelog_recording:
            lifelog_db.insert("window", app_name=app,
                              window_title=title, content_path=shot)

    def _on_clipboard(self, clip_type: str, content: str):
        if not self._lifelog_recording:
            return
        app, _ = get_active_window()
        if clip_type == "text":
            lifelog_db.insert("clipboard_text",  app_name=app, content_text=content)
        else:
            lifelog_db.insert("clipboard_image", app_name=app, content_path=content)

    def _on_quit(self):
        self._save_all_positions()
        if hasattr(self, "_win_mon"):
            self._win_mon.stop()
        if hasattr(self, "_clip_mon"):
            self._clip_mon.stop()

    def _set_all_pinned(self, pinned: bool):
        for win in self._windows.values():
            win.set_pinned(pinned)

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            any_visible = any(w.isVisible() for w in self._windows.values())
            if any_visible:
                self.hide_all()
            else:
                self.show_all()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("WorkAssistant")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(DARK_TECH)

    wa = App()
    wa.show_all()

    sys.exit(app.exec())
