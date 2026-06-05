"""
奖励弹窗 — 轻量级右下角弹出，不打断工作
带粒子光效 + 自动淡出
"""
import math
import random
from PyQt6.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QLinearGradient, QPainterPath

from modules.theme import NEON_COLORS as NC


# ── 轻量粒子（不需要全屏那么暴力）────────────────────────────────────────────

class _Spark:
    __slots__ = ('x', 'y', 'vx', 'vy', 'r', 'alpha', 'color', 'life', 'max_life')

    COLORS = ['#ffd740', '#00e676', '#4fc3f7', '#ff6e40', '#e040fb', '#69f0ae', '#ffab40']

    def __init__(self, cx, cy):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(1.5, 5)
        self.x = cx + random.uniform(-20, 20)
        self.y = cy + random.uniform(-10, 10)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(0, 3)
        self.r = random.uniform(2, 6)
        self.alpha = 240
        self.max_life = random.randint(30, 60)
        self.life = self.max_life
        self.color = QColor(random.choice(self.COLORS))

    def update(self):
        self.x += self.vx; self.y += self.vy
        self.vy += 0.2; self.vx *= 0.96
        self.life -= 1
        self.alpha = int(240 * self.life / self.max_life)
        return self.life > 0


# ── 奖励弹窗 ──────────────────────────────────────────────────────────────────

class RewardPopup(QWidget):
    """右下角淡入弹出的夸夸浮窗，4秒后自动淡出消失"""

    closed = pyqtSignal()

    # 颜色主题
    _THEMES = {
        'water':     {'border': '#4fc3f7', 'glow': '#1565c0', 'bg': (5, 18, 38)},
        'move':      {'border': '#00e676', 'glow': '#1b5e20', 'bg': (5, 20, 10)},
        'milestone': {'border': '#ffd740', 'glow': '#5d4000', 'bg': (20, 14, 0)},
        'streak':    {'border': '#e040fb', 'glow': '#4a148c', 'bg': (20, 5, 25)},
        'score':     {'border': '#ff6e40', 'glow': '#bf360c', 'bg': (22, 8, 0)},
    }

    def __init__(self, title: str, body: str, theme: str = 'water', score: int = None):
        super().__init__()
        self._title = title
        self._body  = body
        self._score = score
        self._theme = self._THEMES.get(theme, self._THEMES['water'])
        self._sparks: list[_Spark] = []
        self._alpha  = 0
        self._fade_out = False
        self._stay_ticks = 0     # 停留帧数（淡入完成后开始计）
        self._STAY = 200         # 约 5 秒 @ 25ms

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(320, 110)
        self._place_at_corner()
        self._burst_sparks()

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(25)

    def _place_at_corner(self):
        screen = QApplication.primaryScreen().geometry()
        # 右下角，留 20px 边距，多个弹窗会依次向上叠
        x = screen.width()  - self.width()  - 20
        y = screen.height() - self.height() - 60
        # 检查是否有其他同类弹窗，向上偏移
        for w in QApplication.topLevelWidgets():
            if isinstance(w, RewardPopup) and w is not self and w.isVisible():
                y -= self.height() + 8
        self.move(x, y)

    def _burst_sparks(self):
        cx, cy = self.width() / 2, self.height() / 2
        for _ in range(20):
            self._sparks.append(_Spark(cx, cy))

    def _tick(self):
        if not self._fade_out:
            self._alpha = min(255, self._alpha + 20)
            if self._alpha >= 255:
                self._stay_ticks += 1
                if self._stay_ticks >= self._STAY:
                    self._fade_out = True
        else:
            self._alpha = max(0, self._alpha - 14)
            if self._alpha == 0:
                self._tick_timer.stop()
                self.closed.emit()
                self.close()
                return

        # 持续少量粒子
        if not self._fade_out and random.random() < 0.25:
            self._sparks.append(_Spark(random.uniform(10, self.width() - 10),
                                       random.uniform(5, 30)))
        self._sparks = [s for s in self._sparks if s.update()]
        self.update()

    def mousePressEvent(self, e):
        self._fade_out = True

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        t = self._theme

        # 背景卡片
        bg = QColor(*t['bg'])
        bg.setAlpha(int(self._alpha * 0.96))
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 12, 12)
        p.setClipPath(path)
        p.fillPath(path, QBrush(bg))

        # 左侧竖条渐变
        bar_grad = QLinearGradient(0, 0, 0, h)
        bc = QColor(t['border'])
        bc.setAlpha(int(self._alpha * 0.9))
        bar_grad.setColorAt(0, bc)
        tc = QColor(t['border']); tc.setAlpha(0)
        bar_grad.setColorAt(1, tc)
        p.setBrush(QBrush(bar_grad)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 4, h, 2, 2)

        # 边框
        border_c = QColor(t['border']); border_c.setAlpha(int(self._alpha * 0.6))
        p.setPen(QPen(border_c, 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, w - 1, h - 1, 12, 12)

        # 粒子
        for s in self._sparks:
            c = QColor(s.color); c.setAlpha(min(s.alpha, self._alpha))
            p.setBrush(QBrush(c)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(int(s.x - s.r), int(s.y - s.r), int(s.r*2), int(s.r*2))

        p.setClipping(False)

        # 标题
        f_t = QFont(); f_t.setPixelSize(14); f_t.setBold(True)
        p.setFont(f_t)
        tc2 = QColor(t['border']); tc2.setAlpha(self._alpha)
        p.setPen(tc2)
        p.drawText(QRect(14, 10, w - 28, 24), Qt.AlignmentFlag.AlignVCenter, self._title)

        # 进度分 (可选)
        if self._score is not None:
            score_c = QColor('#ffd740'); score_c.setAlpha(self._alpha)
            p.setPen(score_c)
            f_s = QFont(); f_s.setPixelSize(13); f_s.setBold(True); p.setFont(f_s)
            p.drawText(QRect(w - 60, 10, 50, 24), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{self._score}分")

        # 正文
        f_b = QFont(); f_b.setPixelSize(12)
        p.setFont(f_b)
        body_c = QColor(NC['text']); body_c.setAlpha(int(self._alpha * 0.85))
        p.setPen(body_c)
        p.drawText(QRect(14, 36, w - 28, h - 46),
                   Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, self._body)

        # 底部进度条（倒计时可视化）
        if not self._fade_out and self._alpha >= 255:
            remain_pct = max(0, 1 - self._stay_ticks / self._STAY)
            bar_w = int((w - 28) * remain_pct)
            bar_bg = QColor(NC['border']); bar_bg.setAlpha(100)
            p.setBrush(QBrush(bar_bg)); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(14, h - 8, w - 28, 3, 1, 1)
            if bar_w > 0:
                bar_c = QColor(t['border']); bar_c.setAlpha(120)
                p.setBrush(QBrush(bar_c))
                p.drawRoundedRect(14, h - 8, bar_w, 3, 1, 1)

        p.end()


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

_active_popups: list[RewardPopup] = []


def _cleanup(popup: RewardPopup):
    if popup in _active_popups:
        _active_popups.remove(popup)


def show_reward(title: str, body: str, theme: str = 'water', score: int = None) -> RewardPopup:
    popup = RewardPopup(title, body, theme, score)
    popup.closed.connect(lambda: _cleanup(popup))
    _active_popups.append(popup)
    popup.show()
    popup.raise_()
    return popup


def show_water_praise(title: str, body: str) -> RewardPopup:
    return show_reward(title, body, 'water')


def show_move_praise(title: str, body: str) -> RewardPopup:
    return show_reward(title, body, 'move')


def show_milestone(title: str, body: str) -> RewardPopup:
    return show_reward(title, body, 'milestone')


def show_streak(title: str, body: str) -> RewardPopup:
    return show_reward(title, body, 'streak')


def show_daily_score(score: int, title: str, body: str) -> RewardPopup:
    return show_reward(title, body, 'score', score=score)
