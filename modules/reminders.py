"""
喝水 / 吃饭 / 站起来动一动 提醒模块
"""
import math
import random
import subprocess
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
)
from PyQt6.QtCore import QTimer, Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QRadialGradient
from modules.theme import NEON_COLORS as NC
from modules.fullscreen_alert import show_water_alert, show_food_alert, show_move_alert
import modules.config_manager as cfg
import modules.health_db as hdb
from modules import reward_engine as re_engine
from modules import reward_popup as rp


def _notify(title: str, body: str):
    try:
        subprocess.Popen(
            ['notify-send', '-i', 'dialog-information', '-t', '5000', title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


# ── 水波涟漪 ──────────────────────────────────────────────────────────────────

class WaterRippleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(140, 140)
        self._pct = 1.0
        self._phase = 0.0
        self._ripples = []
        self._urgent = False
        t = QTimer(self); t.timeout.connect(self._tick); t.start(40)

    def set_remaining_pct(self, pct: float, urgent: bool = False):
        self._pct = max(0.0, min(1.0, pct))
        self._urgent = urgent

    def trigger_ripple(self):
        self._ripples.append([0, 30])

    def _tick(self):
        self._phase += 0.06
        self._ripples = [[a+1, m] for a, m in self._ripples if a < m]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 70, 70, 55
        border_color = NC['red'] if self._urgent else NC['cyan']
        pen = QPen(QColor(border_color)); pen.setWidth(2)
        p.setPen(pen); p.setBrush(QColor(10, 20, 40))
        p.drawEllipse(cx-r, cy-r, 2*r, 2*r)

        p.save()
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addEllipse(cx-r+1, cy-r+1, 2*r-2, 2*r-2)
        p.setClipPath(path)

        water_y = cy + r - int(2*r*self._pct)
        wave_color = QColor('#1a7aad' if not self._urgent else '#8B0000')
        wave_color.setAlpha(160)
        wave_pts = []
        for i in range(2*r+2):
            x = cx - r + i
            y = water_y + int(4*math.sin(self._phase + i*0.18)) + int(2*math.sin(self._phase*1.3 + i*0.12))
            wave_pts.append((x, y))

        from PyQt6.QtGui import QPolygon
        from PyQt6.QtCore import QPoint
        poly_pts = [QPoint(cx-r, cy+r+2), QPoint(cx+r, cy+r+2)]
        for x, y in reversed(wave_pts):
            poly_pts.append(QPoint(x, y))
        p.setBrush(QBrush(wave_color)); p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygon(poly_pts))
        p.restore()

        for age, max_age in self._ripples:
            ratio = age / max_age
            rr = int(r * ratio * 1.2)
            alpha = int(200 * (1 - ratio))
            p.setPen(QPen(QColor(79, 195, 247, alpha), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx-rr, cy-rr, 2*rr, 2*rr)

        p.setPen(QColor('white'))
        f = QFont(); f.setPixelSize(13); f.setBold(True); p.setFont(f)
        if self._urgent:
            p.setPen(QColor(NC['red']))
            p.drawText(QRect(cx-r, cy-15, 2*r, 30), Qt.AlignmentFlag.AlignCenter, "喝水！")
        else:
            p.drawText(QRect(cx-r, cy-15, 2*r, 30), Qt.AlignmentFlag.AlignCenter, f"{int(self._pct*100)}%")
        p.end()


# ── 吃饭扇形盘 ────────────────────────────────────────────────────────────────

class MealCountdownWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 130)
        self._pct = 0.0; self._phase = 0.0
        self._name = "午饭"; self._time_str = "--:--"
        t = QTimer(self); t.timeout.connect(self._tick); t.start(50)

    def set_state(self, pct, name, time_str):
        self._pct = pct; self._name = name; self._time_str = time_str

    def _tick(self):
        self._phase += 0.04; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 65, 65, 52
        rect = QRect(cx-r, cy-r, 2*r, 2*r)
        p.setBrush(QColor(12, 22, 42)); p.setPen(QPen(QColor(NC['border']), 2))
        p.drawEllipse(rect)
        if self._pct > 0:
            glow = int(160 + 60*math.sin(self._phase))
            p.setBrush(QColor(255, 152, 0, glow)); p.setPen(Qt.PenStyle.NoPen)
            p.drawPie(rect, 90*16, int(-self._pct*360*16))
        inner_r = r - 14
        p.setBrush(QColor(10, 18, 32)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx-inner_r, cy-inner_r, 2*inner_r, 2*inner_r)
        p.setPen(QColor(NC['orange']))
        f = QFont(); f.setPixelSize(11); f.setBold(True); p.setFont(f)
        p.drawText(QRect(cx-inner_r, cy-16, 2*inner_r, 16), Qt.AlignmentFlag.AlignCenter, self._name)
        f2 = QFont(); f2.setPixelSize(10); p.setFont(f2)
        p.setPen(QColor(NC['dim']))
        p.drawText(QRect(cx-inner_r, cy+2, 2*inner_r, 14), Qt.AlignmentFlag.AlignCenter, self._time_str)
        p.end()


# ── 站立计时器（人形动画） ────────────────────────────────────────────────────

class MoveTimerWidget(QWidget):
    """跑步小人动画 + 环形进度"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 130)
        self._pct = 1.0   # 剩余时间比例
        self._phase = 0.0
        self._urgent = False
        t = QTimer(self); t.timeout.connect(self._tick); t.start(40)

    def set_state(self, pct: float, urgent: bool = False):
        self._pct = max(0.0, min(1.0, pct))
        self._urgent = urgent

    def _tick(self):
        self._phase = (self._phase + 0.08) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = 65, 65

        # 外环背景
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(NC['border']), 6))
        p.drawEllipse(10, 10, 110, 110)

        # 绿色进度弧
        if self._pct > 0:
            color = QColor(NC['red']) if self._urgent else QColor(0, 230, 118)
            glow_a = int(180 + 60 * math.sin(self._phase))
            color.setAlpha(glow_a)
            pen = QPen(color, 6); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(QRect(10, 10, 110, 110), 90*16, int(-self._pct * 360 * 16))

        # 跑步小人（用简单线条画）
        bounce = int(5 * math.sin(self._phase * 2))  # 上下弹跳
        arm_swing = int(12 * math.sin(self._phase))   # 手臂摆动
        leg_swing = int(10 * math.sin(self._phase))   # 腿部摆动

        color_body = QColor(NC['green']) if not self._urgent else QColor(NC['red'])
        pen_body = QPen(color_body, 3); pen_body.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_body); p.setBrush(QBrush(color_body))

        # 头
        head_y = cy - 20 + bounce
        p.drawEllipse(cx-7, head_y-7, 14, 14)

        # 身体
        p.drawLine(cx, head_y+7, cx, head_y+24)

        # 左臂
        p.drawLine(cx, head_y+12, cx - arm_swing, head_y+20)
        # 右臂
        p.drawLine(cx, head_y+12, cx + arm_swing, head_y+20)

        # 左腿
        p.drawLine(cx, head_y+24, cx - leg_swing, head_y+38)
        # 右腿
        p.drawLine(cx, head_y+24, cx + leg_swing, head_y+38)

        # 中心倒计时文字
        f = QFont(); f.setPixelSize(11); f.setBold(True); p.setFont(f)
        p.setPen(QColor(NC['dim']))
        pct_text = f"{int(self._pct*100)}%"
        if self._urgent:
            p.setPen(QColor(NC['red']))
            pct_text = "动！"
        # 在小人下方
        p.drawText(QRect(cx-30, head_y+42, 60, 16), Qt.AlignmentFlag.AlignCenter, pct_text)
        p.end()


# ── 主 Widget ─────────────────────────────────────────────────────────────────

class RemindersWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_water = datetime.now()
        self._last_move  = datetime.now()
        self._notified_water = False
        self._notified_move  = False
        self._last_lunch_date  = None
        self._last_dinner_date = None
        self._water_count_today = 0
        self._water_count_date  = datetime.now().date()
        self._move_count_today  = 0
        self._move_count_date   = datetime.now().date()
        self._daily_score_shown = None   # 当日评分是否已弹出
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        root.addWidget(self._build_water_card())
        root.addWidget(self._build_move_card())
        root.addWidget(self._build_meal_card())
        root.addStretch()

    # ── 喝水卡片 ─────────────────────────────────────────────────────────────

    def _build_water_card(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #071828, stop:1 #050e1c);
                border: 1px solid {NC['border']};
                border-radius: 12px;
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)

        self._water_ripple = WaterRippleWidget()
        lay.addWidget(self._water_ripple)

        right = QVBoxLayout(); right.setSpacing(5)

        title_row = QHBoxLayout()
        lbl_title = QLabel("💧  WATER REMINDER")
        lbl_title.setStyleSheet(f"color:{NC['cyan']};font-size:11px;letter-spacing:2px;")
        self.lbl_water_count = QLabel("今日 0 杯")
        self.lbl_water_count.setStyleSheet(f"color:{NC['green']};font-size:11px;")
        self.lbl_water_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(lbl_title); title_row.addStretch()
        title_row.addWidget(self.lbl_water_count)

        self.lbl_water_countdown = QLabel("00:00")
        self.lbl_water_countdown.setStyleSheet(
            f"color:{NC['cyan']};font-size:32px;font-weight:bold;letter-spacing:2px;")

        self.lbl_water_tip = QLabel()
        self.lbl_water_tip.setStyleSheet(f"color:{NC['dim']};font-size:11px;")

        btn = QPushButton("✓  喝了！")
        btn.setStyleSheet(f"""
            QPushButton {{background:#071e12;color:{NC['green']};border:1px solid #1a4a2a;
            border-radius:6px;padding:6px 18px;font-size:12px;}}
            QPushButton:hover {{background:#0d2a1a;border-color:{NC['green']};}}
        """)
        btn.clicked.connect(self._reset_water)

        right.addLayout(title_row)
        right.addWidget(self.lbl_water_countdown)
        right.addWidget(self.lbl_water_tip)
        right.addStretch()
        right.addWidget(btn)
        lay.addLayout(right, 1)
        return frame

    # ── 站立提醒卡片 ─────────────────────────────────────────────────────────

    def _build_move_card(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #071a0d, stop:1 #050f07);
                border: 1px solid {NC['border']};
                border-radius: 12px;
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)

        self._move_timer_widget = MoveTimerWidget()
        lay.addWidget(self._move_timer_widget)

        right = QVBoxLayout(); right.setSpacing(5)

        title_row = QHBoxLayout()
        lbl_title = QLabel("🏃  MOVE REMINDER")
        lbl_title.setStyleSheet(f"color:{NC['green']};font-size:11px;letter-spacing:2px;")
        self.lbl_move_count = QLabel("今日起身 0 次")
        self.lbl_move_count.setStyleSheet(f"color:{NC['green']};font-size:11px;")
        self.lbl_move_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(lbl_title); title_row.addStretch()
        title_row.addWidget(self.lbl_move_count)

        self.lbl_move_countdown = QLabel("00:00")
        self.lbl_move_countdown.setStyleSheet(
            f"color:{NC['green']};font-size:32px;font-weight:bold;letter-spacing:2px;")

        self.lbl_move_tip = QLabel()
        self.lbl_move_tip.setStyleSheet(f"color:{NC['dim']};font-size:11px;")

        btn = QPushButton("🦵  动了！")
        btn.setStyleSheet(f"""
            QPushButton {{background:#071a07;color:{NC['green']};border:1px solid #1a4a1a;
            border-radius:6px;padding:6px 18px;font-size:12px;}}
            QPushButton:hover {{background:#0d2a0d;border-color:{NC['green']};}}
        """)
        btn.clicked.connect(self._reset_move)

        right.addLayout(title_row)
        right.addWidget(self.lbl_move_countdown)
        right.addWidget(self.lbl_move_tip)
        right.addStretch()
        right.addWidget(btn)
        lay.addLayout(right, 1)
        return frame

    # ── 吃饭卡片 ─────────────────────────────────────────────────────────────

    def _build_meal_card(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #1a0e05, stop:1 #0e0a05);
                border: 1px solid {NC['border']};
                border-radius: 12px;
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)

        self._meal_clock = MealCountdownWidget()
        lay.addWidget(self._meal_clock)

        right = QVBoxLayout(); right.setSpacing(5)
        lbl_title = QLabel("🍱  MEAL REMINDER")
        lbl_title.setStyleSheet(f"color:{NC['orange']};font-size:11px;letter-spacing:2px;")

        self.lbl_meal_countdown = QLabel("--:--:--")
        self.lbl_meal_countdown.setStyleSheet(
            f"color:{NC['orange']};font-size:28px;font-weight:bold;letter-spacing:2px;")

        self.lbl_meal_tip = QLabel()
        self.lbl_meal_tip.setStyleSheet(f"color:{NC['dim']};font-size:11px;")

        right.addWidget(lbl_title)
        right.addWidget(self.lbl_meal_countdown)
        right.addWidget(self.lbl_meal_tip)
        right.addStretch()
        lay.addLayout(right, 1)
        return frame

    # ── 重置 ──────────────────────────────────────────────────────────────────

    def _reset_water(self):
        today = datetime.now().date()
        if self._water_count_date != today:
            self._water_count_today = 0
            self._water_count_date = today
        self._water_count_today += 1
        self._last_water = datetime.now()
        self._notified_water = False
        self._water_ripple.trigger_ripple()
        hdb.log(hdb.TYPE_WATER, hdb.ACT_COMPLETED)

        # ── 奖励 ──
        count = self._water_count_today
        title, body, milestone = re_engine.get_praise(hdb.TYPE_WATER, count)
        theme = 'milestone' if milestone else 'water'
        rp.show_reward(title, body, theme)

        # 连续打卡成就
        ach = re_engine.check_streak_achievement(hdb.TYPE_WATER)
        if ach:
            badge, atitle, abody = ach
            QTimer.singleShot(800, lambda: rp.show_streak(f"{badge} {atitle}", abody))

        cup_emoji = "🎊" if count >= 8 else ("🎯" if count >= 6 else "💧")
        self.lbl_water_count.setText(f"今日 {count} 杯 {cup_emoji}")
        tip = re_engine.get_encouragement_for_count(hdb.TYPE_WATER, count)
        self.lbl_water_tip.setText(tip)

    def _reset_move(self):
        today = datetime.now().date()
        if self._move_count_date != today:
            self._move_count_today = 0
            self._move_count_date = today
        self._move_count_today += 1
        self._last_move = datetime.now()
        self._notified_move = False
        hdb.log(hdb.TYPE_MOVE, hdb.ACT_COMPLETED)

        # ── 奖励 ──
        count = self._move_count_today
        title, body, milestone = re_engine.get_praise(hdb.TYPE_MOVE, count)
        theme = 'milestone' if milestone else 'move'
        rp.show_reward(title, body, theme)

        ach = re_engine.check_streak_achievement(hdb.TYPE_MOVE)
        if ach:
            badge, atitle, abody = ach
            QTimer.singleShot(800, lambda: rp.show_streak(f"{badge} {atitle}", abody))

        move_emoji = "🏆" if count >= 8 else ("⚡" if count >= 5 else "🦵")
        self.lbl_move_count.setText(f"今日起身 {count} 次 {move_emoji}")
        tip = re_engine.get_encouragement_for_count(hdb.TYPE_MOVE, count)
        self.lbl_move_tip.setText(tip)

    # ── 主 tick ───────────────────────────────────────────────────────────────

    def _tick(self):
        now = datetime.now()
        reminders = cfg.load().get('reminders', {})

        # ── 喝水 ──
        water_interval = cfg.get('reminders.water_interval_minutes', 60)
        next_water = self._last_water + timedelta(minutes=water_interval)
        water_rem  = (next_water - now).total_seconds()
        water_total = water_interval * 60

        if water_rem <= 0:
            self.lbl_water_countdown.setText("喝水啦！")
            self.lbl_water_countdown.setStyleSheet(
                f"color:{NC['red']};font-size:26px;font-weight:bold;")
            self.lbl_water_tip.setText('点「喝了！」重置计时')
            self._water_ripple.set_remaining_pct(0.0, urgent=True)
            if not self._notified_water:
                self._notified_water = True
                hdb.log(hdb.TYPE_WATER, hdb.ACT_TRIGGERED)
                self._water_alert = show_water_alert()
                self._water_alert.dismissed.connect(self._reset_water)
        else:
            m, s = divmod(int(water_rem), 60)
            urgent = water_rem < 300
            color = NC['orange'] if urgent else NC['cyan']
            self.lbl_water_countdown.setText(f"{m:02d}:{s:02d}")
            self.lbl_water_countdown.setStyleSheet(
                f"color:{color};font-size:32px;font-weight:bold;letter-spacing:2px;")
            self.lbl_water_tip.setText(
                f"下次: {next_water.strftime('%H:%M')}  |  间隔 {water_interval} 分钟")
            self._water_ripple.set_remaining_pct(water_rem / water_total, urgent=urgent)
            self._notified_water = False

        # ── 站立 ──
        move_interval = cfg.get('reminders.move_interval_minutes', 45)
        next_move = self._last_move + timedelta(minutes=move_interval)
        move_rem  = (next_move - now).total_seconds()
        move_total = move_interval * 60

        if move_rem <= 0:
            self.lbl_move_countdown.setText("快站起来！")
            self.lbl_move_countdown.setStyleSheet(
                f"color:{NC['red']};font-size:22px;font-weight:bold;")
            self.lbl_move_tip.setText('点「动了！」重置计时')
            self._move_timer_widget.set_state(0.0, urgent=True)
            if not self._notified_move:
                self._notified_move = True
                hdb.log(hdb.TYPE_MOVE, hdb.ACT_TRIGGERED)
                self._move_alert = show_move_alert()
                self._move_alert.dismissed.connect(self._reset_move)
        else:
            m, s = divmod(int(move_rem), 60)
            urgent = move_rem < 300
            color = NC['orange'] if urgent else NC['green']
            self.lbl_move_countdown.setText(f"{m:02d}:{s:02d}")
            self.lbl_move_countdown.setStyleSheet(
                f"color:{color};font-size:32px;font-weight:bold;letter-spacing:2px;")
            self.lbl_move_tip.setText(
                f"下次起身: {next_move.strftime('%H:%M')}  |  已坐 {int((move_total-move_rem)//60)} 分钟")
            self._move_timer_widget.set_state(move_rem / move_total, urgent=urgent)
            self._notified_move = False

        # ── 吃饭 ──
        today = now.date()
        meals = [
            ('lunch',  reminders.get('lunch_time', '12:00'),  '午饭',  self._last_lunch_date),
            ('dinner', reminders.get('dinner_time', '18:30'), '晚饭', self._last_dinner_date),
        ]
        for key, tstr, name, last_date in meals:
            h, m = map(int, tstr.split(':'))
            meal_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if abs((meal_dt - now).total_seconds()) <= 120 and last_date != today:
                if key == 'lunch':
                    self._last_lunch_date = today
                else:
                    self._last_dinner_date = today
                hdb.log(hdb.TYPE_MEAL, hdb.ACT_TRIGGERED, name)
                hdb.log(hdb.TYPE_MEAL, hdb.ACT_COMPLETED, name)
                self._food_alert = show_food_alert()

        upcoming = []
        for key, tstr, name, _ in meals:
            h, m = map(int, tstr.split(':'))
            meal_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff = (meal_dt - now).total_seconds()
            if diff > 0:
                upcoming.append((name, diff, meal_dt))

        if upcoming:
            name, diff, meal_dt = min(upcoming, key=lambda x: x[1])
            h2, rem = divmod(int(diff), 3600)
            m2, s2 = divmod(rem, 60)
            self.lbl_meal_countdown.setText(f"{h2:02d}:{m2:02d}:{s2:02d}")
            self.lbl_meal_tip.setText(f"{name}  {meal_dt.strftime('%H:%M')}")
            self._meal_clock.set_state(min(diff/7200, 1.0), name, meal_dt.strftime('%H:%M'))
        else:
            self.lbl_meal_countdown.setText("--:--:--")
            self.lbl_meal_tip.setText("今日用餐完毕 🌙")
            self._meal_clock.set_state(0, "晚安", "--:--")

        # ── 下班后弹今日综合评分（每天只弹一次）──
        work = cfg.load().get('work', {})
        eh, em = map(int, work.get('end_time', '18:00').split(':'))
        end_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
        just_off = 0 <= (now - end_dt).total_seconds() <= 60
        if just_off and self._daily_score_shown != now.date():
            self._daily_score_shown = now.date()
            score, stitle, sbody = re_engine.daily_score()
            QTimer.singleShot(2000, lambda: rp.show_daily_score(score, stitle, sbody))
