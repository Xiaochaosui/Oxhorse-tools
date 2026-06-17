"""
TODO 模块 - 飞书多维表格（Bitable）集成
支持：新增 / 完成 / 删除 / 备注展开编辑
"""
import threading
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QPushButton, QLineEdit,
    QComboBox, QHeaderView, QGroupBox, QTextEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont
from modules.theme import NEON_COLORS as NC
import modules.config_manager as cfg
from modules.feishu_client import FeishuClient as _SDK, FeishuError


_PRIORITY_MAP = {
    'P0': '🔴P0-高优',
    'P1': '🟡P1-一般',
    'P2': '🟢P2-低优',
}
_PRIORITY_MAP_REV = {v: k for k, v in _PRIORITY_MAP.items()}


def _parse_priority(raw: str) -> str:
    """'🔴P0-高优' → 'P0'，兼容纯 'P0' 格式。"""
    s = str(raw)
    if s in _PRIORITY_MAP_REV:
        return _PRIORITY_MAP_REV[s]
    for p in ('P0', 'P1', 'P2'):
        if p in s:
            return p
    return 'P2'


def _parse_status(f: dict) -> str:
    """兼容布尔 '是否已完成' 和字符串 '状态' 两种字段。"""
    if '是否已完成' in f:
        return '已完成' if f['是否已完成'] else '待处理'
    return str(f.get('状态', f.get('status', '待处理')))


def _parse_created(val) -> str:
    if isinstance(val, (int, float)):
        from datetime import datetime
        return datetime.fromtimestamp(val / 1000).strftime('%Y-%m-%d %H:%M')
    return str(val) if val else ''


def _parse_record(item: dict) -> dict:
    f = item.get('fields', {})
    title = str(f.get('待办事项', f.get('标题', f.get('title', ''))))
    note_raw = f.get('备注', f.get('note', ''))
    note = str(note_raw) if note_raw else ''
    return {
        'record_id': item.get('record_id', ''),
        'title':    title,
        'status':   _parse_status(f),
        'priority': _parse_priority(f.get('优先级', f.get('priority', 'P2'))),
        'note':     note,
        'created':  _parse_created(f.get('创建时间', '')),
    }


PRIORITY_COLORS = {
    "P0": NC['red'],
    "P1": NC['orange'],
    "P2": NC['yellow'],
    "P3": NC['dim'],
}
STATUS_COLORS = {
    "待处理": NC['dim'],
    "进行中": NC['cyan'],
    "已完成": NC['green'],
    "已取消": NC['text_dim'],
}

_GROUP_STYLE = f"""
    QGroupBox {{
        border: 1px solid {NC['border']};
        border-radius: 6px;
        margin-top: 10px;
        color: {NC['dim']};
        font-size: 10px;
        letter-spacing: 2px;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
"""


class FeishuClient(QObject):
    """Qt 信号桥：在后台线程调用 _SDK，结果通过信号回到主线程。"""
    data_ready = pyqtSignal(list)
    sync_done  = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._sdk = _SDK()
        self._refresh_creds()

    def _refresh_creds(self):
        self._sdk.configure(
            cfg.get('feishu.app_id', ''),
            cfg.get('feishu.app_secret', ''),
        )

    def _creds(self):
        return cfg.get('feishu.bitable_app_token', ''), cfg.get('feishu.bitable_table_id', '')

    def _run(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def fetch_records(self):
        self._refresh_creds()
        self._run(self._fetch_run, *self._creds())

    def _fetch_run(self, app_token, table_id):
        try:
            raw = self._sdk.bitable_list(app_token, table_id)
            records = []
            for item in raw:
                f = item.get('fields', {})
                records.append(_parse_record(item))
            self.data_ready.emit(records)
        except Exception:
            self.data_ready.emit([])

    def add_record(self, fields: dict):
        self._refresh_creds()
        self._run(self._add_run, *self._creds(), fields)

    def _add_run(self, app_token, table_id, fields):
        try:
            rid = self._sdk.bitable_add(app_token, table_id, fields)
            self.sync_done.emit(True, rid)
        except Exception as e:
            self.sync_done.emit(False, str(e))

    def update_record(self, record_id: str, fields: dict):
        self._refresh_creds()
        self._run(self._update_run, *self._creds(), record_id, fields)

    def _update_run(self, app_token, table_id, record_id, fields):
        try:
            self._sdk.bitable_update(app_token, table_id, record_id, fields)
            self.sync_done.emit(True, 'update_ok')
        except Exception as e:
            self.sync_done.emit(False, str(e))

    def delete_record(self, record_id: str):
        self._refresh_creds()
        self._run(self._delete_run, *self._creds(), record_id)

    def _delete_run(self, app_token, table_id, record_id):
        try:
            self._sdk.bitable_delete(app_token, table_id, record_id)
            self.sync_done.emit(True, 'delete_ok')
        except Exception as e:
            self.sync_done.emit(False, str(e))


class TodoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = FeishuClient()
        self._client.data_ready.connect(self._on_data)
        self._client.sync_done.connect(self._on_sync)
        self._records = []
        self._pending_add_title = ''   # 等飞书返回 record_id 时用
        self._build_ui()
        self._check_config()
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._fetch)
        self._sync_timer.start(5 * 60 * 1000)

    def _check_config(self):
        if cfg.get('feishu.app_id', ''):
            self._fetch()
        else:
            self._set_status("⚠  请在下方填写飞书配置后点 SAVE", NC['orange'])

    def _set_status(self, text: str, color: str = None):
        self.lbl_status.setText(text)
        if color:
            self.lbl_status.setStyleSheet(f"color:{color}; font-size:11px;")

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # ── 顶栏 ──
        top = QHBoxLayout()
        self.lbl_status = QLabel("TODO  //  飞书多维表格")
        self.lbl_status.setStyleSheet(f"color:{NC['dim']}; font-size:11px; letter-spacing:2px;")
        btn_sync = QPushButton("⟳  SYNC")
        btn_sync.setMinimumWidth(70)
        btn_sync.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        btn_sync.clicked.connect(self._fetch)
        top.addWidget(self.lbl_status)
        top.addStretch()
        top.addWidget(btn_sync)
        root.addLayout(top)

        # ── 主表格：5列 ──
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["P", "标题", "状态", "✓", "✕"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 32)
        self.table.setColumnWidth(2, 68)
        self.table.setColumnWidth(3, 36)
        self.table.setColumnWidth(4, 36)
        self.table.cellClicked.connect(self._on_row_click)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background:#050d18; alternate-background-color:#07111f;
                gridline-color:#0f1e30; border:1px solid {NC['border']};
                font-size:12px;
            }}
            QTableWidget::item {{ padding:4px 6px; color:{NC['text']}; }}
            QTableWidget::item:selected {{ background:#1a3a5c; }}
            QHeaderView::section {{
                background:#050d18; color:{NC['dim']};
                border:none; border-bottom:1px solid {NC['border']};
                padding:4px 4px; font-size:10px; letter-spacing:1px;
            }}
        """)
        root.addWidget(self.table, 4)

        # ── 编辑面板（标题编辑 / 备注）──
        self.edit_frame = QFrame()
        self.edit_frame.setStyleSheet(f"""
            QFrame {{
                background:#07111f;
                border:1px solid {NC['border']};
                border-radius:6px;
            }}
        """)
        edit_layout = QVBoxLayout(self.edit_frame)
        edit_layout.setContentsMargins(10, 8, 10, 8)
        edit_layout.setSpacing(6)

        edit_top = QHBoxLayout()
        self.lbl_edit_title = QLabel("备注")
        self.lbl_edit_title.setStyleSheet(f"color:{NC['cyan']}; font-size:10px; letter-spacing:2px;")
        self.btn_edit_save = QPushButton("SAVE")
        self.btn_edit_save.clicked.connect(self._save_edit_panel)
        edit_top.addWidget(self.lbl_edit_title)
        edit_top.addStretch()
        edit_top.addWidget(self.btn_edit_save)

        # 单行编辑（标题）
        self.edit_line = QLineEdit()
        self.edit_line.setStyleSheet(f"""
            QLineEdit {{
                background:#050d18; border:none; border-bottom:1px solid {NC['border']};
                color:{NC['text']}; font-size:12px; padding:2px 0;
            }}
        """)
        self.edit_line.returnPressed.connect(self._save_edit_panel)
        self.edit_line.hide()

        # 多行编辑（备注）
        self.edit_text = QTextEdit()
        self.edit_text.setFixedHeight(60)
        self.edit_text.setPlaceholderText("点击任意行查看/编辑备注...")
        self.edit_text.setStyleSheet(f"""
            QTextEdit {{
                background:#050d18; border:none;
                color:{NC['text']}; font-size:12px;
            }}
        """)

        edit_layout.addLayout(edit_top)
        edit_layout.addWidget(self.edit_line)
        edit_layout.addWidget(self.edit_text)
        self.edit_frame.hide()
        self._edit_mode = 'note'   # 'note' | 'title' | 'priority'
        root.addWidget(self.edit_frame)

        # 向后兼容
        self.note_frame = self.edit_frame
        self.note_edit  = self.edit_text
        self.lbl_note_title = self.lbl_edit_title

        # ── 新增 ──
        add_group = QGroupBox("NEW TASK")
        add_group.setStyleSheet(_GROUP_STYLE)
        ag = QHBoxLayout(add_group)
        ag.setContentsMargins(10, 14, 10, 10)
        ag.setSpacing(6)

        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("任务标题...")
        self.input_title.returnPressed.connect(self._add_todo)

        self.combo_priority = QComboBox()
        self.combo_priority.addItems(["P0", "P1", "P2"])
        self.combo_priority.setCurrentIndex(1)
        self.combo_priority.setMinimumWidth(55)
        self.combo_priority.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        btn_add = QPushButton("ADD")
        btn_add.setMinimumWidth(50)
        btn_add.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        btn_add.clicked.connect(self._add_todo)

        ag.addWidget(self.input_title)
        ag.addWidget(self.combo_priority)
        ag.addWidget(btn_add)
        root.addWidget(add_group)

        # ── 飞书配置（两行）──
        cfg_group = QGroupBox("FEISHU CONFIG")
        cfg_group.setStyleSheet(_GROUP_STYLE)
        cg = QVBoxLayout(cfg_group)
        cg.setContentsMargins(10, 14, 10, 10)
        cg.setSpacing(4)

        self.input_appid     = QLineEdit(); self.input_appid.setPlaceholderText("App ID")
        self.input_appsecret = QLineEdit(); self.input_appsecret.setPlaceholderText("App Secret")
        self.input_appsecret.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_apptoken  = QLineEdit(); self.input_apptoken.setPlaceholderText("Bitable App Token")
        self.input_tableid   = QLineEdit(); self.input_tableid.setPlaceholderText("Table ID")

        self.input_appid.setText(cfg.get('feishu.app_id', ''))
        self.input_appsecret.setText(cfg.get('feishu.app_secret', ''))
        self.input_apptoken.setText(cfg.get('feishu.bitable_app_token', ''))
        self.input_tableid.setText(cfg.get('feishu.bitable_table_id', ''))

        btn_cfg_save = QPushButton("SAVE CONFIG")
        btn_cfg_save.clicked.connect(self._save_feishu_config)

        row1 = QHBoxLayout(); row1.setSpacing(6)
        row1.addWidget(self.input_appid)
        row1.addWidget(self.input_appsecret)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        row2.addWidget(self.input_apptoken)
        row2.addWidget(self.input_tableid)
        row2.addWidget(btn_cfg_save)

        cg.addLayout(row1)
        cg.addLayout(row2)
        root.addWidget(cfg_group)

        self._selected_record = None  # 当前选中的 record dict

    # ── 数据 ────────────────────────────────────────────────────────────────

    def _fetch(self):
        if not all([cfg.get('feishu.app_id'), cfg.get('feishu.app_secret'),
                    cfg.get('feishu.bitable_app_token'), cfg.get('feishu.bitable_table_id')]):
            return
        self._set_status("⟳ 同步中...", NC['dim'])
        self._client.fetch_records()

    def _on_data(self, records: list):
        self._records = records
        self._render_table(records)
        self._set_status(f"✓  {len(records)} 条  ·  {datetime.now().strftime('%H:%M:%S')}", NC['green'])

    def _sorted_records(self) -> list:
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        return sorted(self._records, key=lambda r: (
            r.get('status') == '已完成',
            order.get(r.get('priority', 'P2'), 99)
        ))

    def _render_table(self, records: list):
        sorted_recs = self._sorted_records()
        self.table.setRowCount(len(sorted_recs))
        for ri, item in enumerate(sorted_recs):
            prio   = item.get('priority', 'P2')
            title  = item.get('title', '')
            status = item.get('status', '待处理')

            p_cell = QTableWidgetItem(prio)
            p_cell.setForeground(QColor(PRIORITY_COLORS.get(prio, NC['text'])))
            p_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            t_cell = QTableWidgetItem(title)
            if status == '已完成':
                t_cell.setForeground(QColor(NC['dim']))
                f = t_cell.font(); f.setStrikeOut(True); t_cell.setFont(f)
            elif status == '进行中':
                t_cell.setForeground(QColor(NC['cyan']))

            s_cell = QTableWidgetItem(status)
            s_cell.setForeground(QColor(STATUS_COLORS.get(status, NC['text'])))
            s_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(ri, 0, p_cell)
            self.table.setItem(ri, 1, t_cell)
            self.table.setItem(ri, 2, s_cell)

            # ✓ Done 按钮
            btn_done = QPushButton("✓")
            btn_done.setToolTip("标记完成")
            btn_done.setStyleSheet(f"""
                QPushButton {{
                    background:#071a07; color:{NC['green']};
                    border:1px solid #1a3a1a; border-radius:3px;
                    font-size:11px; padding:1px 2px;
                }}
                QPushButton:hover {{ background:#0d2a0d; }}
            """)
            btn_done.clicked.connect(lambda _, r=item: self._mark_done(r))
            self.table.setCellWidget(ri, 3, btn_done)

            # ✕ Delete 按钮
            btn_del = QPushButton("✕")
            btn_del.setToolTip("删除")
            btn_del.setStyleSheet(f"""
                QPushButton {{
                    background:#1a0707; color:{NC['red']};
                    border:1px solid #3a1a1a; border-radius:3px;
                    font-size:11px; padding:1px 2px;
                }}
                QPushButton:hover {{ background:#2a0d0d; }}
            """)
            btn_del.clicked.connect(lambda _, r=item: self._delete_todo(r))
            self.table.setCellWidget(ri, 4, btn_del)

    def _on_row_click(self, row, col):
        if col in (3, 4):
            return
        if row < 0 or row >= len(self._records):
            return
        record = self._sorted_records()[row]
        self._selected_record = record
        short = record.get('title', '')[:20]

        if col == 0:
            # 优先级：面板显示 ComboBox
            self._edit_mode = 'priority'
            self.lbl_edit_title.setText(f"优先级  //  {short}")
            self.btn_edit_save.setText("SAVE")
            self.edit_line.show()
            self.edit_text.hide()
            # 复用 edit_line 位置放 combo，但直接用独立 combo 弹窗更可靠
            self._show_priority_panel(record)
            return

        if col == 1:
            # 标题：面板显示单行输入框
            self._edit_mode = 'title'
            self.lbl_edit_title.setText(f"标题  //  {short}")
            self.btn_edit_save.setText("SAVE")
            self.edit_line.setText(record.get('title', ''))
            self.edit_line.show()
            self.edit_text.hide()
            self.edit_frame.show()
            self.edit_line.setFocus()
            self.edit_line.selectAll()
            return

        # 其他列：备注
        self._edit_mode = 'note'
        self.lbl_edit_title.setText(f"备注  //  {short}")
        self.btn_edit_save.setText("SAVE NOTE")
        note = record.get('note', '')
        self.edit_text.setPlainText(note if note != 'None' else '')
        self.edit_line.hide()
        self.edit_text.show()
        self.edit_frame.show()

    def _show_priority_panel(self, record: dict):
        """在面板里显示优先级下拉。"""
        self.edit_line.hide()
        self.edit_text.hide()

        if not hasattr(self, '_prio_combo'):
            self._prio_combo = QComboBox()
            self._prio_combo.addItems(["P0", "P1", "P2"])
            self._prio_combo.setStyleSheet(f"""
                QComboBox {{
                    background:#050d18; color:{NC['cyan']};
                    border:1px solid {NC['border']}; border-radius:3px;
                    font-size:12px; padding:3px 6px;
                }}
                QComboBox QAbstractItemView {{
                    background:#0a1422; color:{NC['text']};
                    selection-background-color:#1a3a5c;
                }}
            """)
            self.edit_frame.layout().addWidget(self._prio_combo)

        self._prio_combo.setCurrentText(record.get('priority', 'P1'))
        self._prio_combo.show()
        self.edit_frame.show()

    def _save_edit_panel(self):
        if not self._selected_record:
            return
        record = self._selected_record
        record_id = record.get('record_id', '')
        has_creds = bool(record_id and cfg.get('feishu.app_id'))

        if self._edit_mode == 'title':
            new_val = self.edit_line.text().strip()
            if new_val and new_val != record.get('title'):
                record['title'] = new_val
                if has_creds:
                    self._client.update_record(record_id, {'待办事项': new_val})
                    self._set_status("⟳ 同步标题...", NC['dim'])
            self._render_table(self._records)

        elif self._edit_mode == 'priority':
            new_val = self._prio_combo.currentText()
            if new_val != record.get('priority'):
                record['priority'] = new_val
                if has_creds:
                    self._client.update_record(record_id, {'优先级': _PRIORITY_MAP.get(new_val, '🟡P1-一般')})
                    self._set_status("⟳ 同步优先级...", NC['dim'])
            self._render_table(self._records)

        elif self._edit_mode == 'note':
            note_text = self.edit_text.toPlainText().strip()
            record['note'] = note_text
            if has_creds:
                self._client.update_record(record_id, {'备注': note_text})
                self._set_status("⟳ 同步备注...", NC['dim'])
            else:
                self._set_status("备注已保存（本地）", NC['cyan'])

    # 向后兼容旧引用
    def _save_note(self):
        self._edit_mode = 'note'
        self._save_edit_panel()

    def _add_todo(self):
        title = self.input_title.text().strip()
        if not title:
            return
        priority = self.combo_priority.currentText()
        new_item = {
            'record_id': '', 'title': title,
            'priority': priority, 'status': '待处理',
            'note': '', 'created': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        self._records.append(new_item)
        self._render_table(self._records)
        self.input_title.clear()
        if cfg.get('feishu.app_id'):
            self._pending_add_title = title
            prio_label = _PRIORITY_MAP.get(priority, '🟡P1-一般')
            self._client.add_record({'待办事项': title, '优先级': prio_label, '是否已完成': False})

    def _mark_done(self, record: dict):
        for r in self._records:
            if r is record or (r.get('record_id') and r.get('record_id') == record.get('record_id')):
                r['status'] = '已完成'
                break
        self._render_table(self._records)
        if cfg.get('feishu.app_id') and record.get('record_id'):
            self._client.update_record(record['record_id'], {'是否已完成': True})

    def _delete_todo(self, record: dict):
        record_id = record.get('record_id', '')
        self._records = [r for r in self._records if r is not record]
        self._render_table(self._records)
        if self._selected_record is record:
            self.note_frame.hide()
            self._selected_record = None
        if cfg.get('feishu.app_id') and record_id:
            self._client.delete_record(record_id)

    def _on_sync(self, ok: bool, msg: str):
        if not ok:
            self._set_status(f"✗  {msg}", NC['red'])
            return
        # add_record 成功时 msg 是新 record_id
        if msg and msg.startswith('rec') and self._pending_add_title:
            for r in self._records:
                if r.get('title') == self._pending_add_title and not r.get('record_id'):
                    r['record_id'] = msg
                    break
            self._pending_add_title = ''
            self._set_status("✓  已同步到飞书", NC['green'])
        elif msg in ('update_ok', 'delete_ok'):
            self._set_status("✓  操作已同步", NC['green'])
        else:
            self._set_status(f"✓  {msg}", NC['green'])

    def _save_feishu_config(self):
        s = cfg.load()
        s['feishu']['app_id']              = self.input_appid.text().strip()
        s['feishu']['app_secret']          = self.input_appsecret.text().strip()
        s['feishu']['bitable_app_token']   = self.input_apptoken.text().strip()
        s['feishu']['bitable_table_id']    = self.input_tableid.text().strip()
        cfg.save(s)
        self._check_config()
