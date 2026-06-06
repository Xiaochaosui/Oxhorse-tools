"""
打卡面板 — 大按钮 · 情绪价值满满
嵌入 RemindersWidget 顶部 + SalaryClockWidget 顶部
"""
import math
import random
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
from PyQt6.QtCore import Qt, QTimer, QRect, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QPainterPath

from modules.theme import NEON_COLORS as NC
from modules.work_session import WorkSession, WorkState


# ── 按钮光晕粒子 ─────────────────────────────────────────────────────────────

class _GlowParticle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'r', 'alpha', 'color', 'life', 'max_life')
    PALETTES = {
        'green':  ['#00e676', '#69f0ae', '#b9f6ca', '#ffd740'],
        'orange': ['#ff6e40', '#ffab40', '#ffd740', '#ff4081'],
        'cyan':   ['#4fc3f7', '#80deea', '#b2ebf2', '#e040fb'],
        'red':    ['#ff5252', '#ff4081', '#f48fb1', '#ffd740'],
        'purple': ['#e040fb', '#ea80fc', '#ce93d8', '#80deea'],
    }

    def __init__(self, cx, cy, palette='green'):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2, 7)
        self.x = cx + random.uniform(-30, 30)
        self.y = cy + random.uniform(-15, 15)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(1, 4)
        self.r = random.uniform(3, 8)
        self.alpha = 255
        self.max_life = random.randint(40, 80)
        self.life = self.max_life
        self.color = QColor(random.choice(self.PALETTES.get(palette, self.PALETTES['green'])))

    def update(self):
        self.x += self.vx; self.y += self.vy
        self.vy += 0.25; self.vx *= 0.95
        self.life -= 1
        self.alpha = int(255 * self.life / self.max_life)
        return self.life > 0


# ── 单个大按钮 ────────────────────────────────────────────────────────────────

class GlowButton(QWidget):
    """带光晕动效、点击爆粒子的大按钮"""
    clicked = pyqtSignal()

    # 配色主题
    THEMES = {
        'start':    dict(bg='#003d1a', border='#00e676', text='#00e676',   glow='#00e67640', label='green'),
        'lunch':    dict(bg='#3d2200', border='#ffab40', text='#ffab40',   glow='#ffab4040', label='orange'),
        'back':     dict(bg='#003340', border='#4fc3f7', text='#4fc3f7',   glow='#4fc3f740', label='cyan'),
        'overtime': dict(bg='#2a003d', border='#e040fb', text='#e040fb',   glow='#e040fb40', label='purple'),
        'end':      dict(bg='#3d0000', border='#ff5252', text='#ff5252',   glow='#ff525240', label='red'),
        'weekend':  dict(bg='#2d1a00', border='#ffd740', text='#ffd740',   glow='#ffd74040', label='orange'),
    }

    def __init__(self, theme_key: str, icon: str, text: str, sub: str = '', parent=None):
        super().__init__(parent)
        self._theme_key = theme_key
        self._icon = icon
        self._text = text
        self._sub  = sub
        self._particles: list[_GlowParticle] = []
        self._phase = 0.0
        self._hover = False
        self._press_alpha = 0
        self.setFixedHeight(78)
        self.setMinimumWidth(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        t = QTimer(self); t.timeout.connect(self._tick); t.start(25)

    def _tick(self):
        self._phase = (self._phase + 0.06) % (2 * math.pi)
        self._particles = [p for p in self._particles if p.update()]
        if self._press_alpha > 0:
            self._press_alpha = max(0, self._press_alpha - 15)
        self.update()

    def _burst(self):
        th = self.THEMES[self._theme_key]
        cx, cy = self.width() / 2, self.height() / 2
        for _ in range(35):
            self._particles.append(_GlowParticle(cx, cy, th['label']))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_alpha = 180
            self._burst()
            self.clicked.emit()

    def enterEvent(self, e):
        self._hover = True

    def leaveEvent(self, e):
        self._hover = False

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        th = self.THEMES[self._theme_key]

        # 背景圆角卡片
        bg = QColor(th['bg'])
        path = QPainterPath()
        path.addRoundedRect(2, 2, w - 4, h - 4, 14, 14)

        # hover 时稍微加亮
        if self._hover:
            bg_h = QColor(bg); bg_h.setAlpha(220)
            # 渐变
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0, bg_h)
            lighter = QColor(th['border']); lighter.setAlpha(30)
            grad.setColorAt(1, lighter)
            p.fillPath(path, QBrush(grad))
        else:
            p.fillPath(path, QBrush(bg))

        # 点击白闪
        if self._press_alpha > 0:
            flash = QColor(255, 255, 255, self._press_alpha)
            p.fillPath(path, QBrush(flash))

        # 呼吸光晕边框
        glow_a = int(120 + 80 * math.sin(self._phase)) if self._hover else int(60 + 40 * math.sin(self._phase))
        border_c = QColor(th['border']); border_c.setAlpha(glow_a)
        pen = QPen(border_c, 2 if not self._hover else 2.5)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(2, 2, w - 4, h - 4, 14, 14)

        # 粒子
        for pt in self._particles:
            c = QColor(pt.color); c.setAlpha(pt.alpha)
            p.setBrush(QBrush(c)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(int(pt.x - pt.r), int(pt.y - pt.r), int(pt.r * 2), int(pt.r * 2))

        # 图标
        icon_c = QColor(th['text'])
        f_icon = QFont(); f_icon.setPixelSize(24); p.setFont(f_icon)
        p.setPen(icon_c)
        p.drawText(QRect(0, 4, w, 30), Qt.AlignmentFlag.AlignCenter, self._icon)

        # 主文字
        f_txt = QFont(); f_txt.setPixelSize(13); f_txt.setBold(True); p.setFont(f_txt)
        txt_c = QColor(th['text']); txt_c.setAlpha(230)
        p.setPen(txt_c)
        p.drawText(QRect(0, 34, w, 20), Qt.AlignmentFlag.AlignCenter, self._text)

        # 副文字
        if self._sub:
            f_sub = QFont(); f_sub.setPixelSize(9); p.setFont(f_sub)
            sub_c = QColor(th['text']); sub_c.setAlpha(140)
            p.setPen(sub_c)
            p.drawText(QRect(0, 54, w, 16), Qt.AlignmentFlag.AlignCenter, self._sub)

        p.end()


# ── 打卡面板主体 ──────────────────────────────────────────────────────────────

class PunchPanel(QFrame):
    """根据当前工作状态显示不同按钮的打卡面板"""

    punched = pyqtSignal(str)   # 传出事件类型：'in'/'lunch_start'/'lunch_end'/'overtime'/'out'

    # 各状态对应显示配置
    # (按钮列表) 每项: (theme_key, icon, text, sub, action)
    _STATE_BUTTONS = {
        WorkState.BEFORE_WORK: [
            ('start',   '🚀', '开始上班', '打响今天的第一枪！', 'in'),
        ],
        WorkState.WORKING: [
            ('lunch',   '🍜', '去吃午饭', '劳碌了一上午，好好吃！', 'lunch_start'),
            ('end',     '🏠', '下班回家', '今天辛苦了，走！',       'out'),
        ],
        WorkState.LUNCH_BREAK: [
            ('back',    '💻', '下午开工', '吃饱了，继续冲！', 'lunch_end'),
        ],
        WorkState.OVERTIME: [
            ('end',     '🏠', '加班结束', '付出终有回报，走吧！', 'out'),
        ],
        WorkState.OFF_WORK: [],   # 下班后不显示（或显示加班按钮）
    }

    # 下班后额外显示加班按钮
    _OVERTIME_BTN = ('overtime', '⚡', '继续加班', '英雄就是你！', 'overtime')

    # 周末显示
    _WEEKEND_BUTTONS = [
        ('weekend',  '💪', '周末加班打卡', '节假日出勤，牛！', 'in'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session = WorkSession.instance()
        self._session.state_changed.connect(self._on_state_changed)
        self._buttons: list[GlowButton] = []
        self._build_frame()
        self._refresh()

    def _build_frame(self):
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #080f1e, stop:1 #050b14);
                border: 1px solid {NC['border']};
                border-radius: 14px;
            }}
        """)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(14, 12, 14, 14)
        self._root.setSpacing(8)

        # 顶部状态栏
        top = QHBoxLayout(); top.setSpacing(8)
        self._lbl_state_icon = QLabel("📋")
        self._lbl_state_icon.setStyleSheet("font-size:18px;")
        self._lbl_state_text = QLabel("准备开始今天的工作")
        self._lbl_state_text.setStyleSheet(f"color:{NC['cyan']};font-size:13px;font-weight:bold;letter-spacing:1px;")
        self._lbl_time_info = QLabel("")
        self._lbl_time_info.setStyleSheet(f"color:{NC['dim']};font-size:11px;")
        self._lbl_time_info.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._lbl_state_icon)
        top.addWidget(self._lbl_state_text)
        top.addStretch()
        top.addWidget(self._lbl_time_info)
        self._root.addLayout(top)

        # 按钮行（动态构建）
        self._btn_row = QHBoxLayout(); self._btn_row.setSpacing(10)
        self._root.addLayout(self._btn_row)

        # 底部鸡血语
        self._lbl_motto = QLabel("")
        self._lbl_motto.setStyleSheet(
            f"color:{NC['dim']};font-size:11px;font-style:italic;letter-spacing:1px;")
        self._lbl_motto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(self._lbl_motto)

        # 时钟刷新
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_time_info)
        self._clock_timer.start(1000)

    def _clear_buttons(self):
        for b in self._buttons:
            b.setParent(None); b.deleteLater()
        self._buttons.clear()
        # 清空 layout
        while self._btn_row.count():
            item = self._btn_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _refresh(self):
        self._clear_buttons()
        s = self._session.state
        is_weekend = self._session.is_weekend()

        # 决定按钮列表
        if s == WorkState.BEFORE_WORK and is_weekend:
            btn_defs = self._WEEKEND_BUTTONS
        elif s == WorkState.OFF_WORK:
            btn_defs = [self._OVERTIME_BTN]
        else:
            btn_defs = self._STATE_BUTTONS.get(s, [])

        for theme, icon, text, sub, action in btn_defs:
            btn = GlowButton(theme, icon, text, sub)
            btn.clicked.connect(lambda a=action: self._handle_action(a))
            self._btn_row.addWidget(btn)
            self._buttons.append(btn)

        # 状态文字
        icons_map = {
            WorkState.BEFORE_WORK:  ("📋", "准备好了吗？打响今天的第一枪！"),
            WorkState.WORKING:      ("💼", "打工中 · 时间就是人民币"),
            WorkState.LUNCH_BREAK:  ("🍜", "午休中 · 好好吃，下午继续冲"),
            WorkState.OVERTIME:     ("⚡", "加班中 · 你是今天最努力的人"),
            WorkState.OFF_WORK:     ("🎉", "下班啦！今天辛苦了 · 或者继续加班？"),
        }
        ei, et = icons_map.get(s, ("📋", ""))
        if s == WorkState.BEFORE_WORK and is_weekend:
            ei, et = "🌟", "周末！想摸鱼还是加班都行，你最大"
        self._lbl_state_icon.setText(ei)
        self._lbl_state_text.setText(et)

        # 鸡血语
        mottos = {
            WorkState.BEFORE_WORK:  "每天开始打卡的那一刻，就已经赢过了很多人",
            WorkState.WORKING:      "代码在跑，钱在涨，你在努力 · 完美的一天",
            WorkState.LUNCH_BREAK:  "好好休息是为了更好地搬砖，吃饱了再说",
            WorkState.OVERTIME:     "加班是痛苦的，但你的银行卡是感激的",
            WorkState.OFF_WORK:     "今天的你，已经很棒了 · 明天继续冲！",
        }
        self._lbl_motto.setText(mottos.get(s, ""))
        self._update_time_info()

    def _handle_action(self, action: str):
        s = self._session
        if action == 'in':
            s.punch_in()
        elif action == 'lunch_start':
            s.punch_lunch_start()
        elif action == 'lunch_end':
            s.punch_lunch_end()
        elif action == 'overtime':
            s.punch_overtime()
        elif action == 'out':
            s.punch_out()
        self.punched.emit(action)

    def _on_state_changed(self, _state_name: str):
        self._refresh()

    def _update_time_info(self):
        s = self._session
        now = datetime.now()
        info_parts = []
        if s.work_start and s.state != WorkState.BEFORE_WORK:
            elapsed = int((now - s.work_start).total_seconds())
            h, r = divmod(elapsed, 3600); m, _ = divmod(r, 60)
            info_parts.append(f"上班 {h}h{m:02d}m")
        if s.state == WorkState.LUNCH_BREAK and s.lunch_start:
            lb = int((now - s.lunch_start).total_seconds())
            lm, ls = divmod(lb, 60)
            info_parts.append(f"午休 {lm}:{ls:02d}")
        self._lbl_time_info.setText("  ·  ".join(info_parts) if info_parts else now.strftime("%H:%M:%S"))
