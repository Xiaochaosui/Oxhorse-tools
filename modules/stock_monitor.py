"""
A股盯盘模块 - 新浪财经实时行情 + 涨跌幅提醒
"""
import threading
import subprocess
import requests
import re
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QPushButton, QLineEdit,
    QHeaderView, QGroupBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor
from modules.theme import NEON_COLORS as NC
import modules.config_manager as cfg

SINA_URL = "http://hq.sinajs.cn/list={codes}"
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}


def _notify(title: str, body: str):
    try:
        subprocess.Popen(
            ['notify-send', '-i', 'dialog-information', '-t', '8000', title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def _parse_sina(code: str, raw: str) -> dict | None:
    m = re.search(r'"([^"]*)"', raw)
    if not m:
        return None
    parts = m.group(1).split(',')
    try:
        if code.startswith('sh0') or code.startswith('sz3') or code.startswith('sh000'):
            if len(parts) < 6:
                return None
            name = parts[0]
            prev_close = float(parts[2]) if parts[2] else 0
            price      = float(parts[3]) if parts[3] else 0
        else:
            if len(parts) < 10:
                return None
            name = parts[0]
            prev_close = float(parts[2]) if parts[2] else 0
            price      = float(parts[3]) if parts[3] else 0
        if prev_close == 0:
            return None
        change     = price - prev_close
        change_pct = change / prev_close * 100
        high   = float(parts[4]) if len(parts) > 4 and parts[4] else price
        low    = float(parts[5]) if len(parts) > 5 and parts[5] else price
        volume = float(parts[8]) / 1e8 if len(parts) > 8 and parts[8] else 0
        return {
            'code': code, 'name': name.strip() or code,
            'price': price, 'prev_close': prev_close,
            'change': change, 'change_pct': change_pct,
            'high': high, 'low': low, 'volume': volume,
        }
    except (ValueError, IndexError):
        return None


class StockFetcher(QObject):
    data_ready = pyqtSignal(list)

    def fetch(self, codes: list):
        threading.Thread(target=self._run, args=(codes,), daemon=True).start()

    def _run(self, codes: list):
        if not codes:
            self.data_ready.emit([]); return
        try:
            url  = SINA_URL.format(codes=','.join(codes))
            resp = requests.get(url, headers=SINA_HEADERS, timeout=5)
            resp.encoding = 'gbk'
            lines   = resp.text.strip().split('\n')
            results = [item for line, code in zip(lines, codes)
                       if (item := _parse_sina(code, line))]
            self.data_ready.emit(results)
        except Exception:
            self.data_ready.emit([])


class StockWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fetcher = StockFetcher()
        self._fetcher.data_ready.connect(self._on_data)
        self._alert_threshold = cfg.get('stock.alert_threshold_pct', 3.0)
        self._alerted: set = set()   # 已触发提醒的 code，避免重复弹
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(cfg.get('stock.refresh_interval_seconds', 10) * 1000)
        self._refresh()

    def _is_trading_time(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = now.hour * 60 + now.minute
        return (9 * 60 + 25 <= t <= 11 * 60 + 35) or (12 * 60 + 55 <= t <= 15 * 60 + 5)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # ── 顶栏（伪装成 shell）──
        header = QFrame()
        header.setStyleSheet(f"QFrame{{background:#050d18;border:1px solid {NC['border']};border-radius:6px;}}")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 10, 6)
        h_layout.setSpacing(8)

        shell_label = QLabel("❯ python3 data_pipeline.py --monitor --live")
        shell_label.setStyleSheet(f"color:{NC['dim']};font-size:11px;font-family:monospace;")

        self.lbl_last_update = QLabel("--:--:--")
        self.lbl_last_update.setStyleSheet(f"color:{NC['dim']};font-size:10px;font-family:monospace;")
        self.lbl_last_update.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_market_status = QLabel("● LIVE")
        self.lbl_market_status.setStyleSheet(f"color:{NC['green']};font-size:10px;font-family:monospace;")
        self.lbl_market_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        h_layout.addWidget(shell_label, 4)
        h_layout.addWidget(self.lbl_last_update, 1)
        h_layout.addWidget(self.lbl_market_status, 1)
        root.addWidget(header)

        # ── 行情表格 ──
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "最新价", "涨跌幅", "涨跌额", "成交量(亿)"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(2, 75)
        self.table.setColumnWidth(3, 75)
        self.table.setColumnWidth(4, 65)
        self.table.setColumnWidth(5, 80)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background:#050d18; alternate-background-color:#07111f;
                gridline-color:#0f1e30; border:1px solid {NC['border']};
                font-family:monospace; font-size:12px;
            }}
            QTableWidget::item {{ padding:5px 6px; color:{NC['text']}; }}
            QTableWidget::item:selected {{ background:#1a3a5c; }}
            QHeaderView::section {{
                background:#050d18; color:{NC['dim']};
                border:none; border-bottom:1px solid {NC['border']};
                padding:5px 6px; font-size:10px; letter-spacing:1px;
            }}
        """)
        root.addWidget(self.table)

        # ── 涨跌提醒设置 ──
        alert_group = QGroupBox("PRICE ALERT  //  涨跌提醒")
        alert_group.setStyleSheet(f"""
            QGroupBox {{
                border:1px solid {NC['border']}; border-radius:6px;
                margin-top:8px; color:{NC['dim']};
                font-size:10px; letter-spacing:2px;
            }}
            QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 5px; }}
        """)
        al = QHBoxLayout(alert_group)
        al.setContentsMargins(10, 14, 10, 10)
        al.setSpacing(8)

        lbl_a = QLabel("涨跌幅超过")
        lbl_a.setStyleSheet(f"color:{NC['dim']};font-size:11px;")
        self.sb_alert = QDoubleSpinBox()
        self.sb_alert.setRange(0.5, 20.0)
        self.sb_alert.setValue(self._alert_threshold)
        self.sb_alert.setSuffix(" %")
        self.sb_alert.setFixedWidth(80)
        self.sb_alert.valueChanged.connect(self._save_alert_threshold)
        lbl_b = QLabel("时通知")
        lbl_b.setStyleSheet(f"color:{NC['dim']};font-size:11px;")

        self.lbl_alert_info = QLabel("")
        self.lbl_alert_info.setStyleSheet(f"color:{NC['orange']};font-size:10px;")

        al.addWidget(lbl_a)
        al.addWidget(self.sb_alert)
        al.addWidget(lbl_b)
        al.addStretch()
        al.addWidget(self.lbl_alert_info)
        root.addWidget(alert_group)

        # ── 自选股管理 ──
        manage_group = QGroupBox("WATCHLIST  //  自选股")
        manage_group.setStyleSheet(alert_group.styleSheet())
        mg = QHBoxLayout(manage_group)
        mg.setContentsMargins(10, 14, 10, 10)
        mg.setSpacing(6)

        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("sh600519 / sz002281 / 600519")
        self.input_code.setStyleSheet(f"""
            QLineEdit {{
                background:#050d18; border:1px solid {NC['border']};
                border-radius:4px; color:{NC['text']};
                padding:5px 8px; font-family:monospace; font-size:12px;
            }}
            QLineEdit:focus {{ border-color:{NC['cyan']}; }}
        """)
        self.input_code.returnPressed.connect(self._add_code)

        def _btn(text, fg, bg1, bg2, border):
            b = QPushButton(text)
            b.setFixedWidth(70)
            b.setStyleSheet(f"""
                QPushButton {{background:{bg1};color:{fg};border:1px solid {border};
                border-radius:4px;padding:5px;font-size:11px;}}
                QPushButton:hover {{background:{bg2};border-color:{fg};}}
            """)
            return b

        btn_add     = _btn("+ ADD", NC['cyan'],  '#0a1a2a', '#1a3a5c', NC['border'])
        btn_remove  = _btn("- DEL", NC['red'],   '#1a0a0a', '#2a1010', '#3a1a1a')
        btn_refresh = QPushButton("⟳")
        btn_refresh.setFixedWidth(36)
        btn_refresh.setStyleSheet(f"""
            QPushButton {{background:#0a1a0a;color:{NC['green']};border:1px solid #1a3a1a;
            border-radius:4px;padding:5px;font-size:13px;}}
            QPushButton:hover {{background:#0f2a0f;border-color:{NC['green']};}}
        """)
        btn_add.clicked.connect(self._add_code)
        btn_remove.clicked.connect(self._remove_selected)
        btn_refresh.clicked.connect(self._refresh)

        mg.addWidget(self.input_code)
        mg.addWidget(btn_add)
        mg.addWidget(btn_remove)
        mg.addWidget(btn_refresh)
        root.addWidget(manage_group)

    def _save_alert_threshold(self, val: float):
        self._alert_threshold = val
        cfg.set('stock.alert_threshold_pct', val)
        self._alerted.clear()  # 阈值改变后重置已提醒集合

    def _refresh(self):
        trading = self._is_trading_time()
        self.lbl_market_status.setText("● LIVE" if trading else "○ 休市")
        self.lbl_market_status.setStyleSheet(
            f"color:{NC['green']};font-size:10px;font-family:monospace;" if trading
            else f"color:{NC['dim']};font-size:10px;font-family:monospace;"
        )
        codes = cfg.get('stock.watchlist', [])
        if codes:
            self._fetcher.fetch(codes)

    def _on_data(self, data: list):
        self.lbl_last_update.setText(datetime.now().strftime('%H:%M:%S'))
        self.table.setRowCount(len(data))

        alerted_this_batch = []
        for ri, item in enumerate(data):
            chg_pct = item['change_pct']
            chg     = item['change']
            sign    = '+' if chg_pct > 0 else ''
            color   = NC['red'] if chg_pct > 0 else (NC['green'] if chg_pct < 0 else NC['text'])

            cells = [
                (item['code'],                    NC['dim']),
                (item['name'],                    NC['text']),
                (f"{item['price']:.2f}",          color),
                (f"{sign}{chg_pct:.2f}%",         color),
                (f"{sign}{chg:.2f}",              color),
                (f"{item['volume']:.3f}" if item['volume'] > 0 else "--", NC['dim']),
            ]
            for col, (text, fg) in enumerate(cells):
                cell = QTableWidgetItem(text)
                cell.setForeground(QColor(fg))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(ri, col, cell)

            # 涨跌提醒检查
            code = item['code']
            if self._is_trading_time() and abs(chg_pct) >= self._alert_threshold and code not in self._alerted:
                self._alerted.add(code)
                alerted_this_batch.append((item['name'], chg_pct, item['price']))

        if alerted_this_batch:
            lines = [f"{'↑' if p>0 else '↓'} {name}  {'+' if p>0 else ''}{p:.2f}%  ({price:.2f})"
                     for name, p, price in alerted_this_batch]
            _notify("📊 行情提醒", '\n'.join(lines))
            self.lbl_alert_info.setText(f"最近提醒: {alerted_this_batch[-1][0]} {alerted_this_batch[-1][1]:+.2f}%")

    def _normalize_code(self, raw: str) -> str:
        raw = raw.strip().lower()
        if raw.startswith(('sh', 'sz', 'bj')):
            return raw
        digits = re.sub(r'\D', '', raw)
        if not digits:
            return ''
        if digits.startswith('6'):
            return 'sh' + digits
        elif digits.startswith(('0', '3', '2')):
            return 'sz' + digits
        elif digits.startswith(('8', '4')):
            return 'bj' + digits
        return 'sh' + digits

    def _add_code(self):
        raw = self.input_code.text().strip()
        if not raw:
            return
        code = self._normalize_code(raw)
        if not code:
            return
        codes = cfg.get('stock.watchlist', [])
        names = cfg.get('stock.watchlist_names', [])
        if code not in codes:
            codes.append(code)
            names.append(code)
            cfg.set('stock.watchlist', codes)
            cfg.set('stock.watchlist_names', names)
        self.input_code.clear()
        self._refresh()

    def _remove_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        code_item = self.table.item(row, 0)
        if not code_item:
            return
        code  = code_item.text()
        codes = cfg.get('stock.watchlist', [])
        names = cfg.get('stock.watchlist_names', [])
        if code in codes:
            idx = codes.index(code)
            codes.pop(idx)
            if idx < len(names):
                names.pop(idx)
            cfg.set('stock.watchlist', codes)
            cfg.set('stock.watchlist_names', names)
        self._alerted.discard(code)
        self.table.removeRow(row)
