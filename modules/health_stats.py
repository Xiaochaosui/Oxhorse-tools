"""
健康数据统计浮窗
今日概览 / 周趋势 / 小时热力图 / 连续打卡 / 历史总量
全部用 QPainter 手绘，不依赖第三方图表库
"""
import math
from datetime import date, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTabWidget, QScrollArea, QGridLayout
)
from PyQt6.QtCore import Qt, QRect, QTimer, QPoint
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient,
    QPainterPath, QFontMetrics
)
from modules.theme import NEON_COLORS as NC
from modules import health_db as db

_TYPE_META = {
    db.TYPE_WATER: {'label': '喝水', 'color': '#4fc3f7', 'emoji': '💧', 'target': 8},
    db.TYPE_MOVE:  {'label': '站立', 'color': '#00e676', 'emoji': '🏃', 'target': 8},
    db.TYPE_MEAL:  {'label': '吃饭', 'color': '#ff9800', 'emoji': '🍱', 'target': 2},
}

# ── 小型图表基类 ──────────────────────────────────────────────────────────────

class _ChartBase(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)

    @staticmethod
    def _font(size=11, bold=False):
        f = QFont(); f.setPixelSize(size)
        if bold: f.setBold(True)
        return f


# ── 今日概览卡片 ──────────────────────────────────────────────────────────────

class TodayCard(QFrame):
    def __init__(self, event_type: str, parent=None):
        super().__init__(parent)
        self._type = event_type
        meta = _TYPE_META[event_type]
        self.setStyleSheet(f"""
            QFrame {{
                background: {NC['bg_card']};
                border: 1px solid {NC['border']};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(4)

        top = QHBoxLayout()
        emoji = QLabel(meta['emoji'])
        emoji.setStyleSheet("font-size:20px; background:transparent;")
        title = QLabel(meta['label'])
        title.setStyleSheet(f"color:{meta['color']}; font-size:11px; letter-spacing:1px; background:transparent;")
        top.addWidget(emoji); top.addWidget(title); top.addStretch()

        self.lbl_count = QLabel("0")
        self.lbl_count.setStyleSheet(f"color:{meta['color']}; font-size:32px; font-weight:bold; background:transparent;")
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_sub = QLabel("响应率 0%")
        self.lbl_sub.setStyleSheet(f"color:{NC['dim']}; font-size:10px; background:transparent;")
        self.lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._bar = _MiniBar(meta['color'], meta['target'])

        lay.addLayout(top)
        lay.addWidget(self.lbl_count)
        lay.addWidget(self._bar)
        lay.addWidget(self.lbl_sub)

    def refresh(self, summary: dict):
        s = summary.get(self._type, {})
        comp = s.get(db.ACT_COMPLETED, 0)
        rate = s.get('response_rate', 0)
        meta = _TYPE_META[self._type]
        self.lbl_count.setText(str(comp))
        color = NC['green'] if comp >= meta['target'] else meta['color']
        self.lbl_count.setStyleSheet(
            f"color:{color}; font-size:32px; font-weight:bold; background:transparent;")
        self.lbl_sub.setText(f"响应率 {rate}%  |  目标 {meta['target']} 次")
        self._bar.set_value(comp, meta['target'])


class _MiniBar(QWidget):
    def __init__(self, color: str, target: int, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        self._color = color; self._pct = 0.0
        self._target = target

    def set_value(self, val: int, target: int):
        self._pct = min(val / max(target, 1), 1.0)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setBrush(QColor(NC['border'])); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, w, h, 4, 4)
        if self._pct > 0:
            fw = int(w * self._pct)
            g = QLinearGradient(0, 0, fw, 0)
            c = QColor(self._color)
            g.setColorAt(0, c.darker(130)); g.setColorAt(1, c)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(0, 0, fw, h, 4, 4)
        p.end()


# ── 周柱状图 ──────────────────────────────────────────────────────────────────

class WeekBarChart(_ChartBase):
    """最近7天完成次数柱状图，三种类型叠加"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = {t: [{'date':'', 'count':0, 'label':''} for _ in range(7)]
                      for t in _TYPE_META}
        self.setMinimumHeight(160)

    def refresh(self):
        for t in _TYPE_META:
            self._data[t] = db.weekly_counts(t)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        PAD_L, PAD_R, PAD_T, PAD_B = 36, 10, 12, 28
        chart_w = w - PAD_L - PAD_R
        chart_h = h - PAD_T - PAD_B

        # 最大值
        max_val = 1
        for t in _TYPE_META:
            for d in self._data[t]:
                max_val = max(max_val, d['count'])

        # 背景网格线
        p.setPen(QPen(QColor(NC['border']), 1))
        for i in range(1, 5):
            y = PAD_T + chart_h - int(chart_h * i / 4)
            p.drawLine(PAD_L, y, w - PAD_R, y)
            p.setFont(_ChartBase._font(9))
            p.setPen(QColor(NC['dim']))
            p.drawText(QRect(0, y - 8, PAD_L - 4, 16), Qt.AlignmentFlag.AlignRight, str(int(max_val * i / 4)))
            p.setPen(QPen(QColor(NC['border']), 1))

        # 柱子
        n = 7
        group_w = chart_w / n
        bar_gap = 2
        types = list(_TYPE_META.keys())
        bar_w  = (group_w - bar_gap * (len(types) + 1)) / len(types)
        bar_w  = max(bar_w, 4)

        for gi, day_idx in enumerate(range(7)):
            gx = PAD_L + gi * group_w
            for ti, t in enumerate(types):
                cnt = self._data[t][day_idx]['count']
                if cnt == 0:
                    continue
                bx = gx + bar_gap + ti * (bar_w + bar_gap)
                bh = int(chart_h * cnt / max_val)
                by = PAD_T + chart_h - bh
                meta = _TYPE_META[t]
                color = QColor(meta['color'])
                grad = QLinearGradient(bx, by + bh, bx, by)
                grad.setColorAt(0, color.darker(140))
                grad.setColorAt(1, color)
                p.setBrush(QBrush(grad)); p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(int(bx), by, int(bar_w), bh, 2, 2)

            # X 轴标签
            label = self._data[types[0]][day_idx]['label']
            p.setFont(_ChartBase._font(9))
            p.setPen(QColor(NC['dim']))
            p.drawText(QRect(int(gx), h - PAD_B + 4, int(group_w), 16),
                       Qt.AlignmentFlag.AlignCenter, label)

        # 图例
        lx = PAD_L
        for t, meta in _TYPE_META.items():
            p.setBrush(QColor(meta['color'])); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(lx, 2, 10, 8, 2, 2)
            p.setFont(_ChartBase._font(9))
            p.setPen(QColor(NC['dim']))
            p.drawText(lx + 13, 11, meta['label'])
            lx += 52

        p.end()


# ── 小时热力图 ────────────────────────────────────────────────────────────────

class HourHeatmap(_ChartBase):
    """24小时完成热力，三行（水/站/餐）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = {t: [0]*24 for t in _TYPE_META}
        self.setMinimumHeight(110)

    def refresh(self):
        for t in _TYPE_META:
            self._data[t] = db.hourly_distribution(t)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        PAD_L, PAD_R, PAD_T, PAD_B = 36, 8, 8, 18
        cell_w = (w - PAD_L - PAD_R) / 24
        row_h  = (h - PAD_T - PAD_B - 4) / len(_TYPE_META)

        types = list(_TYPE_META.keys())
        for ri, t in enumerate(types):
            dist = self._data[t]
            mx = max(dist) if max(dist) > 0 else 1
            meta = _TYPE_META[t]
            cy = PAD_T + ri * (row_h + 2)

            # 类型标签
            p.setFont(_ChartBase._font(9))
            p.setPen(QColor(meta['color']))
            p.drawText(QRect(0, int(cy + row_h/2 - 8), PAD_L - 4, 16),
                       Qt.AlignmentFlag.AlignRight, meta['emoji'])

            for hr in range(24):
                val = dist[hr]
                if val == 0:
                    continue
                intensity = val / mx
                color = QColor(meta['color'])
                alpha = int(40 + 200 * intensity)
                color.setAlpha(min(alpha, 255))
                cx = PAD_L + hr * cell_w + 1
                p.setBrush(QBrush(color)); p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(int(cx), int(cy), int(cell_w - 2), int(row_h), 2, 2)

        # X 轴时间标
        p.setFont(_ChartBase._font(8))
        p.setPen(QColor(NC['dim']))
        for hr in range(0, 24, 4):
            cx = PAD_L + hr * cell_w
            p.drawText(QRect(int(cx - 8), h - PAD_B + 2, 20, 14),
                       Qt.AlignmentFlag.AlignCenter, f"{hr:02d}")
        p.end()


# ── 连续打卡 ──────────────────────────────────────────────────────────────────

class StreakWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background:{NC['bg_card']};
                border:1px solid {NC['border']};
                border-radius:10px;
            }}
        """)
        lay = QGridLayout(self); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        self._labels = {}
        for col, (t, meta) in enumerate(_TYPE_META.items()):
            emoji = QLabel(meta['emoji'])
            emoji.setStyleSheet("font-size:18px; background:transparent;")
            emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl = QLabel("0 天")
            lbl.setStyleSheet(f"color:{meta['color']}; font-size:22px; font-weight:bold; background:transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            name = QLabel(f"{meta['label']}连续")
            name.setStyleSheet(f"color:{NC['dim']}; font-size:10px; background:transparent;")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lay.addWidget(emoji, 0, col)
            lay.addWidget(lbl, 1, col)
            lay.addWidget(name, 2, col)
            self._labels[t] = lbl

    def refresh(self):
        targets = {db.TYPE_WATER: 6, db.TYPE_MOVE: 6, db.TYPE_MEAL: 2}
        for t, lbl in self._labels.items():
            days = db.streak(t, targets[t])
            lbl.setText(f"{days} 天")
            meta = _TYPE_META[t]
            color = NC['green'] if days >= 7 else meta['color']
            lbl.setStyleSheet(f"color:{color}; font-size:22px; font-weight:bold; background:transparent;")


# ── 历史总量表 ────────────────────────────────────────────────────────────────

class TotalsWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{background:{NC['bg_card']}; border:1px solid {NC['border']}; border-radius:10px;}}
        """)
        lay = QGridLayout(self); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(6)
        headers = ["类型", "触发次数", "完成次数", "忽略次数", "总响应率"]
        for ci, h in enumerate(headers):
            l = QLabel(h)
            l.setStyleSheet(f"color:{NC['dim']}; font-size:10px; letter-spacing:1px;")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(l, 0, ci)

        self._rows = {}
        for ri, (t, meta) in enumerate(_TYPE_META.items(), 1):
            cells = []
            for ci in range(5):
                l = QLabel("—")
                l.setStyleSheet(f"color:{meta['color'] if ci==0 else NC['text']}; font-size:12px;")
                l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.addWidget(l, ri, ci)
                cells.append(l)
            cells[0].setText(f"{meta['emoji']} {meta['label']}")
            self._rows[t] = cells

    def refresh(self):
        totals = db.all_time_totals()
        for t, cells in self._rows.items():
            s = totals.get(t, {})
            trig = s.get(db.ACT_TRIGGERED, 0)
            comp = s.get(db.ACT_COMPLETED, 0)
            snz  = s.get(db.ACT_SNOOZED, 0)
            rate = round(comp / trig * 100, 1) if trig > 0 else 0
            cells[1].setText(str(trig))
            cells[2].setText(str(comp))
            cells[3].setText(str(snz))
            cells[4].setText(f"{rate}%")
            color = NC['green'] if rate >= 70 else (NC['orange'] if rate >= 40 else NC['red'])
            cells[4].setStyleSheet(f"color:{color}; font-size:12px;")


# ── 主统计窗口 ────────────────────────────────────────────────────────────────

class HealthStatsWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(620, 680)
        self._build_ui()
        # 定时自动刷新
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_all)
        self._refresh_timer.start(60_000)   # 每分钟刷新
        self.refresh_all()

    def _build_ui(self):
        from modules.theme import NEON_COLORS as NC
        container = QFrame(self)
        container.setObjectName("hs_container")
        container.setGeometry(0, 0, self.width(), self.height())
        container.setStyleSheet(f"""
            QFrame#hs_container {{
                background: rgba(10,14,26,252);
                border: 1px solid {NC['border']};
                border-radius: 12px;
            }}
        """)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏
        title_bar = QFrame()
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet(f"""
            QFrame {{
                background:#060d1c;
                border-top-left-radius:12px; border-top-right-radius:12px;
                border-bottom:1px solid {NC['border']};
            }}
        """)
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(12, 0, 10, 0); tb.setSpacing(6)
        for c in ['#ff5f57','#febc2e','#28c840']:
            d = QFrame(); d.setFixedSize(10,10)
            d.setStyleSheet(f"QFrame{{background:{c};border-radius:5px;}}")
            tb.addWidget(d)
        tb.addSpacing(8)
        lbl = QLabel("📊  HEALTH STATS  //  健康统计")
        lbl.setStyleSheet(f"color:{NC['dim']};font-size:10px;letter-spacing:2px;")
        tb.addWidget(lbl); tb.addStretch()
        btn_refresh = QPushButton("⟳")
        btn_refresh.setFixedSize(24, 24)
        btn_refresh.setStyleSheet(f"""
            QPushButton {{background:transparent;color:{NC['dim']};border:none;font-size:14px;}}
            QPushButton:hover {{color:{NC['cyan']};}}
        """)
        btn_refresh.clicked.connect(self.refresh_all)
        btn_close = QPushButton("×")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet(f"""
            QPushButton {{background:transparent;color:{NC['dim']};border:none;font-size:16px;}}
            QPushButton:hover {{color:#ff5f57;}}
        """)
        btn_close.clicked.connect(self.hide)
        tb.addWidget(btn_refresh); tb.addWidget(btn_close)
        title_bar.mousePressEvent   = self._tb_press
        title_bar.mouseMoveEvent    = self._tb_move
        title_bar.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
        root.addWidget(title_bar)

        # 内容滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(14, 12, 14, 14)
        inner_lay.setSpacing(12)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # ── 今日日期 ──
        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet(f"color:{NC['dim']};font-size:10px;letter-spacing:2px;")
        inner_lay.addWidget(self.lbl_date)

        # ── 今日三卡 ──
        cards_row = QHBoxLayout(); cards_row.setSpacing(8)
        self._today_cards = {}
        for t in _TYPE_META:
            card = TodayCard(t)
            self._today_cards[t] = card
            cards_row.addWidget(card)
        inner_lay.addLayout(cards_row)

        # ── 连续打卡 ──
        streak_label = self._section("🔥  连续打卡")
        inner_lay.addWidget(streak_label)
        self._streak = StreakWidget()
        inner_lay.addWidget(self._streak)

        # ── 周趋势 ──
        inner_lay.addWidget(self._section("📅  近7天趋势"))
        legend = QHBoxLayout(); legend.setSpacing(16)
        for t, meta in _TYPE_META.items():
            dot = QFrame(); dot.setFixedSize(10,10)
            dot.setStyleSheet(f"QFrame{{background:{meta['color']};border-radius:5px;}}")
            lbl = QLabel(meta['label'])
            lbl.setStyleSheet(f"color:{NC['dim']};font-size:10px;")
            legend.addWidget(dot); legend.addWidget(lbl)
        legend.addStretch()
        inner_lay.addLayout(legend)
        self._week_chart = WeekBarChart()
        inner_lay.addWidget(self._week_chart)

        # ── 时段热力图 ──
        inner_lay.addWidget(self._section("⏰  完成时段热力（近30天）"))
        self._heatmap = HourHeatmap()
        inner_lay.addWidget(self._heatmap)

        # ── 历史总量 ──
        inner_lay.addWidget(self._section("📈  历史总量"))
        self._totals = TotalsWidget()
        inner_lay.addWidget(self._totals)

        inner_lay.addStretch()

    def _section(self, title: str) -> QLabel:
        l = QLabel(title)
        l.setStyleSheet(f"color:{NC['cyan']};font-size:11px;letter-spacing:2px;")
        return l

    def refresh_all(self):
        today = date.today()
        self.lbl_date.setText(f"TODAY  ·  {today.strftime('%Y-%m-%d  %A').upper()}")
        summary = db.daily_summary()
        for t, card in self._today_cards.items():
            card.refresh(summary)
        self._streak.refresh()
        self._week_chart.refresh()
        self._heatmap.refresh()
        self._totals.refresh()

    def resizeEvent(self, e):
        c = self.findChild(QFrame, "hs_container")
        if c: c.setGeometry(0, 0, self.width(), self.height())

    def _tb_press(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _tb_move(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
