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
from PyQt6.QtCore import QTimer, Qt, QRect, QPoint
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QBrush,
    QPainterPath, QPolygon, QLinearGradient
)
from modules.theme import NEON_COLORS as NC
from modules.fullscreen_alert import show_water_alert, show_food_alert, show_move_alert
import modules.config_manager as cfg
import modules.health_db as hdb
from modules import reward_engine as re_engine
from modules import reward_popup as rp
from modules.punch_panel import PunchPanel
from modules.work_session import WorkSession, WorkState


def _notify(title: str, body: str):
    try:
        subprocess.Popen(
            ['notify-send', '-i', 'dialog-information', '-t', '5000', title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


# ── 水波涟漪（80×80）────────────────────────────────────────────────────────

class WaterRippleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._pct = 1.0
        self._phase = 0.0
        self._ripples = []
        self._urgent = False
        t = QTimer(self); t.timeout.connect(self._tick); t.start(40)

    def set_remaining_pct(self, pct: float, urgent: bool = False):
        self._pct = max(0.0, min(1.0, pct))
        self._urgent = urgent

    def trigger_ripple(self):
        self._ripples.append([0, 25])

    def _tick(self):
        self._phase += 0.07
        self._ripples = [[a+1, m] for a, m in self._ripples if a < m]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 40, 40, 33
        border_color = NC['red'] if self._urgent else NC['cyan']
        pen = QPen(QColor(border_color)); pen.setWidth(2)
        p.setPen(pen); p.setBrush(QColor(10, 20, 40))
        p.drawEllipse(cx-r, cy-r, 2*r, 2*r)

        p.save()
        path = QPainterPath()
        path.addEllipse(cx-r+1, cy-r+1, 2*r-2, 2*r-2)
        p.setClipPath(path)

        water_y = cy + r - int(2*r*self._pct)
        wave_color = QColor('#1a7aad' if not self._urgent else '#8B0000')
        wave_color.setAlpha(160)
        wave_pts = []
        for i in range(2*r+2):
            x = cx - r + i
            y = water_y + int(3*math.sin(self._phase + i*0.22)) + int(1.5*math.sin(self._phase*1.3 + i*0.15))
            wave_pts.append((x, y))

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
            p.setPen(QPen(QColor(79, 195, 247, alpha), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx-rr, cy-rr, 2*rr, 2*rr)

        f = QFont(); f.setPixelSize(11); f.setBold(True); p.setFont(f)
        if self._urgent:
            p.setPen(QColor(NC['red']))
            p.drawText(QRect(cx-r, cy-10, 2*r, 20), Qt.AlignmentFlag.AlignCenter, "喝水！")
        else:
            p.setPen(QColor('white'))
            p.drawText(QRect(cx-r, cy-10, 2*r, 20), Qt.AlignmentFlag.AlignCenter, f"{int(self._pct*100)}%")
        p.end()


# ── 吃饭扇形盘（80×80）──────────────────────────────────────────────────────

class MealCountdownWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
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
        cx, cy, r = 40, 40, 33
        rect = QRect(cx-r, cy-r, 2*r, 2*r)
        p.setBrush(QColor(12, 22, 42)); p.setPen(QPen(QColor(NC['border']), 2))
        p.drawEllipse(rect)
        if self._pct > 0:
            glow = int(160 + 60*math.sin(self._phase))
            p.setBrush(QColor(255, 152, 0, glow)); p.setPen(Qt.PenStyle.NoPen)
            p.drawPie(rect, 90*16, int(-self._pct*360*16))
        inner_r = r - 9
        p.setBrush(QColor(10, 18, 32)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx-inner_r, cy-inner_r, 2*inner_r, 2*inner_r)
        p.setPen(QColor(NC['orange']))
        f = QFont(); f.setPixelSize(10); f.setBold(True); p.setFont(f)
        p.drawText(QRect(cx-inner_r, cy-11, 2*inner_r, 13), Qt.AlignmentFlag.AlignCenter, self._name)
        f2 = QFont(); f2.setPixelSize(9); p.setFont(f2)
        p.setPen(QColor(NC['dim']))
        p.drawText(QRect(cx-inner_r, cy+2, 2*inner_r, 12), Qt.AlignmentFlag.AlignCenter, self._time_str)
        p.end()


# ── 站立计时器（80×80）──────────────────────────────────────────────────────

class MoveTimerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._pct = 1.0
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
        cx, cy = 40, 40

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(NC['border']), 4))
        p.drawEllipse(4, 4, 72, 72)

        if self._pct > 0:
            color = QColor(NC['red']) if self._urgent else QColor(0, 230, 118)
            glow_a = int(180 + 60 * math.sin(self._phase))
            color.setAlpha(glow_a)
            pen = QPen(color, 4); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(QRect(4, 4, 72, 72), 90*16, int(-self._pct * 360 * 16))

        bounce     = int(3 * math.sin(self._phase * 2))
        arm_swing  = int(8 * math.sin(self._phase))
        leg_swing  = int(7 * math.sin(self._phase))

        color_body = QColor(NC['green']) if not self._urgent else QColor(NC['red'])
        pen_body = QPen(color_body, 2); pen_body.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_body); p.setBrush(QBrush(color_body))

        head_y = cy - 14 + bounce
        p.drawEllipse(cx-5, head_y-5, 10, 10)
        p.drawLine(cx, head_y+5, cx, head_y+18)
        p.drawLine(cx, head_y+9,  cx - arm_swing, head_y+15)
        p.drawLine(cx, head_y+9,  cx + arm_swing, head_y+15)
        p.drawLine(cx, head_y+18, cx - leg_swing, head_y+29)
        p.drawLine(cx, head_y+18, cx + leg_swing, head_y+29)

        f = QFont(); f.setPixelSize(10); f.setBold(True); p.setFont(f)
        if self._urgent:
            p.setPen(QColor(NC['red']))
            p.drawText(QRect(cx-25, head_y+31, 50, 14), Qt.AlignmentFlag.AlignCenter, "动！")
        else:
            p.setPen(QColor(NC['dim']))
            p.drawText(QRect(cx-25, head_y+31, 50, 14), Qt.AlignmentFlag.AlignCenter, f"{int(self._pct*100)}%")
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
        self._daily_score_shown = None
        self._session = WorkSession.instance()
        self._build_ui()
        self._load_today_progress_from_db()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 12, 14, 12)

        # ── 打卡面板 ──────────────────────────────────────────────────────────
        self._punch_panel = PunchPanel()
        root.addWidget(self._punch_panel)

        # ── 三个提醒卡 ────────────────────────────────────────────────────────
        root.addWidget(self._build_water_card())
        root.addWidget(self._build_move_card())
        root.addWidget(self._build_meal_card())
        root.addStretch()

    # ── 通用卡片框架 ──────────────────────────────────────────────────────────

    def _card_frame(self, bg_start, bg_end) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {bg_start}, stop:1 {bg_end});
                border: 1px solid {NC['border']};
                border-radius: 12px;
            }}
        """)
        return f

    def _action_btn(self, text, fg, bg, border) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(80, 36)
        btn.setStyleSheet(f"""
            QPushButton {{
                background:{bg}; color:{fg};
                border:1px solid {border}; border-radius:8px;
                font-size:12px; font-weight:bold;
            }}
            QPushButton:hover {{
                background:{border}22; border-color:{fg};
            }}
            QPushButton:pressed {{ background:{border}44; }}
        """)
        return btn

    # ── 喝水卡片 ──────────────────────────────────────────────────────────────

    def _build_water_card(self):
        frame = self._card_frame('#071828', '#050e1c')
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)

        self._water_ripple = WaterRippleWidget()
        lay.addWidget(self._water_ripple)

        mid = QVBoxLayout(); mid.setSpacing(3)

        # 标题行：图标 + 次数
        title_row = QHBoxLayout(); title_row.setSpacing(6)
        lbl_t = QLabel("💧 WATER")
        lbl_t.setStyleSheet(f"color:{NC['cyan']};font-size:11px;letter-spacing:2px;font-weight:bold;")
        self.lbl_water_count = QLabel("今日 0 杯")
        self.lbl_water_count.setStyleSheet(f"color:{NC['green']};font-size:11px;")
        self.lbl_water_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(lbl_t); title_row.addStretch(); title_row.addWidget(self.lbl_water_count)

        # 大倒计时
        self.lbl_water_countdown = QLabel("--:--")
        self.lbl_water_countdown.setStyleSheet(
            f"color:{NC['cyan']};font-size:34px;font-weight:bold;letter-spacing:3px;")

        # 小提示
        self.lbl_water_tip = QLabel("等待开始...")
        self.lbl_water_tip.setStyleSheet(f"color:{NC['dim']};font-size:10px;")

        mid.addLayout(title_row)
        mid.addWidget(self.lbl_water_countdown)
        mid.addWidget(self.lbl_water_tip)

        # 按钮
        btn = self._action_btn("💧 喝了！", NC['cyan'], '#050e1c', NC['cyan'])
        btn.clicked.connect(self._reset_water)

        lay.addLayout(mid, 1)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return frame

    # ── 站立卡片 ──────────────────────────────────────────────────────────────

    def _build_move_card(self):
        frame = self._card_frame('#071a0d', '#050f07')
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)

        self._move_timer_widget = MoveTimerWidget()
        lay.addWidget(self._move_timer_widget)

        mid = QVBoxLayout(); mid.setSpacing(3)

        title_row = QHBoxLayout(); title_row.setSpacing(6)
        lbl_t = QLabel("🏃 MOVE")
        lbl_t.setStyleSheet(f"color:{NC['green']};font-size:11px;letter-spacing:2px;font-weight:bold;")
        self.lbl_move_count = QLabel("今日 0 次")
        self.lbl_move_count.setStyleSheet(f"color:{NC['green']};font-size:11px;")
        self.lbl_move_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(lbl_t); title_row.addStretch(); title_row.addWidget(self.lbl_move_count)

        self.lbl_move_countdown = QLabel("--:--")
        self.lbl_move_countdown.setStyleSheet(
            f"color:{NC['green']};font-size:34px;font-weight:bold;letter-spacing:3px;")

        self.lbl_move_tip = QLabel("等待开始...")
        self.lbl_move_tip.setStyleSheet(f"color:{NC['dim']};font-size:10px;")

        mid.addLayout(title_row)
        mid.addWidget(self.lbl_move_countdown)
        mid.addWidget(self.lbl_move_tip)

        btn = self._action_btn("🦵 动了！", NC['green'], '#050f07', NC['green'])
        btn.clicked.connect(self._reset_move)

        lay.addLayout(mid, 1)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return frame

    # ── 吃饭卡片 ──────────────────────────────────────────────────────────────

    def _build_meal_card(self):
        frame = self._card_frame('#1a0e05', '#0e0a05')
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)

        self._meal_clock = MealCountdownWidget()
        lay.addWidget(self._meal_clock)

        mid = QVBoxLayout(); mid.setSpacing(3)

        lbl_t = QLabel("🍱 MEAL")
        lbl_t.setStyleSheet(f"color:{NC['orange']};font-size:11px;letter-spacing:2px;font-weight:bold;")

        self.lbl_meal_countdown = QLabel("--:--:--")
        self.lbl_meal_countdown.setStyleSheet(
            f"color:{NC['orange']};font-size:34px;font-weight:bold;letter-spacing:3px;")

        self.lbl_meal_tip = QLabel("计算中...")
        self.lbl_meal_tip.setStyleSheet(f"color:{NC['dim']};font-size:10px;")

        mid.addWidget(lbl_t)
        mid.addWidget(self.lbl_meal_countdown)
        mid.addWidget(self.lbl_meal_tip)

        lay.addLayout(mid, 1)
        return frame

    # ── 数据 ──────────────────────────────────────────────────────────────────

    def _load_today_progress_from_db(self):
        today = datetime.now().date()
        summary = hdb.daily_summary(today.isoformat())
        self._water_count_today = summary.get(hdb.TYPE_WATER, {}).get(hdb.ACT_COMPLETED, 0)
        self._move_count_today  = summary.get(hdb.TYPE_MOVE,  {}).get(hdb.ACT_COMPLETED, 0)
        self._water_count_date  = today
        self._move_count_date   = today
        self._refresh_counts()

    def _refresh_counts(self):
        wc = self._water_count_today
        mc = self._move_count_today
        cup  = "🎊" if wc >= 8 else ("🎯" if wc >= 6 else "💧")
        move = "🏆" if mc >= 8 else ("⚡" if mc >= 5 else "🦵")
        self.lbl_water_count.setText(f"今日 {wc} 杯 {cup}")
        self.lbl_move_count.setText(f"今日 {mc} 次 {move}")

    # ── 重置 ──────────────────────────────────────────────────────────────────

    def _reset_water(self, from_alert: bool = False):
        today = datetime.now().date()
        if self._water_count_date != today:
            self._water_count_today = 0
            self._water_count_date  = today
        self._water_count_today += 1
        self._last_water     = datetime.now()
        self._notified_water = False
        self._water_ripple.trigger_ripple()
        if not from_alert:
            hdb.log(hdb.TYPE_WATER, hdb.ACT_COMPLETED)

        count = self._water_count_today
        title, body, milestone = re_engine.get_praise(hdb.TYPE_WATER, count)
        rp.show_reward(title, body, 'milestone' if milestone else 'water')

        ach = re_engine.check_streak_achievement(hdb.TYPE_WATER)
        if ach:
            badge, atitle, abody = ach
            QTimer.singleShot(800, lambda: rp.show_streak(f"{badge} {atitle}", abody))

        self._refresh_counts()

    def _reset_move(self, from_alert: bool = False):
        today = datetime.now().date()
        if self._move_count_date != today:
            self._move_count_today = 0
            self._move_count_date  = today
        self._move_count_today += 1
        self._last_move     = datetime.now()
        self._notified_move = False
        if not from_alert:
            hdb.log(hdb.TYPE_MOVE, hdb.ACT_COMPLETED)

        count = self._move_count_today
        title, body, milestone = re_engine.get_praise(hdb.TYPE_MOVE, count)
        rp.show_reward(title, body, 'milestone' if milestone else 'move')

        ach = re_engine.check_streak_achievement(hdb.TYPE_MOVE)
        if ach:
            badge, atitle, abody = ach
            QTimer.singleShot(800, lambda: rp.show_streak(f"{badge} {atitle}", abody))

        self._refresh_counts()

    # ── 主 tick ───────────────────────────────────────────────────────────────

    def _tick(self):
        now      = datetime.now()
        reminder = cfg.load().get('reminders', {})

        if self._water_count_date != now.date() or self._move_count_date != now.date():
            self._load_today_progress_from_db()

        # 午休 / 下班：暂停水和动的计时
        sess_state = self._session.state
        in_break   = sess_state in (WorkState.LUNCH_BREAK, WorkState.OFF_WORK)
        if in_break:
            self._last_water     = now
            self._last_move      = now
            self._notified_water = False
            self._notified_move  = False
            pause_style = f"color:{NC['dim']};font-size:22px;font-weight:bold;"
            self.lbl_water_countdown.setText("休息中")
            self.lbl_water_countdown.setStyleSheet(pause_style)
            self.lbl_water_tip.setText("休息 / 下班期间暂停")
            self._water_ripple.set_remaining_pct(1.0, urgent=False)
            self.lbl_move_countdown.setText("休息中")
            self.lbl_move_countdown.setStyleSheet(pause_style)
            self.lbl_move_tip.setText("休息 / 下班期间暂停")
            self._move_timer_widget.set_state(1.0, urgent=False)
            self._tick_meal(now, reminder)
            return

        # ── 喝水倒计时 ────────────────────────────────────────────────────────
        water_interval = cfg.get('reminders.water_interval_minutes', 60)
        next_water     = self._last_water + timedelta(minutes=water_interval)
        water_rem      = (next_water - now).total_seconds()
        water_total    = water_interval * 60

        if water_rem <= 0:
            self.lbl_water_countdown.setText("喝水啦！")
            self.lbl_water_countdown.setStyleSheet(
                f"color:{NC['red']};font-size:26px;font-weight:bold;")
            self.lbl_water_tip.setText("点「喝了！」重置计时")
            self._water_ripple.set_remaining_pct(0.0, urgent=True)
            if not self._notified_water:
                self._notified_water = True
                hdb.log(hdb.TYPE_WATER, hdb.ACT_TRIGGERED)
                self._water_alert = show_water_alert()
                self._water_alert.confirmed.connect(lambda: self._reset_water(from_alert=True))
                self._water_alert.dismissed.connect(lambda: setattr(self, '_notified_water', False))
        else:
            m, s = divmod(int(water_rem), 60)
            urgent = water_rem < 300
            color  = NC['orange'] if urgent else NC['cyan']
            self.lbl_water_countdown.setText(f"{m:02d}:{s:02d}")
            self.lbl_water_countdown.setStyleSheet(
                f"color:{color};font-size:34px;font-weight:bold;letter-spacing:3px;")
            self.lbl_water_tip.setText(
                f"下次 {next_water.strftime('%H:%M')}  ·  间隔 {water_interval} min")
            self._water_ripple.set_remaining_pct(water_rem / water_total, urgent=urgent)
            self._notified_water = False

        # ── 站立倒计时 ────────────────────────────────────────────────────────
        move_interval = cfg.get('reminders.move_interval_minutes', 45)
        next_move     = self._last_move + timedelta(minutes=move_interval)
        move_rem      = (next_move - now).total_seconds()
        move_total    = move_interval * 60

        if move_rem <= 0:
            self.lbl_move_countdown.setText("站起来！")
            self.lbl_move_countdown.setStyleSheet(
                f"color:{NC['red']};font-size:26px;font-weight:bold;")
            self.lbl_move_tip.setText("点「动了！」重置计时")
            self._move_timer_widget.set_state(0.0, urgent=True)
            if not self._notified_move:
                self._notified_move = True
                hdb.log(hdb.TYPE_MOVE, hdb.ACT_TRIGGERED)
                self._move_alert = show_move_alert()
                self._move_alert.confirmed.connect(lambda: self._reset_move(from_alert=True))
                self._move_alert.dismissed.connect(lambda: setattr(self, '_notified_move', False))
        else:
            m, s = divmod(int(move_rem), 60)
            urgent = move_rem < 300
            color  = NC['orange'] if urgent else NC['green']
            self.lbl_move_countdown.setText(f"{m:02d}:{s:02d}")
            self.lbl_move_countdown.setStyleSheet(
                f"color:{color};font-size:34px;font-weight:bold;letter-spacing:3px;")
            self.lbl_move_tip.setText(
                f"下次 {next_move.strftime('%H:%M')}  ·  已坐 {int((move_total-move_rem)//60)} min")
            self._move_timer_widget.set_state(move_rem / move_total, urgent=urgent)
            self._notified_move = False

        self._tick_meal(now, reminder)

        # 下班后弹今日综合评分（每天只弹一次）
        work = cfg.load().get('work', {})
        eh, em = map(int, work.get('end_time', '18:00').split(':'))
        end_dt   = now.replace(hour=eh, minute=em, second=0, microsecond=0)
        just_off = 0 <= (now - end_dt).total_seconds() <= 60
        if just_off and self._daily_score_shown != now.date():
            self._daily_score_shown = now.date()
            score, stitle, sbody = re_engine.daily_score()
            QTimer.singleShot(2000, lambda: rp.show_daily_score(score, stitle, sbody))

    def _tick_meal(self, now, reminders):
        today = now.date()
        meals = [
            ('lunch',  reminders.get('lunch_time',  '12:00'), '午饭', self._last_lunch_date),
            ('dinner', reminders.get('dinner_time', '18:30'), '晚饭', self._last_dinner_date),
        ]
        for key, tstr, name, last_date in meals:
            h, m = map(int, tstr.split(':'))
            meal_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if abs((meal_dt - now).total_seconds()) <= 120 and last_date != today:
                if key == 'lunch':
                    self._last_lunch_date  = today
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
            h2, rem = divmod(int(diff), 3600); m2, s2 = divmod(rem, 60)
            self.lbl_meal_countdown.setText(f"{h2:02d}:{m2:02d}:{s2:02d}")
            self.lbl_meal_tip.setText(f"{name}  {meal_dt.strftime('%H:%M')}")
            self._meal_clock.set_state(min(diff/7200, 1.0), name, meal_dt.strftime('%H:%M'))
        else:
            self.lbl_meal_countdown.setText("--:--:--")
            self.lbl_meal_tip.setText("今日用餐完毕 🌙")
            self._meal_clock.set_state(0, "晚安", "--:--")
