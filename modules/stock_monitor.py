"""
A股盯盘模块 - 新浪财经实时行情 + 涨跌幅提醒
"""
import threading
import requests
import re
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QPushButton, QLineEdit,
    QHeaderView, QGroupBox, QDoubleSpinBox, QMenu, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt6.QtGui import QColor, QAction
from modules.theme import NEON_COLORS as NC
import modules.config_manager as cfg
from modules.daily_report import ReportPanel
from cross_platform_utils import send_notification as _notify

SINA_URL = "http://hq.sinajs.cn/list={codes}"
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}


def _parse_sina(code: str, raw: str) -> tuple:
    """返回 (dict | None, reason: str)。reason 用于失败时日志诊断"""
    m = re.search(r'"([^"]*)"', raw)
    if not m:
        return None, "regex no match"
    parts = m.group(1).split(',')
    # 未开市 / 代码不存在时新浪只返回 name 一个字段
    if len(parts) < 2:
        return None, f"empty data ({len(parts)} field): code may not exist on Sina"
    try:
        if code.startswith('sh0') or code.startswith('sz3') or code.startswith('sh000'):
            if len(parts) < 6:
                return None, f"index: only {len(parts)} fields"
            name = parts[0]
            prev_close = float(parts[2]) if parts[2] else 0
            price      = float(parts[3]) if parts[3] else 0
        else:
            if len(parts) < 10:
                return None, f"stock/etf: only {len(parts)} fields (need >=10)"
            name = parts[0]
            prev_close = float(parts[2]) if parts[2] else 0
            price      = float(parts[3]) if parts[3] else 0
        if prev_close == 0:
            return None, "prev_close is 0"
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
        }, "ok"
    except (ValueError, IndexError) as e:
        return None, f"value error: {e}"


_log = logging.getLogger(__name__)


class _ReorderTable(QTableWidget):
    """支持拖拽排序的 QTableWidget，drop 后通过 _on_reorder 回调通知"""

    def dropEvent(self, event):
        src_row = self.currentRow()
        super().dropEvent(event)
        # 计算 drop 后的新行号（通过行的 item 反查）
        if hasattr(self, '_on_reorder') and src_row >= 0:
            self._on_reorder()


class StockFetcher(QObject):
    data_ready = pyqtSignal(list)
    _MAX_WARN_COUNT = 5  # 单个代码最多 warning 次数

    def __init__(self):
        super().__init__()
        self._parse_failures: dict[str, int] = {}  # 代码 → 累计解析失败次数

    def fetch(self, codes: list):
        threading.Thread(target=self._run, args=(codes,), daemon=True).start()

    def _run(self, codes: list):
        if not codes:
            self.data_ready.emit([]); return
        try:
            url  = SINA_URL.format(codes=','.join(codes))
            resp = requests.get(url, headers=SINA_HEADERS, timeout=10)
            resp.encoding = 'gbk'
            lines   = resp.text.strip().split('\n')
            results = []
            for line, code in zip(lines, codes):
                item, reason = _parse_sina(code, line)
                if item:
                    results.append(item)
                    self._parse_failures.pop(code, None)  # 成功后重置计数
                else:
                    self._log_parse_fail(code, reason)
            self.data_ready.emit(results)
        except requests.exceptions.Timeout:
            _log.warning("Sina API timeout (codes=%d)", len(codes))
            self.data_ready.emit([])
        except requests.exceptions.RequestException as e:
            _log.warning("Sina API request failed: %s", e)
            self.data_ready.emit([])

    def _log_parse_fail(self, code: str, reason: str):
        """解析失败限流：前 _MAX_WARN_COUNT 次打 WARNING，之后静默为 DEBUG"""
        count = self._parse_failures.get(code, 0) + 1
        self._parse_failures[code] = count
        if count <= self._MAX_WARN_COUNT:
            _log.warning("Sina parse fail [%s] (%d/%d): %s",
                         code, count, self._MAX_WARN_COUNT, reason)
        else:
            _log.debug("Sina parse fail [%s] (x%d, suppressed): %s",
                       code, count, reason)


def _classify_code(code: str) -> str:
    """将代码归类为 index / etf / stock"""
    c = code.lower()
    num = c[2:] if c[:2] in ('sh', 'sz', 'bj') else c
    # 指数：sh000xxx / sz399xxx
    if c.startswith('sh0') or c.startswith('sz3') or c.startswith('sh000'):
        return 'index'
    # ETF / 基金：sh5xxxxx / sz1xxxxx（含 sz159xxx）
    if c.startswith('sh5') or c.startswith('sz1'):
        return 'etf'
    return 'stock'


# 分组 tab 定义：id → 显示名
_TABS = [
    ('all',    'ALL'),
    ('index',  '指数'),
    ('stock',  '个股'),
    ('etf',    'ETF'),
    ('custom', '自选'),
]


class StockWidget(QWidget):
    _MAX_ADD_RETRIES = 5   # 新增股票最多重试次数
    _MAX_WARN_COUNT  = 5   # 单个代码最多打印 warning 次数，之后静默

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fetcher = StockFetcher()
        self._fetcher.data_ready.connect(self._on_data)
        self._alert_threshold = cfg.get('stock.alert_threshold_pct', 3.0)
        self._alerted: set = set()
        self._last_data: list = []       # 缓存最新一批行情数据
        self._active_tab: str = 'all'    # 当前激活的分组
        self._pending_codes: dict[str, int] = {}  # 新加代码 → 剩余重试次数
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
        shell_label.setStyleSheet(f"color:{NC['dim']};font-size:11px;font-family:'Consolas','Courier New',monospace;")

        self.lbl_last_update = QLabel("--:--:--")
        self.lbl_last_update.setStyleSheet(f"color:{NC['dim']};font-size:10px;font-family:'Consolas','Courier New',monospace;")
        self.lbl_last_update.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_market_status = QLabel("● LIVE")
        self.lbl_market_status.setStyleSheet(f"color:{NC['green']};font-size:10px;font-family:'Consolas','Courier New',monospace;")
        self.lbl_market_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        h_layout.addWidget(shell_label, 4)
        h_layout.addWidget(self.lbl_last_update, 1)
        h_layout.addWidget(self.lbl_market_status, 1)
        root.addWidget(header)

        # ── 分组 Tab 栏 ──
        tab_bar = QFrame()
        tab_bar.setStyleSheet(f"QFrame{{background:#050d18;border:1px solid {NC['border']};border-radius:6px;}}")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(6, 4, 6, 4)
        tab_layout.setSpacing(4)

        self._tab_btns: dict[str, QPushButton] = {}
        for tid, tlabel in _TABS:
            btn = QPushButton(tlabel)
            btn.setCheckable(True)
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda _, t=tid: self._switch_tab(t))
            self._tab_btns[tid] = btn
            tab_layout.addWidget(btn)
        tab_layout.addStretch()
        self._tab_btns['all'].setChecked(True)
        self._update_tab_style()
        root.addWidget(tab_bar)

        # ── 行情表格 ──
        self.table = _ReorderTable()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["⇅", "代码", "名称", "最新价", "涨跌幅", "涨跌额", "成交量(亿)"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        # 拖拽排序
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDragDropOverwriteMode(False)
        self.table.setDropIndicatorShown(True)
        # 列宽：handle 固定 28px，名称自动拉伸
        self.table.setColumnWidth(0, 28)   # ⇅ handle
        self.table.setColumnWidth(1, 80)   # 代码
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # 名称
        self.table.setColumnWidth(3, 75)   # 最新价
        self.table.setColumnWidth(4, 75)   # 涨跌幅
        self.table.setColumnWidth(5, 65)   # 涨跌额
        self.table.setColumnWidth(6, 80)   # 成交量
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background:#050d18; alternate-background-color:#07111f;
                gridline-color:#0f1e30; border:1px solid {NC['border']};
                font-family:'Consolas','Courier New',monospace; font-size:12px;
            }}
            QTableWidget::item {{ padding:5px 6px; color:{NC['text']}; }}
            QTableWidget::item:selected {{ background:#1a3a5c; }}
            QHeaderView::section {{
                background:#050d18; color:{NC['dim']};
                border:none; border-bottom:1px solid {NC['border']};
                padding:5px 6px; font-size:10px; letter-spacing:1px;
            }}
        """)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table._on_reorder = self._on_table_reorder
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
                padding:5px 8px; font-family:'Consolas','Courier New',monospace; font-size:12px;
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

        # ── 收盘报告面板 ──
        self._report_panel = ReportPanel()
        root.addWidget(self._report_panel)

    def _save_alert_threshold(self, val: float):
        self._alert_threshold = val
        cfg.set('stock.alert_threshold_pct', val)
        self._alerted.clear()  # 阈值改变后重置已提醒集合

    def _refresh(self):
        trading = self._is_trading_time()
        self.lbl_market_status.setText("● LIVE" if trading else "○ 休市")
        self.lbl_market_status.setStyleSheet(
            f"color:{NC['green']};font-size:10px;font-family:'Consolas','Courier New',monospace;" if trading
            else f"color:{NC['dim']};font-size:10px;font-family:'Consolas','Courier New',monospace;"
        )
        codes = cfg.get('stock.watchlist', [])
        if codes:
            self._fetcher.fetch(codes)

    def _switch_tab(self, tab_id: str):
        self._active_tab = tab_id
        for tid, btn in self._tab_btns.items():
            btn.setChecked(tid == tab_id)
        self._update_tab_style()
        self._render_table(self._last_data)

    def _update_tab_style(self):
        for tid, btn in self._tab_btns.items():
            active = btn.isChecked()
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:{'#0f2a3a' if active else '#050d18'};
                    color:{NC['cyan'] if active else NC['dim']};
                    border:1px solid {NC['cyan'] if active else NC['border']};
                    border-radius:4px; font-size:10px; padding:2px 8px;
                    font-family:'Consolas','Courier New',monospace; letter-spacing:1px;
                }}
                QPushButton:hover {{ background:#0f2a3a; border-color:{NC['cyan']}; color:{NC['cyan']}; }}
            """)

    def _update_tab_counts(self, data: list):
        """更新各 tab 按钮上的数量标注"""
        custom = set(cfg.get('stock.custom_group', []))
        counts = {'all': len(data), 'index': 0, 'stock': 0, 'etf': 0, 'custom': 0}
        for item in data:
            counts[_classify_code(item['code'])] += 1
            if item['code'] in custom:
                counts['custom'] += 1
        for tid, tlabel in _TABS:
            n = counts.get(tid, 0)
            suffix = f' {n}' if n else ''
            self._tab_btns[tid].setText(tlabel + suffix)

    def _filtered_data(self, data: list) -> list:
        if self._active_tab == 'all':
            return data
        if self._active_tab == 'custom':
            custom = set(cfg.get('stock.custom_group', []))
            return [d for d in data if d['code'] in custom]
        return [d for d in data if _classify_code(d['code']) == self._active_tab]

    def _render_table(self, data: list):
        rows = self._filtered_data(data)
        self.table.setRowCount(len(rows))
        for ri, item in enumerate(rows):
            # 拖拽手柄列
            handle = QTableWidgetItem("⋮⋮")
            handle.setForeground(QColor(NC['dim']))
            handle.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            handle.setToolTip("拖拽可调整顺序")
            self.table.setItem(ri, 0, handle)

            chg_pct = item['change_pct']
            chg     = item['change']
            sign    = '+' if chg_pct > 0 else ''
            color   = NC['red'] if chg_pct > 0 else (NC['green'] if chg_pct < 0 else NC['text'])
            cells = [
                (item['code'],                    NC['dim']),
                (item['name'],                    NC['text']),
                (f"{item['price']:.3f}",          color),
                (f"{sign}{chg_pct:.2f}%",         color),
                (f"{sign}{chg:.3f}",              color),
                (f"{item['volume']:.3f}" if item['volume'] > 0 else "--", NC['dim']),
            ]
            for col, (text, fg) in enumerate(cells):
                cell = QTableWidgetItem(text)
                cell.setForeground(QColor(fg))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(ri, col + 1, cell)  # col 0 is handle

    def _show_context_menu(self, pos: QPoint):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        code_item = self.table.item(row, 1)   # col 1 is 代码
        name_item = self.table.item(row, 2)   # col 2 is 名称
        if not code_item:
            return
        code = code_item.text()
        name = name_item.text() if name_item else code
        total_rows = self.table.rowCount()
        custom = set(cfg.get('stock.custom_group', []))
        in_custom = code in custom

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background:#07111f; border:1px solid {NC['border']};
                color:{NC['text']}; padding:4px; border-radius:6px;
            }}
            QMenu::item {{ padding:6px 20px 6px 12px; border-radius:3px; }}
            QMenu::item:selected {{ background:{NC['border']}; color:{NC['cyan']}; }}
            QMenu::separator {{ background:{NC['border']}; height:1px; margin:3px 6px; }}
        """)

        lbl = menu.addAction(f"  {name}（{code}）")
        lbl.setEnabled(False)
        menu.addSeparator()

        # 排序操作
        act_top    = menu.addAction("⤒  移至顶部")
        act_up     = menu.addAction("↑  上移")
        act_down   = menu.addAction("↓  下移")
        act_bottom = menu.addAction("⤓  移至底部")
        menu.addSeparator()

        if in_custom:
            act_toggle = menu.addAction("☆  从「自选」分组移除")
        else:
            act_toggle = menu.addAction("★  加入「自选」分组")

        menu.addSeparator()
        act_del = menu.addAction("✕  从自选股删除")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == act_top:
            self._move_row(row, 0 - row)
        elif action == act_up:
            self._move_row(row, -1)
        elif action == act_down:
            self._move_row(row, 1)
        elif action == act_bottom:
            self._move_row(row, total_rows - 1 - row)
        elif action == act_toggle:
            self._toggle_custom(code, in_custom)
        elif action == act_del:
            self._remove_by_code(code)

    def _toggle_custom(self, code: str, currently_in: bool):
        custom = cfg.get('stock.custom_group', [])
        if currently_in:
            custom = [c for c in custom if c != code]
        else:
            if code not in custom:
                custom.append(code)
        cfg.set('stock.custom_group', custom)
        self._update_tab_counts(self._last_data)
        if self._active_tab == 'custom':
            self._render_table(self._last_data)

    # ── 拖拽排序 ──────────────────────────────────────────────────────────

    def _on_table_reorder(self):
        """拖拽后回调：将表格当前行顺序同步回 watchlist 配置"""
        new_order = []
        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 1)  # col 1 = 代码
            if code_item:
                new_order.append(code_item.text())
        if not new_order:
            return

        # 获取原 watchlist 中未在当前视图显示的代码，保持顺序追加到末尾
        displayed = set(new_order)
        codes = cfg.get('stock.watchlist', [])
        names = cfg.get('stock.watchlist_names', [])
        # 构建 code->name 映射
        name_map = dict(zip(codes, names))
        # 重新排列 watchlist
        new_codes = new_order + [c for c in codes if c not in displayed]
        new_names = [name_map.get(c, c) for c in new_codes]
        cfg.set('stock.watchlist', new_codes)
        cfg.set('stock.watchlist_names', new_names)

        # 同步 _last_data 顺序
        data_map = {d['code']: d for d in self._last_data}
        self._last_data = [data_map[c] for c in new_order if c in data_map]
        # 不需要重新 fetch，只重绘
        self._update_tab_counts(self._last_data)
        self._render_table(self._last_data)

    def _move_row(self, row: int, delta: int):
        """将 row 移动 delta 行（负数=上移，正数=下移）"""
        if delta == 0:
            return
        target = max(0, min(self.table.rowCount() - 1, row + delta))
        if target == row:
            return
        # 构建新的顺序列表
        codes = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            if item:
                codes.append(item.text())
        # 移动元素
        code = codes.pop(row)
        codes.insert(target, code)
        # 构建新的 data 列表
        data_map = {d['code']: d for d in self._last_data}
        new_data = [data_map[c] for c in codes if c in data_map]
        # 更新 watchlist
        all_codes = cfg.get('stock.watchlist', [])
        name_map = dict(zip(all_codes, cfg.get('stock.watchlist_names', [])))
        other = [c for c in all_codes if c not in codes]
        new_all = codes + other
        cfg.set('stock.watchlist', new_all)
        cfg.set('stock.watchlist_names', [name_map.get(c, c) for c in new_all])
        # 刷新
        self._last_data = new_data
        self._update_tab_counts(self._last_data)
        self._render_table(self._last_data)

    def _on_data(self, data: list):
        self.lbl_last_update.setText(datetime.now().strftime('%H:%M:%S'))
        self._last_data = data
        self._update_tab_counts(data)
        self._render_table(data)

        # ── 新加代码重试验证 ──
        succeeded = {item['code'] for item in data}
        expired = []
        for code, remaining in list(self._pending_codes.items()):
            if code in succeeded:
                del self._pending_codes[code]   # 验证成功，移除追踪
            else:
                self._pending_codes[code] = remaining - 1
                if self._pending_codes[code] <= 0:
                    expired.append(code)

        for code in expired:
            del self._pending_codes[code]
            self._remove_by_code(code, notify=True)

        alerted_this_batch = []
        for item in data:
            chg_pct = item['change_pct']
            code    = item['code']
            if self._is_trading_time() and abs(chg_pct) >= self._alert_threshold and code not in self._alerted:
                self._alerted.add(code)
                alerted_this_batch.append((item['name'], chg_pct, item['price']))

        if alerted_this_batch:
            lines = [f"{'↑' if p>0 else '↓'} {name}  {'+' if p>0 else ''}{p:.2f}%  ({price:.3f})"
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
            # 新代码加入重试队列，最多 _MAX_ADD_RETRIES 次验证
            self._pending_codes[code] = self._MAX_ADD_RETRIES
        self.input_code.clear()
        self._refresh()

    def _remove_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        code_item = self.table.item(row, 1)  # col 1 = 代码
        if not code_item:
            return
        self._remove_by_code(code_item.text())

    def _remove_by_code(self, code: str, notify: bool = False):
        codes = cfg.get('stock.watchlist', [])
        names = cfg.get('stock.watchlist_names', [])
        if code in codes:
            idx = codes.index(code)
            codes.pop(idx)
            if idx < len(names):
                removed_name = names.pop(idx)
            else:
                removed_name = code
            cfg.set('stock.watchlist', codes)
            cfg.set('stock.watchlist_names', names)
        else:
            removed_name = code
        # 同步从自选分组移除
        custom = cfg.get('stock.custom_group', [])
        if code in custom:
            cfg.set('stock.custom_group', [c for c in custom if c != code])
        self._alerted.discard(code)
        self._pending_codes.pop(code, None)  # 清理重试追踪
        self._last_data = [d for d in self._last_data if d['code'] != code]
        self._update_tab_counts(self._last_data)
        self._render_table(self._last_data)
        self._refresh()
        if notify:
            _notify("📊 行情提醒", f"{removed_name}（{code}）\n多次获取失败，已自动从盯盘列表移除")
