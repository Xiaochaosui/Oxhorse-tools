"""
全屏浮夸提醒弹窗
粒子爆炸 + 全屏半透明遮罩 + 大字闪烁 + 自动消失
支持：喝水 / 吃饭 / 站起来动一动
"""
import math
import random
from PyQt6.QtWidgets import QWidget, QApplication, QPushButton
from PyQt6.QtCore import Qt, QTimer, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, QPainterPath


# ── 俏皮提醒语句库 ────────────────────────────────────────────────────────────
# 每次触发随机抽一条，title + subtitle 成对
_MOVE_MESSAGES = [
    ("🦴 你的椎间盘在哭泣！", "站起来溜达两圈，别等它罢工"),
    ("🧠 大脑缺氧警告！", "久坐血液都堆腿上去了，快动一动"),
    ("🚨 侦测到高危码农姿势！", "离开座位，你的腰不是铁打的"),
    ("🐢 你比龟还慢——至少龟会走路！", "离开椅子，哪怕只是去趟厕所"),
    ("📡 模型还在跑，你先去跑两步", "训练的事交给 GPU，健康得靠自己"),
    ("💀 久坐是新型吸烟", "每 45 分钟站一次，命更值钱"),
    ("🤖 机器可以 24h 不动，你不行", "站起来，活动五分钟，效率反而更高"),
    ("🔋 电量不足 10%，请充电！", "站起来走走，相当于给大脑插上充电线"),
    ("🦵 你的腿记得你吗？", "它已经麻了，去认识认识它"),
    ("⚡ 久坐伤身，站立续命！", "五分钟，绕工位走两圈，血液循环一下"),
    ("🏃 跑不动没关系，走两步行不行？", "站起来溜达，你的背脊会感谢你"),
    ("📊 loss 在降，你的颈椎在升", "快去做两个肩颈环绕，投资回报率极高"),
    ("🍑 你的屁股快和椅子融合了！", "赶紧站起来，物理分离一下"),
    ("🧘 算法工程师最贵的资产是身体", "别把它坐废了，起来活动五分钟"),
    ("🌊 血栓预防指南第一条：别久坐", "站起来走走，自己的健康自己负责"),
    ("💪 模型涨点靠调参，你的健康靠运动", "现在就站起来，五分钟不亏"),
    ("🎯 你今天已经坐了太久了", "起来！走两步！就这么简单！"),
    ("🌿 植物都要浇水，你要走路", "离开工位，哪怕装作去倒水也好"),
    ("🔥 燃烧吧，卡路里！", "算法不会帮你减肥，站起来才会"),
    ("😤 凭什么 GPU 在工作你在坐着？", "它在跑，你也得动，站起来！"),
    ("🏋️ 你不是在等 GPU，你在等腰椎病", "站起来，做两个拉伸，提前预防"),
    ("💼 打工人的命是自己给的", "久坐一小时 = 少活 22 分钟，快起来"),
    ("🎮 你不是在 AFK，你在伤身", "五分钟活动，比任何补药都有效"),
    ("🚶 用两条腿走路，这是人类进化的成果", "别辜负几百万年的演化，站起来！"),
    ("🤸 颈椎不好？那是因为你坐太久了", "左转右转，活动一下，别等它发警报"),
    ("🌅 站起来，看看窗外，世界还在转", "对焦远方，眼睛感谢你，腰也感谢你"),
    ("🎪 不是在 review 代码，就是在坐着 review 代码", "换个姿势——站着！"),
    ("🧬 你的 DNA 里写着要直立行走", "违背本性太久了，快站起来"),
    ("📈 投资自己健康，ROI 最高", "现在站起来，是你今天最好的决策"),
    ("🦅 展开双臂，释放被代码束缚的灵魂", "站起来，伸个懒腰，做个人"),
]


# ── 粒子 ─────────────────────────────────────────────────────────────────────

class Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'r', 'alpha', 'color', 'life', 'max_life', 'kind')

    def __init__(self, cx: float, cy: float, kind: str = 'spark'):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2, 10)
        self.x = cx + random.uniform(-30, 30)
        self.y = cy + random.uniform(-30, 30)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(0, 4)
        self.r = random.uniform(3, 9)
        self.alpha = 255
        self.max_life = random.randint(40, 90)
        self.life = self.max_life
        self.kind = kind
        palettes = {
            'water': ['#4fc3f7', '#81d4fa', '#b3e5fc', '#80deea', '#e0f7fa', '#ffffff'],
            'food':  ['#ff9800', '#ffc107', '#ff5722', '#ffeb3b', '#ff7043', '#ffe082'],
            'move':  ['#00e676', '#69f0ae', '#b9f6ca', '#76ff03', '#ccff90', '#ffffff'],
            'spark': ['#4fc3f7', '#ff9800', '#ffffff', '#ffd740'],
        }
        self.color = QColor(random.choice(palettes.get(kind, palettes['spark'])))

    def update(self):
        self.x  += self.vx
        self.y  += self.vy
        self.vy += 0.25
        self.vx *= 0.97
        self.life -= 1
        self.alpha = int(255 * (self.life / self.max_life))
        self.r    = max(1, self.r * 0.985)

    @property
    def alive(self):
        return self.life > 0


# ── 全屏弹窗 ─────────────────────────────────────────────────────────────────

class FullscreenAlert(QWidget):
    dismissed = pyqtSignal()
    confirmed = pyqtSignal()
    snoozed = pyqtSignal()
    auto_closed = pyqtSignal()

    WATER_CFG = {
        'kind':      'water',
        'emoji':     '💧',
        'title':     '该喝水啦！',
        'subtitle':  '离开座位，喝一杯温水，动一动',
        'bg_start':  QColor(0, 30, 60, 210),
        'bg_end':    QColor(0, 60, 100, 190),
        'accent':    QColor(79, 195, 247),
        'auto_secs': 12,
    }
    FOOD_CFG = {
        'kind':      'food',
        'emoji':     '🍱',
        'title':     '吃饭时间到！',
        'subtitle':  '放下工具，好好吃饭，补充能量',
        'bg_start':  QColor(60, 20, 0, 210),
        'bg_end':    QColor(100, 40, 0, 190),
        'accent':    QColor(255, 152, 0),
        'auto_secs': 15,
    }

    def __init__(self, cfg_key: str = 'water', move_msg: tuple | None = None):
        super().__init__()

        if cfg_key == 'move':
            title, subtitle = move_msg or random.choice(_MOVE_MESSAGES)
            self._vcfg = {
                'kind':      'move',
                'emoji':     '🏃',
                'title':     title,
                'subtitle':  subtitle,
                'bg_start':  QColor(0, 50, 20, 215),
                'bg_end':    QColor(0, 90, 30, 190),
                'accent':    QColor(0, 230, 118),
                'auto_secs': 20,
            }
        elif cfg_key == 'water':
            self._vcfg = self.WATER_CFG
        else:
            self._vcfg = self.FOOD_CFG

        self._particles: list[Particle] = []
        self._phase      = 0.0
        self._text_scale = 0.0
        self._alpha      = 0
        self._fade_out   = False
        self._countdown  = self._vcfg['auto_secs']

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._build_btn()
        self._burst(10)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(16)

        self._cd_timer = QTimer(self)
        self._cd_timer.timeout.connect(self._cd_tick)
        self._cd_timer.start(1000)

    def _build_btn(self):
        cx, cy = self.width() // 2, self.height() // 2
        color_map = {
            'water': '#4fc3f7',
            'food':  '#ff9800',
            'move':  '#00e676',
        }
        color = color_map.get(self._vcfg['kind'], '#4fc3f7')

        # 主确认按钮
        btn = QPushButton("好的，这就动！✓" if self._vcfg['kind'] == 'move' else "知道了 ✓", self)
        btn.setFixedSize(200, 52)
        btn.move(cx - 100, cy + 130)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,0,0,0);
                color: {color};
                border: 2px solid {color};
                border-radius: 26px;
                font-size: 16px;
                font-weight: bold;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
            QPushButton:pressed {{ background: rgba(255,255,255,0.22); }}
        """)
        btn.clicked.connect(self._confirm)
        self._btn = btn

        # 「再给我5分钟」按钮（仅运动提醒）
        if self._vcfg['kind'] == 'move':
            btn2 = QPushButton("再坐 5 分钟…", self)
            btn2.setFixedSize(160, 40)
            btn2.move(cx - 80, cy + 200)
            btn2.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(0,0,0,0);
                    color: rgba(150,150,150,180);
                    border: 1px solid rgba(150,150,150,100);
                    border-radius: 20px;
                    font-size: 13px;
                }}
                QPushButton:hover {{ color: rgba(200,200,200,220); }}
            """)
            btn2.clicked.connect(self._snooze)

    def _burst(self, n: int = 6):
        cx, cy = self.width() / 2, self.height() / 2
        for _ in range(n * 8):
            self._particles.append(Particle(cx, cy, self._vcfg['kind']))

    def _tick(self):
        self._phase += 0.05
        if not self._fade_out:
            self._alpha      = min(255, self._alpha + 18)
            self._text_scale = min(1.0, self._text_scale + 0.06)
        else:
            self._alpha      = max(0, self._alpha - 18)
            self._text_scale = max(0.0, self._text_scale - 0.08)
            if self._alpha == 0:
                self._tick_timer.stop()
                self.close()
                self.dismissed.emit()
                return

        if not self._fade_out and random.random() < 0.6:
            cx = self.width() / 2 + random.uniform(-200, 200)
            cy = self.height() / 2 + random.uniform(-100, 100)
            for _ in range(3):
                self._particles.append(Particle(cx, cy, self._vcfg['kind']))

        for p in self._particles:
            p.update()
        self._particles = [p for p in self._particles if p.alive]
        self.update()

    def _cd_tick(self):
        self._countdown -= 1
        label = "好的，这就动！" if self._vcfg['kind'] == 'move' else "知道了"
        self._btn.setText(f"{label} ✓  ({self._countdown})")
        if self._countdown <= 0:
            self._cd_timer.stop()
            self._log_action('auto_close')
            self.auto_closed.emit()
            self._dismiss()

    def _confirm(self):
        """用户明确点击主按钮，才算真实完成。"""
        self._cd_timer.stop()
        self._log_action('completed')
        self.confirmed.emit()
        self._fade_out = True
        self._burst(4)

    def _dismiss(self):
        self._cd_timer.stop()
        self._fade_out = True
        self._burst(4)

    def _snooze(self):
        """再坐5分钟 — 关闭弹窗但不重置计时器"""
        self._cd_timer.stop()
        self._log_action('snoozed')
        self.snoozed.emit()
        self._fade_out = True
        self._burst(2)

    def _log_action(self, action: str):
        try:
            from modules import health_db as hdb
            type_map = {'water': hdb.TYPE_WATER, 'food': hdb.TYPE_MEAL, 'move': hdb.TYPE_MOVE}
            t = type_map.get(self._vcfg['kind'])
            if t:
                hdb.log(t, action)
        except Exception:
            pass

    def mousePressEvent(self, e):
        self._dismiss()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # 背景
        bg_s = QColor(self._vcfg['bg_start'])
        bg_s.setAlpha(int(self._alpha * bg_s.alphaF()))
        bg_e = QColor(self._vcfg['bg_end'])
        bg_e.setAlpha(int(self._alpha * bg_e.alphaF()))
        grad = QRadialGradient(cx, cy, max(w, h) * 0.7)
        grad.setColorAt(0, bg_s); grad.setColorAt(1, bg_e)
        p.fillRect(0, 0, w, h, QBrush(grad))

        # 粒子
        for pt in self._particles:
            c = QColor(pt.color); c.setAlpha(pt.alpha)
            p.setBrush(QBrush(c)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(int(pt.x - pt.r), int(pt.y - pt.r), int(pt.r * 2), int(pt.r * 2))

        # 中央光晕
        glow_r = 220 + int(30 * math.sin(self._phase))
        glow = QRadialGradient(cx, cy, glow_r)
        accent = QColor(self._vcfg['accent']); accent.setAlpha(int(60 * self._text_scale))
        trans = QColor(accent); trans.setAlpha(0)
        glow.setColorAt(0, accent); glow.setColorAt(1, trans)
        p.setBrush(QBrush(glow)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx - glow_r), int(cy - glow_r), glow_r * 2, glow_r * 2)

        # 文字弹入
        p.save()
        p.translate(cx, cy)
        p.scale(self._text_scale, self._text_scale)

        # emoji（运动提醒额外加弹跳感）
        f_e = QFont(); f_e.setPixelSize(100); p.setFont(f_e)
        bounce = int(10 * math.sin(self._phase * 4)) if self._vcfg['kind'] == 'move' else 0
        flicker = int(230 + 25 * math.sin(self._phase * 3))
        p.setPen(QColor(255, 255, 255, min(flicker, 255)))
        p.drawText(QRect(-200, -210 + bounce, 400, 120), Qt.AlignmentFlag.AlignCenter, self._vcfg['emoji'])

        # 主标题
        f_t = QFont(); f_t.setPixelSize(54); f_t.setBold(True)
        f_t.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
        p.setFont(f_t)
        accent_c = QColor(self._vcfg['accent']); accent_c.setAlpha(255)
        p.setPen(accent_c)
        p.drawText(QRect(-450, -80, 900, 80), Qt.AlignmentFlag.AlignCenter, self._vcfg['title'])

        # 副标题
        f_s = QFont(); f_s.setPixelSize(22)
        f_s.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        p.setFont(f_s)
        p.setPen(QColor(200, 230, 210 if self._vcfg['kind'] == 'move' else 240, 210))
        p.drawText(QRect(-450, 14, 900, 40), Qt.AlignmentFlag.AlignCenter, self._vcfg['subtitle'])

        p.restore()
        p.end()


def show_water_alert() -> FullscreenAlert:
    a = FullscreenAlert('water'); a.show(); a.raise_(); a.activateWindow(); return a

def show_food_alert() -> FullscreenAlert:
    a = FullscreenAlert('food'); a.show(); a.raise_(); a.activateWindow(); return a

def show_move_alert() -> FullscreenAlert:
    msg = random.choice(_MOVE_MESSAGES)
    a = FullscreenAlert('move', move_msg=msg)
    a.show(); a.raise_(); a.activateWindow()
    return a
