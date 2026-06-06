"""
上下班时钟、工资计量、发薪倒计时
含：钱雨动画、励志语句轮播
"""
import math
import random
from datetime import datetime, date, timedelta
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import QTimer, Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient
from modules.theme import NEON_COLORS as NC
import modules.config_manager as cfg
from modules.work_session import WorkSession, WorkState


# ── 励志语句库（100 条，涵盖 AI 算法人、打工人、财富感）─────────────────────
_QUOTES = [
    "每一行代码都是你积累的财富。",
    "模型在跑，钱在涨，摸鱼也是生产力。",
    "你今天 debug 的 bug，明天就是别人羡慕的经验。",
    "不是在开会，就是在去开会的路上——但钱还在涨。",
    "梯度下降，收入上升。",
    "把时间卖给公司，把才华留给自己。",
    "今日打工，明日打工，但每秒都在赚钱。",
    "GPU 在算，你在摸，进度条都在跑。",
    "人间值得，工资值更多。",
    "又是充实的一天，钱包也在充实。",
    "你的每一秒，都在转化为人民币。",
    "卷不动了？但钱还在流。",
    "算法改变世界，也改变你的银行卡余额。",
    "loss 在降，工资在涨，人生向好。",
    "今天的努力是明天涨薪的底气。",
    "比你聪明的人还比你努力，那你不努力不就亏了？",
    "代码写得好，福报少不了。",
    "不要问薪水够不够，要问今天学了多少。",
    "每个成功的 PR，都是一笔小小的投资。",
    "休息是为了更好地赚钱。",
    "时间是最公平的，每人每天 86400 秒。",
    "你离财务自由只差一个好的算法。",
    "熬过这段时间，就是别人羡慕的经历。",
    "大模型会替代平庸，但不会替代有深度的你。",
    "你不是在打工，你在用时间换未来。",
    "今天解决的问题，明天都是你的护城河。",
    "AI 时代，学得快才是真财富。",
    "钱是一种量化的努力。",
    "每次 commit 都是一次微小的成功。",
    "把难题干掉，工资自然上去。",
    "比起焦虑，不如干一件具体的事。",
    "代码跑起来的那一刻，很爽。",
    "你现在的积累，是未来溢价的资本。",
    "今天多学一点，明天选择多一点。",
    "工作是手段，生活才是目的——但先把工作搞好。",
    "不是每个 epoch 都有提升，但每个 epoch 都算数。",
    "慢慢来，比较快。",
    "聪明人找杠杆，努力人打基础，你两样都要有。",
    "今天让你崩溃的 bug，三天后就是段子。",
    "别人在休息，你在积累；别人醒来，你已领先。",
    "大脑是最好的 GPU，要给它充电。",
    "你写的每行代码，都有人在用。这很了不起。",
    "不怕慢，就怕站。",
    "钱来了，不要慌；钱少了，继续学。",
    "成长是一种复利，今天的 1% 会滚出未来的大数字。",
    "现在看起来很难，回头看都是小事。",
    "你比你想象的更强大。",
    "压力是成长的前兆，不适感是突破的信号。",
    "今天的版本比昨天好，就够了。",
    "不内耗，不焦虑，专注手头这件事。",
    "薪资是上限，能力才是天花板。",
    "你值得被高薪对待，但先让自己配得上。",
    "在最难的事情上坚持，就是与众不同。",
    "算法工程师的价值，在于把复杂变简单。",
    "今日事今日毕，工资日日进。",
    "精力比时间更值钱，好好睡觉。",
    "每一次技术突破，都是一次身价提升。",
    "复盘比努力更重要。",
    "干就完了，别想太多。",
    "优秀是一种习惯，从今天开始。",
    "你现在承受的，都是未来吹牛的资本。",
    "思考清楚再下手，少走弯路。",
    "一个好的想法 + 执行力 = 改变。",
    "工资涨不涨，先看你敢不敢提。",
    "技术不会骗人，能力说话。",
    "专注比努力更重要。",
    "数据不会说谎，但你要会问对问题。",
    "好奇心是工程师最贵的品质。",
    "今天多一份积累，明天多一份从容。",
    "代码是工具，思维才是核心。",
    "你的成长速度，决定你的薪资速度。",
    "把一件事做到极致，就是竞争力。",
    "不是每天都有灵感，但每天都要有输出。",
    "量变引起质变，坚持就是积累量变。",
    "多写，多读，多想，少抱怨。",
    "你比昨天好一点，就是进步。",
    "工作是最好的修行场。",
    "不焦虑未来，不后悔过去，专注当下。",
    "能力圈扩一圈，机会圈大一圈。",
    "钱是量化的时间，花好每一秒。",
    "把复杂的事情做简单，把简单的事情做极致。",
    "每一个大神，都是从菜鸟熬过来的。",
    "你的上限，是你还没到达的地方。",
    "先完成，再完美。",
    "把焦虑变成行动，就赢了一半。",
    "今天的疲惫，是明天的勋章。",
    "写代码如写诗，讲究的是韵律和优雅。",
    "学新技术的痛苦是暂时的，落后的痛苦是长期的。",
    "不卷别人，只卷昨天的自己。",
    "每次搞定一个难题，就是一次定价权提升。",
    "工程师的价值，在深度不在广度——但广度是基础。",
    "今天能多想一步，明天就能少踩一个坑。",
    "做难而正确的事。",
    "在不确定的世界里，能力是最确定的资产。",
    "你的专注是别人卷不走的护城河。",
    "钱是结果，成长是过程，搞好过程。",
    "今天又是充实的一天，感谢还在成长的自己。",
]


def _next_salary_date(salary_day: int) -> date:
    today = date.today()
    year, month = today.year, today.month
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    candidate = date(year, month, min(salary_day, last_day))
    if candidate < today:
        month += 1
        if month > 12:
            year, month = year + 1, 1
        last_day = calendar.monthrange(year, month)[1]
        candidate = date(year, month, min(salary_day, last_day))
    while candidate.weekday() in (5, 6):
        candidate -= timedelta(days=1)
    return candidate


# ── 钱雨粒子 ─────────────────────────────────────────────────────────────────

class _Coin:
    """单个下落的钱币/符号"""
    __slots__ = ('x', 'y', 'vy', 'vx', 'size', 'alpha', 'rot', 'rot_v',
                 'symbol', 'color', 'life', 'max_life')

    SYMBOLS = ['¥', '¥', '¥', '$', '💰', '💵', '🪙', '💎']
    COLORS  = ['#ffd740', '#00e676', '#4fc3f7', '#ffb300', '#69f0ae', '#ffd54f']

    def __init__(self, width: int):
        self.x      = random.uniform(10, width - 10)
        self.y      = random.uniform(-40, -5)
        self.vy     = random.uniform(1.5, 4.5)
        self.vx     = random.uniform(-0.6, 0.6)
        self.size   = random.randint(11, 22)
        self.alpha  = random.randint(160, 255)
        self.rot    = random.uniform(0, 360)
        self.rot_v  = random.uniform(-4, 4)
        self.symbol = random.choice(self.SYMBOLS)
        self.color  = random.choice(self.COLORS)
        self.max_life = random.randint(80, 160)
        self.life   = self.max_life

    def update(self):
        self.y    += self.vy
        self.x    += self.vx
        self.vy   += 0.08          # 重力
        self.rot  += self.rot_v
        self.life -= 1
        # 后半段逐渐透明
        if self.life < self.max_life * 0.4:
            self.alpha = int(255 * (self.life / (self.max_life * 0.4)))
        return self.life > 0


class MoneyRainWidget(QWidget):
    """全宽钱雨画布，叠在其他 Widget 上方（透明背景）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._coins: list[_Coin] = []
        self._spawn_rate = 0.0    # 每帧期望新增数量（由外部设置）
        self._frac = 0.0          # 小数累积
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(25)               # ~40fps

    def set_intensity(self, rate: float):
        """rate: 每帧期望新增粒子数，0=停止，1=普通，3=爆发"""
        self._spawn_rate = max(0.0, rate)

    def burst(self, n: int = 20):
        """一次性爆发 n 个粒子"""
        for _ in range(n):
            self._coins.append(_Coin(max(self.width(), 100)))

    def _tick(self):
        # 生成新粒子
        if self._spawn_rate > 0:
            self._frac += self._spawn_rate
            while self._frac >= 1:
                self._coins.append(_Coin(max(self.width(), 100)))
                self._frac -= 1
        # 更新粒子
        self._coins = [c for c in self._coins if c.update()]
        # 超过 200 个截断（防止积压）
        if len(self._coins) > 200:
            self._coins = self._coins[-200:]
        if self._coins:
            self.update()

    def paintEvent(self, event):
        if not self._coins:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for c in self._coins:
            p.save()
            p.translate(c.x, c.y)
            p.rotate(c.rot)
            color = QColor(c.color)
            color.setAlpha(c.alpha)
            p.setPen(Qt.PenStyle.NoPen)
            if c.symbol in ('💰', '💵', '🪙', '💎'):
                # emoji 直接画文字
                f = QFont()
                f.setPixelSize(c.size)
                p.setFont(f)
                p.setPen(color)
                p.drawText(QRect(-c.size, -c.size, c.size*2, c.size*2),
                           Qt.AlignmentFlag.AlignCenter, c.symbol)
            else:
                # ¥ / $ 画带圆底的徽章
                r = c.size // 2
                p.setBrush(QColor(0, 0, 0, int(c.alpha * 0.3)))
                p.drawEllipse(-r, -r, r*2, r*2)
                f = QFont()
                f.setPixelSize(c.size - 2)
                f.setBold(True)
                p.setFont(f)
                p.setPen(color)
                p.drawText(QRect(-r, -r, r*2, r*2),
                           Qt.AlignmentFlag.AlignCenter, c.symbol)
            p.restore()
        p.end()


# ── 励志语句轮播 ──────────────────────────────────────────────────────────────

class QuoteWidget(QWidget):
    """淡入淡出的励志语句标签"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._alpha = 0
        self._fading_in = True
        self._text = ''
        self._recent: list[int] = []   # 最近出现的下标，避免重复

        self._lbl = QLabel(self)
        self._lbl.setWordWrap(True)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._lbl)

        # 渐变 timer
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_tick)

        # 换句子 timer（20~35 秒随机）
        self._change_timer = QTimer(self)
        self._change_timer.timeout.connect(self._schedule_change)

        self._pick_quote()
        self._fade_in()
        self._schedule_change()

    def _pick_quote(self):
        avoid = set(self._recent[-15:])      # 避开最近 15 条
        pool  = [i for i in range(len(_QUOTES)) if i not in avoid]
        if not pool:
            pool = list(range(len(_QUOTES)))
        idx = random.choice(pool)
        self._recent.append(idx)
        if len(self._recent) > 30:
            self._recent.pop(0)
        self._text = _QUOTES[idx]

    def _schedule_change(self):
        interval = random.randint(18000, 32000)   # 18~32 秒
        self._change_timer.start(interval)
        # 先淡出
        self._fading_in = False
        self._fade_timer.start(30)

    def _fade_tick(self):
        if self._fading_in:
            self._alpha = min(255, self._alpha + 12)
            self._update_style()
            if self._alpha >= 255:
                self._fade_timer.stop()
        else:
            self._alpha = max(0, self._alpha - 10)
            self._update_style()
            if self._alpha <= 0:
                self._fade_timer.stop()
                self._pick_quote()
                self._update_style()
                self._fade_in()

    def _fade_in(self):
        self._alpha = 0
        self._fading_in = True
        self._fade_timer.start(25)

    def _update_style(self):
        self._lbl.setText(self._text)
        self._lbl.setStyleSheet(f"""
            color: rgba(180, 210, 240, {self._alpha});
            font-size: 12px;
            letter-spacing: 1px;
            font-style: italic;
        """)


# ── 圆环进度 ──────────────────────────────────────────────────────────────────

class RingProgressWidget(QWidget):
    def __init__(self, size=120, parent=None):
        super().__init__(parent)
        self._pct = 0.0
        self._size = size
        self.setFixedSize(size, size)
        self._phase = 0.0
        t = QTimer(self); t.timeout.connect(self._tick); t.start(50)

    def _tick(self):
        self._phase = (self._phase + 0.05) % (2 * math.pi)
        self.update()

    def set_progress(self, pct: float):
        self._pct = max(0.0, min(1.0, pct))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s, mg = self._size, 12
        rect = QRect(mg, mg, s - 2*mg, s - 2*mg)

        pen = QPen(QColor(NC['border']))
        pen.setWidth(8); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        if self._pct > 0:
            alpha = int(180 + 60 * math.sin(self._phase))
            pen2 = QPen(QColor(79, 195, 247, alpha))
            pen2.setWidth(8); pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen2)
            p.drawArc(rect, 90*16, int(-self._pct * 360 * 16))

        p.setPen(QColor(NC['cyan']))
        f = QFont(); f.setPixelSize(18); f.setBold(True); p.setFont(f)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{int(self._pct*100)}%")
        p.end()


# ── 粒子进度条 ────────────────────────────────────────────────────────────────

class SalaryBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self._pct = 0.0
        self._particles = []
        self._phase = 0.0
        t = QTimer(self); t.timeout.connect(self._tick); t.start(50)

    def set_progress(self, pct: float):
        self._pct = max(0.0, min(1.0, pct))

    def _tick(self):
        self._phase += 0.04
        if self._pct > 0 and random.random() < 0.35:
            self._particles.append([0.0, random.uniform(0.1, 0.9)])
        self._particles = [[x + 0.018, y] for x, y in self._particles if x < 1.1]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.setBrush(QColor(NC['border'])); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, h//2-3, w, 6, 3, 3)

        if self._pct > 0:
            fw = int(w * self._pct)
            g = QLinearGradient(0, 0, fw, 0)
            g.setColorAt(0, QColor('#1565c0'))
            g.setColorAt(0.6, QColor('#4fc3f7'))
            g.setColorAt(1, QColor('#80deea'))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(0, h//2-3, fw, 6, 3, 3)

        for x, y in self._particles:
            px = int(x * w)
            if px > int(w * self._pct):
                continue
            py = int(y * h)
            a = int(200 * (1 - x))
            p.setBrush(QColor(200, 240, 255, a))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(px-2, py-2, 4, 4)
        p.end()


# ── 主 Widget ─────────────────────────────────────────────────────────────────

class SalaryClockWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._prev_earned = 0.0
        self._last_burst_earned = 0.0
        self._session = WorkSession.instance()
        self._session.state_changed.connect(lambda _: self._tick())
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)
        self._tick()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # ── 顶部卡：时钟 + 圆环 ──────────────────────────────────────────────
        top_frame = QFrame()
        top_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #0d1e3a, stop:1 #07111f);
                border: 1px solid {NC['border']};
                border-radius: 12px;
            }}
        """)
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(18, 14, 18, 14)
        top_layout.setSpacing(16)

        self._ring = RingProgressWidget(size=110)
        top_layout.addWidget(self._ring)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)

        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet(f"color:{NC['dim']}; font-size:10px; letter-spacing:2px;")

        self.lbl_time = QLabel()
        self.lbl_time.setStyleSheet(f"color:{NC['cyan']}; font-size:38px; font-weight:bold; letter-spacing:3px;")

        self.lbl_status_emoji = QLabel()
        self.lbl_status_emoji.setStyleSheet("font-size:22px;")
        self.lbl_status_text = QLabel()
        self.lbl_status_text.setStyleSheet(f"color:{NC['dim']}; font-size:11px; letter-spacing:2px;")

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.addWidget(self.lbl_status_emoji)
        status_row.addWidget(self.lbl_status_text)
        status_row.addStretch()

        right_col.addWidget(self.lbl_date)
        right_col.addWidget(self.lbl_time)
        right_col.addLayout(status_row)
        right_col.addStretch()
        top_layout.addLayout(right_col, 1)
        root.addWidget(top_frame)

        # ── 三卡片 ───────────────────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._card_countdown = self._metric_card("⏱ 工作倒计时", "--:--:--", NC['cyan'])
        self._card_earned    = self._metric_card("💰 今日已赚",   "¥ 0.00",  NC['green'])
        self._card_salary    = self._metric_card("🎁 距发薪",     "-- 天",   NC['yellow'])
        cards_row.addWidget(self._card_countdown[0])
        cards_row.addWidget(self._card_earned[0])
        cards_row.addWidget(self._card_salary[0])
        root.addLayout(cards_row)

        # ── 钱雨 + 进度条组合区 ───────────────────────────────────────────────
        rain_frame = QFrame()
        rain_frame.setStyleSheet(f"""
            QFrame {{
                background: {NC['bg_card']};
                border: 1px solid {NC['border']};
                border-radius: 10px;
            }}
        """)
        rain_frame.setMinimumHeight(90)
        rain_layout = QVBoxLayout(rain_frame)
        rain_layout.setContentsMargins(12, 10, 12, 10)
        rain_layout.setSpacing(6)

        bar_header = QHBoxLayout()
        lbl_earn_title = QLabel("TODAY  EARNINGS")
        lbl_earn_title.setStyleSheet(f"color:{NC['dim']}; font-size:10px; letter-spacing:2px;")
        self.lbl_bar_pct = QLabel("0%")
        self.lbl_bar_pct.setStyleSheet(f"color:{NC['cyan']}; font-size:10px;")
        self.lbl_bar_pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        bar_header.addWidget(lbl_earn_title)
        bar_header.addStretch()
        bar_header.addWidget(self.lbl_bar_pct)

        self._salary_bar = SalaryBarWidget()
        rain_layout.addLayout(bar_header)
        rain_layout.addWidget(self._salary_bar)

        # 钱雨覆盖层（透明，叠在 rain_frame 上）
        self._rain = MoneyRainWidget(rain_frame)
        self._rain.setGeometry(0, 0, rain_frame.width(), rain_frame.height())
        rain_frame.resizeEvent = lambda e: self._rain.setGeometry(
            0, 0, rain_frame.width(), rain_frame.height()
        )
        root.addWidget(rain_frame)

        # ── 励志语句 ──────────────────────────────────────────────────────────
        quote_frame = QFrame()
        quote_frame.setFixedHeight(36)
        quote_frame.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border-top: 1px solid {NC['border']};
            }}
        """)
        ql = QVBoxLayout(quote_frame)
        ql.setContentsMargins(4, 4, 4, 4)
        self._quote = QuoteWidget()
        ql.addWidget(self._quote)
        root.addWidget(quote_frame)

        root.addStretch()

    def _metric_card(self, title: str, value: str, color: str):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {NC['bg_card']};
                border: 1px solid {NC['border']};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(3)

        t = QLabel(title)
        t.setStyleSheet(f"color:{NC['dim']}; font-size:10px; letter-spacing:1px;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)

        v = QLabel(value)
        v.setStyleSheet(f"color:{color}; font-size:16px; font-weight:bold;")
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setWordWrap(True)

        lay.addWidget(t)
        lay.addWidget(v)
        return frame, v

    def _tick(self):
        now = datetime.now()
        w   = cfg.load().get('work', {})
        self.lbl_date.setText(now.strftime("%Y · %m · %d  %A").upper())
        self.lbl_time.setText(now.strftime("%H:%M:%S"))

        monthly = w.get('monthly_salary', 20000)
        daily   = monthly / 21.75

        # 工作会话状态
        sess  = self._session
        state = sess.state

        # ── 计算已赚钱数 & 状态文字 ──────────────────────────────────────────
        pct    = 0.0
        earned = 0.0

        if state == WorkState.BEFORE_WORK:
            # 未打卡：按配置时间显示距上班倒计时
            sh, sm = map(int, w.get('start_time', '09:00').split(':'))
            start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if now < start_dt:
                delta = start_dt - now
                h, r = divmod(int(delta.total_seconds()), 3600); m, s = divmod(r, 60)
                self._card_countdown[1].setText(f"{h:02d}:{m:02d}:{s:02d}")
                self._card_countdown[1].setStyleSheet(f"color:{NC['yellow']};font-size:16px;font-weight:bold;")
            else:
                self._card_countdown[1].setText("待打卡")
                self._card_countdown[1].setStyleSheet(f"color:{NC['orange']};font-size:16px;font-weight:bold;")
            self.lbl_status_emoji.setText("🌅")
            self.lbl_status_text.setText("等待打卡上班")
            self._card_earned[1].setText("¥ 0.00")
            self._rain.set_intensity(0)

        elif state in (WorkState.WORKING, WorkState.OVERTIME, WorkState.LUNCH_BREAK):
            # 按实际打卡时间计算工作时长（午休不计）
            work_start = sess.work_start or now
            # 扣掉午休时间
            lunch_dur = 0
            if sess.lunch_start:
                lunch_end_t = sess.lunch_end or (now if state == WorkState.LUNCH_BREAK else now)
                lunch_dur = (lunch_end_t - sess.lunch_start).total_seconds()

            if state == WorkState.LUNCH_BREAK:
                # 午休：不累计时间，显示午休时长
                lb_secs = (now - sess.lunch_start).total_seconds()
                lm, ls  = divmod(int(lb_secs), 60)
                self._card_countdown[1].setText(f"午休 {lm}:{ls:02d}")
                self._card_countdown[1].setStyleSheet(f"color:{NC['orange']};font-size:16px;font-weight:bold;")
                self.lbl_status_emoji.setText("🍜")
                self.lbl_status_text.setText("午休中")
                # 用午休前的已赚
                elapsed = max(0, (sess.lunch_start - work_start).total_seconds())
                # 按8小时标准工作日计算
                work_day_secs = 8 * 3600
                pct    = min(elapsed / work_day_secs, 1.0)
                earned = daily * pct
                self._card_earned[1].setText(f"¥ {earned:,.2f}")
                self._rain.set_intensity(0)
            else:
                # 工作中 / 加班中
                elapsed = max(0, (now - work_start).total_seconds() - lunch_dur)
                work_day_secs = 8 * 3600
                pct    = min(elapsed / work_day_secs, 1.0)
                earned = daily * pct

                # 加班按1.5倍计，超出8小时部分额外计
                if elapsed > work_day_secs:
                    overtime_secs = elapsed - work_day_secs
                    earned = daily + (daily / work_day_secs) * overtime_secs * 1.5

                if state == WorkState.OVERTIME:
                    self.lbl_status_emoji.setText("⚡")
                    self.lbl_status_text.setText("加班中")
                    self._card_countdown[1].setStyleSheet(f"color:{NC['purple']};font-size:16px;font-weight:bold;")
                else:
                    self.lbl_status_emoji.setText("💼")
                    self.lbl_status_text.setText("打工中")
                    self._card_countdown[1].setStyleSheet(f"color:{NC['cyan']};font-size:16px;font-weight:bold;")

                # 剩余时间（距8小时满）
                remain = max(0, work_day_secs - elapsed)
                rh, rr = divmod(int(remain), 3600); rm, rs = divmod(rr, 60)
                if elapsed >= work_day_secs:
                    ot = int(elapsed - work_day_secs)
                    oh, or_ = divmod(ot, 3600); om, os = divmod(or_, 60)
                    self._card_countdown[1].setText(f"+{oh:02d}:{om:02d}:{os:02d}")
                else:
                    self._card_countdown[1].setText(f"{rh:02d}:{rm:02d}:{rs:02d}")

                self._card_earned[1].setText(f"¥ {earned:,.2f}")

                per_second = daily / work_day_secs
                intensity  = min(0.3 + per_second / 0.5, 1.2)
                self._rain.set_intensity(intensity)

                milestone = 10.0
                if int(earned / milestone) > int(self._last_burst_earned / milestone):
                    self._rain.burst(15)
                    self._last_burst_earned = earned

        elif state == WorkState.OFF_WORK:
            work_start = sess.work_start or now
            lunch_dur  = 0
            if sess.lunch_start and sess.lunch_end:
                lunch_dur = (sess.lunch_end - sess.lunch_start).total_seconds()
            work_end = sess.work_end or now
            elapsed  = max(0, (work_end - work_start).total_seconds() - lunch_dur)
            work_day_secs = 8 * 3600
            pct    = min(elapsed / work_day_secs, 1.0)
            earned = daily * pct
            if elapsed > work_day_secs:
                earned = daily + (daily / work_day_secs) * (elapsed - work_day_secs) * 1.5

            self.lbl_status_emoji.setText("🎉")
            self.lbl_status_text.setText("下班了！辛苦了！")
            self._card_countdown[1].setText("DONE ✓")
            self._card_countdown[1].setStyleSheet(f"color:{NC['green']};font-size:16px;font-weight:bold;")
            self._card_earned[1].setText(f"¥ {earned:,.2f}")
            pct = min(pct, 1.0)
            self._rain.set_intensity(0)

        self._ring.set_progress(pct)
        self._salary_bar.set_progress(pct)
        self.lbl_bar_pct.setText(f"{pct*100:.1f}%")
        self._prev_earned = earned

        # ── 发薪倒计时 ────────────────────────────────────────────────────────
        salary_day = w.get('salary_day', 30)
        next_s     = _next_salary_date(salary_day)
        days_left  = (next_s - date.today()).days
        if days_left == 0:
            self._card_salary[1].setText("🎉 今天！")
            self._card_salary[1].setStyleSheet(f"color:{NC['green']};font-size:16px;font-weight:bold;")
        elif days_left <= 3:
            self._card_salary[1].setText(f"🔥 {days_left} 天")
            self._card_salary[1].setStyleSheet(f"color:{NC['orange']};font-size:16px;font-weight:bold;")
        else:
            self._card_salary[1].setText(f"{days_left} 天")
            self._card_salary[1].setStyleSheet(f"color:{NC['yellow']};font-size:16px;font-weight:bold;")
