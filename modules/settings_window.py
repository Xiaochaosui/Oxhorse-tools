"""
独立设置窗口 — 汇总所有配置，分 Tab 管理
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTabWidget,
    QGroupBox, QGridLayout, QPushButton, QLineEdit, QTimeEdit,
    QDoubleSpinBox, QSpinBox, QComboBox, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QTime, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen
from modules.theme import NEON_COLORS as NC, DARK_TECH
import modules.config_manager as cfg

_GRP = f"""
    QGroupBox {{
        border: 1px solid {NC['border']};
        border-radius: 8px;
        margin-top: 14px;
        color: {NC['cyan']};
        font-size: 10px;
        letter-spacing: 2px;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}
"""

def _lbl(text, dim=True):
    l = QLabel(text)
    l.setStyleSheet(f"color:{ NC['dim'] if dim else NC['text'] }; font-size:12px;")
    return l

def _sep():
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{NC['border']}; border:none;")
    return line


class SettingsWindow(QWidget):
    """独立设置浮窗，包含所有配置项"""
    settings_saved = pyqtSignal()  # 任何设置保存时广播，各模块收到后刷新

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(540, 620)
        self._build_ui()
        self._load_all()

    def _build_ui(self):
        container = QFrame(self)
        container.setObjectName("settings_container")
        container.setGeometry(0, 0, self.width(), self.height())
        container.setStyleSheet(f"""
            QFrame#settings_container {{
                background: rgba(10,14,26,252);
                border: 1px solid {NC['border']};
                border-radius: 12px;
            }}
        """)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 标题栏 ──
        title_bar = QFrame()
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet(f"""
            QFrame {{
                background: #060d1c;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid {NC['border']};
            }}
        """)
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(12, 0, 10, 0)
        tb.setSpacing(6)
        for c in ['#ff5f57','#febc2e','#28c840']:
            d = QFrame(); d.setFixedSize(10,10)
            d.setStyleSheet(f"QFrame{{background:{c};border-radius:5px;}}")
            tb.addWidget(d)
        tb.addSpacing(8)
        lbl = QLabel("⚙  SETTINGS  //  所有配置")
        lbl.setStyleSheet(f"color:{NC['dim']};font-size:10px;letter-spacing:2px;")
        tb.addWidget(lbl)
        tb.addStretch()
        from main import TitleBarBtn
        btn_close = TitleBarBtn("×", '#ff5f57')
        btn_close.clicked.connect(self.hide)
        tb.addWidget(btn_close)
        title_bar.mousePressEvent   = self._tb_press
        title_bar.mouseMoveEvent    = self._tb_move
        title_bar.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
        root.addWidget(title_bar)

        # ── Tab ──
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:none; background:transparent; }}
            QTabBar::tab {{
                background:transparent; color:{NC['dim']};
                padding:8px 18px; border:none;
                border-bottom:2px solid transparent;
                font-size:11px; letter-spacing:1.5px; min-width:70px;
            }}
            QTabBar::tab:selected {{
                color:{NC['cyan']};
                border-bottom:2px solid {NC['cyan']};
                background:rgba(79,195,247,0.05);
            }}
            QTabBar::tab:hover:!selected {{ color:#90caf9; }}
        """)

        tabs.addTab(self._tab_work(),     "⏰  工作")
        tabs.addTab(self._tab_remind(),   "🔔  提醒")
        tabs.addTab(self._tab_stock(),    "📊  行情")
        tabs.addTab(self._tab_feishu(),   "✓  飞书")
        tabs.addTab(self._tab_windows(),  "🖥  窗口")

        root.addWidget(tabs)

    # ── 工作设置 ────────────────────────────────────────────────────────────

    def _tab_work(self) -> QWidget:
        w = self._scroll_tab()
        lay = w.layout()

        grp = QGroupBox("上下班时间")
        grp.setStyleSheet(_GRP)
        g = QGridLayout(grp)
        g.setSpacing(10); g.setContentsMargins(14,18,14,14)

        self.te_start = QTimeEdit(); self.te_start.setDisplayFormat("HH:mm")
        self.te_end   = QTimeEdit(); self.te_end.setDisplayFormat("HH:mm")
        g.addWidget(_lbl("上班时间"), 0,0); g.addWidget(self.te_start, 0,1)
        g.addWidget(_lbl("下班时间"), 0,2); g.addWidget(self.te_end,   0,3)
        lay.addWidget(grp)

        grp2 = QGroupBox("薪资 & 发薪日")
        grp2.setStyleSheet(_GRP)
        g2 = QGridLayout(grp2)
        g2.setSpacing(10); g2.setContentsMargins(14,18,14,14)

        self.sb_salary = QDoubleSpinBox()
        self.sb_salary.setRange(1000, 9999999); self.sb_salary.setDecimals(0)
        self.sb_salary.setSingleStep(1000); self.sb_salary.setPrefix("¥ ")
        self.sb_sday = QSpinBox(); self.sb_sday.setRange(1,31)
        self.sb_sday.setSuffix(" 号")

        g2.addWidget(_lbl("月薪"), 0,0); g2.addWidget(self.sb_salary, 0,1)
        g2.addWidget(_lbl("发薪日"), 0,2); g2.addWidget(self.sb_sday, 0,3)
        note = _lbl("* 发薪日遇周末自动提前到周五", dim=True)
        note.setStyleSheet(f"color:{NC['dim']};font-size:10px;font-style:italic;")
        g2.addWidget(note, 1, 0, 1, 4)
        lay.addWidget(grp2)

        lay.addWidget(self._save_btn("保存工作设置", self._save_work))
        lay.addStretch()
        return w

    # ── 提醒设置 ────────────────────────────────────────────────────────────

    def _tab_remind(self) -> QWidget:
        w = self._scroll_tab()
        lay = w.layout()

        grp = QGroupBox("喝水提醒")
        grp.setStyleSheet(_GRP)
        g = QGridLayout(grp)
        g.setSpacing(10); g.setContentsMargins(14,18,14,14)

        self.sb_water = QSpinBox()
        self.sb_water.setRange(10, 240); self.sb_water.setSuffix(" 分钟")
        self.sb_water.setToolTip("每隔多少分钟提醒一次喝水")
        g.addWidget(_lbl("提醒间隔"), 0,0); g.addWidget(self.sb_water, 0,1)
        note = _lbl("* 建议每 45~60 分钟喝一次，每天 8 杯")
        note.setStyleSheet(f"color:{NC['dim']};font-size:10px;font-style:italic;")
        g.addWidget(note, 1,0,1,4)
        lay.addWidget(grp)

        grp_move = QGroupBox("🏃 站起来动一动")
        grp_move.setStyleSheet(_GRP)
        gm = QGridLayout(grp_move)
        gm.setSpacing(10); gm.setContentsMargins(14,18,14,14)

        self.sb_move = QSpinBox()
        self.sb_move.setRange(15, 120); self.sb_move.setSuffix(" 分钟")
        self.sb_move.setToolTip("每隔多少分钟提醒起身活动")
        gm.addWidget(_lbl("提醒间隔"), 0,0); gm.addWidget(self.sb_move, 0,1)
        note_m = _lbl("* 久坐杀手！建议每 45 分钟起身走动一次")
        note_m.setStyleSheet(f"color:{NC['dim']};font-size:10px;font-style:italic;")
        gm.addWidget(note_m, 1,0,1,4)
        lay.addWidget(grp_move)

        grp2 = QGroupBox("吃饭提醒")
        grp2.setStyleSheet(_GRP)
        g2 = QGridLayout(grp2)
        g2.setSpacing(10); g2.setContentsMargins(14,18,14,14)

        self.te_lunch  = QTimeEdit(); self.te_lunch.setDisplayFormat("HH:mm")
        self.te_dinner = QTimeEdit(); self.te_dinner.setDisplayFormat("HH:mm")
        g2.addWidget(_lbl("午饭时间"), 0,0); g2.addWidget(self.te_lunch,  0,1)
        g2.addWidget(_lbl("晚饭时间"), 0,2); g2.addWidget(self.te_dinner, 0,3)
        note2 = _lbl("* 到点前后 2 分钟内触发全屏提醒")
        note2.setStyleSheet(f"color:{NC['dim']};font-size:10px;font-style:italic;")
        g2.addWidget(note2, 1,0,1,4)
        lay.addWidget(grp2)

        lay.addWidget(self._save_btn("保存提醒设置", self._save_remind))
        lay.addStretch()
        return w

    # ── 行情设置 ────────────────────────────────────────────────────────────

    def _tab_stock(self) -> QWidget:
        w = self._scroll_tab()
        lay = w.layout()

        grp = QGroupBox("数据刷新 & 提醒阈值")
        grp.setStyleSheet(_GRP)
        g = QGridLayout(grp)
        g.setSpacing(10); g.setContentsMargins(14,18,14,14)

        self.sb_refresh = QSpinBox()
        self.sb_refresh.setRange(3, 60); self.sb_refresh.setSuffix(" 秒")
        self.sb_alert = QDoubleSpinBox()
        self.sb_alert.setRange(0.5, 20.0); self.sb_alert.setSuffix(" %")
        self.sb_alert.setDecimals(1); self.sb_alert.setSingleStep(0.5)

        g.addWidget(_lbl("刷新间隔"), 0,0); g.addWidget(self.sb_refresh, 0,1)
        g.addWidget(_lbl("涨跌提醒阈值"), 0,2); g.addWidget(self.sb_alert, 0,3)
        note = _lbl("* 交易时段涨跌幅超过阈值时发送桌面通知")
        note.setStyleSheet(f"color:{NC['dim']};font-size:10px;font-style:italic;")
        g.addWidget(note, 1,0,1,4)
        lay.addWidget(grp)

        lay.addWidget(self._save_btn("保存行情设置", self._save_stock))
        lay.addStretch()
        return w

    # ── 飞书设置 ────────────────────────────────────────────────────────────

    def _tab_feishu(self) -> QWidget:
        w = self._scroll_tab()
        lay = w.layout()

        grp = QGroupBox("飞书开放平台凭据")
        grp.setStyleSheet(_GRP)
        g = QGridLayout(grp)
        g.setSpacing(10); g.setContentsMargins(14,18,14,14)

        self.input_appid     = QLineEdit(); self.input_appid.setPlaceholderText("cli_xxxxxxxxxxxxxxxx")
        self.input_appsecret = QLineEdit(); self.input_appsecret.setPlaceholderText("App Secret")
        self.input_appsecret.setEchoMode(QLineEdit.EchoMode.Password)

        g.addWidget(_lbl("App ID"), 0,0); g.addWidget(self.input_appid, 0,1,1,3)
        g.addWidget(_lbl("App Secret"), 1,0); g.addWidget(self.input_appsecret, 1,1,1,3)
        lay.addWidget(grp)

        grp2 = QGroupBox("多维表格（Bitable）")
        grp2.setStyleSheet(_GRP)
        g2 = QGridLayout(grp2)
        g2.setSpacing(10); g2.setContentsMargins(14,18,14,14)

        self.input_apptoken = QLineEdit(); self.input_apptoken.setPlaceholderText("Bitable App Token（URL 中 /base/ 后面）")
        self.input_tableid  = QLineEdit(); self.input_tableid.setPlaceholderText("Table ID（在表格 API 面板里复制）")

        g2.addWidget(_lbl("App Token"), 0,0); g2.addWidget(self.input_apptoken, 0,1,1,3)
        g2.addWidget(_lbl("Table ID"),  1,0); g2.addWidget(self.input_tableid,  1,1,1,3)

        note = _lbl("* 表格必须有「标题 / 优先级 / 状态 / 备注」四列")
        note.setStyleSheet(f"color:{NC['dim']};font-size:10px;font-style:italic;")
        g2.addWidget(note, 2,0,1,4)
        lay.addWidget(grp2)

        lay.addWidget(self._save_btn("保存飞书配置", self._save_feishu))
        lay.addStretch()
        return w

    # ── 窗口大小设置 ─────────────────────────────────────────────────────────

    def _tab_windows(self) -> QWidget:
        w = self._scroll_tab()
        lay = w.layout()

        info = QLabel(
            "每个窗口支持拖拽边缘调整大小，退出时自动记忆位置和尺寸。\n"
            "下方可手动指定各窗口的默认宽/高，点「重置位置」将所有窗口移回屏幕右下角。"
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{NC['dim']};font-size:11px;line-height:160%;padding:4px 0;")
        lay.addWidget(info)

        from main import WINDOWS_CONFIG
        self._win_size_inputs = {}
        for wc in WINDOWS_CONFIG:
            grp = QGroupBox(f"{wc['emoji']}  {wc['title']}")
            grp.setStyleSheet(_GRP)
            g = QGridLayout(grp)
            g.setSpacing(10); g.setContentsMargins(14,18,14,14)

            sb_w = QSpinBox(); sb_w.setRange(320, 1600); sb_w.setSuffix(" px"); sb_w.setValue(wc['width'])
            sb_h = QSpinBox(); sb_h.setRange(300, 1200); sb_h.setSuffix(" px"); sb_h.setValue(wc['height'])
            g.addWidget(_lbl("宽度"), 0,0); g.addWidget(sb_w, 0,1)
            g.addWidget(_lbl("高度"), 0,2); g.addWidget(sb_h, 0,3)
            self._win_size_inputs[wc['id']] = (sb_w, sb_h)
            lay.addWidget(grp)

        row = QHBoxLayout()
        btn_apply  = self._save_btn("应用窗口尺寸", self._apply_window_sizes)
        btn_reset  = QPushButton("↺  重置所有窗口位置")
        btn_reset.setStyleSheet(f"""
            QPushButton {{
                background:#1a1a0a; color:{NC['yellow']};
                border:1px solid #3a3a1a; border-radius:6px;
                padding:8px 16px; font-size:12px;
            }}
            QPushButton:hover {{ background:#2a2a10; border-color:{NC['yellow']}; }}
        """)
        btn_reset.clicked.connect(self._reset_positions)
        row.addWidget(btn_apply)
        row.addWidget(btn_reset)
        lay.addLayout(row)
        lay.addStretch()
        return w

    # ── 辅助 ────────────────────────────────────────────────────────────────

    def _scroll_tab(self) -> QWidget:
        """返回一个带 QVBoxLayout 的可滚动 Tab 页"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        scroll.setWidget(inner)
        # 把 scroll 本身变成可以拿 .layout() 的容器
        scroll._inner_layout = layout
        scroll.layout = lambda: layout   # monkey-patch 方便统一调用
        return scroll

    def _save_btn(self, text: str, slot) -> QPushButton:
        btn = QPushButton(f"✓  {text}")
        btn.setStyleSheet(f"""
            QPushButton {{
                background:#071a07; color:{NC['green']};
                border:1px solid #1a4a1a; border-radius:6px;
                padding:8px 20px; font-size:12px;
            }}
            QPushButton:hover {{ background:#0d2a0d; border-color:{NC['green']}; }}
        """)
        btn.clicked.connect(slot)
        return btn

    def _tb_press(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _tb_move(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def resizeEvent(self, e):
        c = self.findChild(QFrame, "settings_container")
        if c:
            c.setGeometry(0, 0, self.width(), self.height())

    # ── 加载 ────────────────────────────────────────────────────────────────

    def _load_all(self):
        s = cfg.load()
        w  = s.get('work', {})
        r  = s.get('reminders', {})
        st = s.get('stock', {})
        f  = s.get('feishu', {})

        self.te_start.setTime(QTime.fromString(w.get('start_time', '09:00'), 'HH:mm'))
        self.te_end.setTime(QTime.fromString(w.get('end_time', '18:00'), 'HH:mm'))
        self.sb_salary.setValue(w.get('monthly_salary', 20000))
        self.sb_sday.setValue(w.get('salary_day', 30))

        self.sb_water.setValue(r.get('water_interval_minutes', 60))
        self.sb_move.setValue(r.get('move_interval_minutes', 45))
        self.te_lunch.setTime(QTime.fromString(r.get('lunch_time', '12:00'), 'HH:mm'))
        self.te_dinner.setTime(QTime.fromString(r.get('dinner_time', '18:30'), 'HH:mm'))

        self.sb_refresh.setValue(st.get('refresh_interval_seconds', 10))
        self.sb_alert.setValue(st.get('alert_threshold_pct', 3.0))

        self.input_appid.setText(f.get('app_id', ''))
        self.input_appsecret.setText(f.get('app_secret', ''))
        self.input_apptoken.setText(f.get('bitable_app_token', ''))
        self.input_tableid.setText(f.get('bitable_table_id', ''))

        # 窗口尺寸从已保存的配置读取
        from main import _load_positions, WINDOWS_CONFIG
        saved = _load_positions()
        for wc in WINDOWS_CONFIG:
            wid = wc['id']
            if wid in self._win_size_inputs:
                sw, sh = self._win_size_inputs[wid]
                if wid in saved and 'w' in saved[wid]:
                    sw.setValue(saved[wid]['w'])
                    sh.setValue(saved[wid]['h'])

    # ── 保存 ────────────────────────────────────────────────────────────────

    def _save_work(self):
        s = cfg.load()
        s['work']['start_time']    = self.te_start.time().toString('HH:mm')
        s['work']['end_time']      = self.te_end.time().toString('HH:mm')
        s['work']['monthly_salary'] = self.sb_salary.value()
        s['work']['salary_day']    = self.sb_sday.value()
        cfg.save(s)
        self.settings_saved.emit()
        self._flash_saved()

    def _save_remind(self):
        s = cfg.load()
        s['reminders']['water_interval_minutes'] = self.sb_water.value()
        s['reminders']['move_interval_minutes']  = self.sb_move.value()
        s['reminders']['lunch_time']  = self.te_lunch.time().toString('HH:mm')
        s['reminders']['dinner_time'] = self.te_dinner.time().toString('HH:mm')
        cfg.save(s)
        self.settings_saved.emit()
        self._flash_saved()

    def _save_stock(self):
        s = cfg.load()
        s['stock']['refresh_interval_seconds'] = self.sb_refresh.value()
        s['stock']['alert_threshold_pct']      = self.sb_alert.value()
        cfg.save(s)
        self.settings_saved.emit()
        self._flash_saved()

    def _save_feishu(self):
        s = cfg.load()
        s['feishu']['app_id']            = self.input_appid.text().strip()
        s['feishu']['app_secret']        = self.input_appsecret.text().strip()
        s['feishu']['bitable_app_token'] = self.input_apptoken.text().strip()
        s['feishu']['bitable_table_id']  = self.input_tableid.text().strip()
        cfg.save(s)
        self.settings_saved.emit()
        self._flash_saved()

    def _apply_window_sizes(self):
        from main import _load_positions, _save_positions, WINDOWS_CONFIG
        positions = _load_positions()
        for wc in WINDOWS_CONFIG:
            wid = wc['id']
            if wid in self._win_size_inputs:
                sb_w, sb_h = self._win_size_inputs[wid]
                if wid not in positions:
                    positions[wid] = {}
                positions[wid]['w'] = sb_w.value()
                positions[wid]['h'] = sb_h.value()
        _save_positions(positions)
        self.settings_saved.emit()  # main.py 里监听并 resize 窗口
        self._flash_saved()

    def _reset_positions(self):
        from main import _save_positions, WINDOWS_CONFIG, _load_positions
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        sw, sh = screen.width(), screen.height()
        positions = _load_positions()
        for wc in WINDOWS_CONFIG:
            ox, oy = wc['offset']
            x = sw - wc['width'] - 20 - ox
            y = sh - wc['height'] - 60 - oy
            wid = wc['id']
            entry = positions.get(wid, {})
            entry['x'] = max(0, x)
            entry['y'] = max(0, y)
            positions[wid] = entry
        _save_positions(positions)
        self.settings_saved.emit()
        self._flash_saved()

    def _flash_saved(self):
        """短暂变色提示保存成功"""
        orig = self.windowTitle()
        self.setWindowTitle("✓ 已保存")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self.setWindowTitle(orig))
