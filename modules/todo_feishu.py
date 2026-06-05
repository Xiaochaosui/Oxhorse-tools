"""
TODO 模块 - 飞书多维表格（Bitable）集成
支持：新增 / 完成 / 删除 / 备注展开编辑
"""
import threading
import time
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
    data_ready  = pyqtSignal(list)
    sync_done   = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._token = None
        self._token_expiry = 0

    def _get_token(self, app_id: str, app_secret: str) -> str:
        import requests
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        resp = requests.post(
            'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
            json={'app_id': app_id, 'app_secret': app_secret}, timeout=10
        )
        data = resp.json()
        self._token = data.get('tenant_access_token', '')
        self._token_expiry = time.time() + data.get('expire', 7200)
        return self._token

    def _creds(self):
        return (
            cfg.get('feishu.bitable_app_token', ''),
            cfg.get('feishu.bitable_table_id', ''),
            cfg.get('feishu.app_id', ''),
            cfg.get('feishu.app_secret', ''),
        )

    def fetch_records(self):
        threading.Thread(target=self._fetch_run, args=self._creds(), daemon=True).start()

    def _fetch_run(self, app_token, table_id, app_id, app_secret):
        try:
            import requests
            token = self._get_token(app_id, app_secret)
            headers = {'Authorization': f'Bearer {token}'}
            url = f'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records'
            params = {'page_size': 100}
            records = []
            while True:
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                data = resp.json().get('data', {})
                for item in data.get('items', []):
                    f = item.get('fields', {})
                    records.append({
                        'record_id': item.get('record_id', ''),
                        'title':    str(f.get('标题', f.get('title', ''))),
                        'status':   str(f.get('状态', f.get('status', '待处理'))),
                        'priority': str(f.get('优先级', f.get('priority', 'P2'))),
                        'note':     str(f.get('备注', f.get('note', ''))),
                        'created':  str(f.get('创建时间', '')),
                    })
                if not data.get('has_more') or not data.get('page_token'):
                    break
                params['page_token'] = data['page_token']
            self.data_ready.emit(records)
        except Exception:
            self.data_ready.emit([])

    def add_record(self, fields: dict):
        threading.Thread(target=self._add_run, args=(*self._creds(), fields), daemon=True).start()

    def _add_run(self, app_token, table_id, app_id, app_secret, fields):
        try:
            import requests
            token = self._get_token(app_id, app_secret)
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            url = f'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records'
            resp = requests.post(url, headers=headers, json={'fields': fields}, timeout=10)
            d = resp.json()
            ok = d.get('code', -1) == 0
            # 返回新 record_id
            rid = d.get('data', {}).get('record', {}).get('record_id', '')
            self.sync_done.emit(ok, rid if ok else d.get('msg', '失败'))
        except Exception as e:
            self.sync_done.emit(False, str(e))

    def update_record(self, record_id: str, fields: dict):
        threading.Thread(target=self._update_run, args=(*self._creds(), record_id, fields), daemon=True).start()

    def _update_run(self, app_token, table_id, app_id, app_secret, record_id, fields):
        try:
            import requests
            token = self._get_token(app_id, app_secret)
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            url = f'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}'
            resp = requests.put(url, headers=headers, json={'fields': fields}, timeout=10)
            ok = resp.json().get('code', -1) == 0
            self.sync_done.emit(ok, 'update_ok' if ok else resp.json().get('msg', '失败'))
        except Exception as e:
            self.sync_done.emit(False, str(e))

    def delete_record(self, record_id: str):
        threading.Thread(target=self._delete_run, args=(*self._creds(), record_id), daemon=True).start()

    def _delete_run(self, app_token, table_id, app_id, app_secret, record_id):
        try:
            import requests
            token = self._get_token(app_id, app_secret)
            headers = {'Authorization': f'Bearer {token}'}
            url = f'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}'
            resp = requests.delete(url, headers=headers, timeout=10)
            ok = resp.json().get('code', -1) == 0
            self.sync_done.emit(ok, 'delete_ok' if ok else resp.json().get('msg', '删除失败'))
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
        btn_sync.setFixedWidth(80)
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

        # ── 备注展开面板 ──
        self.note_frame = QFrame()
        self.note_frame.setStyleSheet(f"""
            QFrame {{
                background:#07111f;
                border:1px solid {NC['border']};
                border-radius:6px;
            }}
        """)
        note_layout = QVBoxLayout(self.note_frame)
        note_layout.setContentsMargins(10, 8, 10, 8)
        note_layout.setSpacing(6)

        note_top = QHBoxLayout()
        self.lbl_note_title = QLabel("备注")
        self.lbl_note_title.setStyleSheet(f"color:{NC['cyan']}; font-size:10px; letter-spacing:2px;")
        btn_save_note = QPushButton("SAVE NOTE")
        btn_save_note.setFixedWidth(90)
        btn_save_note.clicked.connect(self._save_note)
        note_top.addWidget(self.lbl_note_title)
        note_top.addStretch()
        note_top.addWidget(btn_save_note)

        self.note_edit = QTextEdit()
        self.note_edit.setFixedHeight(60)
        self.note_edit.setPlaceholderText("点击任意行查看/编辑备注...")
        self.note_edit.setStyleSheet(f"""
            QTextEdit {{
                background:#050d18; border:none;
                color:{NC['text']}; font-size:12px;
            }}
        """)
        note_layout.addLayout(note_top)
        note_layout.addWidget(self.note_edit)
        self.note_frame.hide()
        root.addWidget(self.note_frame)

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
        self.combo_priority.addItems(["P0", "P1", "P2", "P3"])
        self.combo_priority.setCurrentIndex(2)
        self.combo_priority.setFixedWidth(55)

        self.combo_status = QComboBox()
        self.combo_status.addItems(["待处理", "进行中", "已完成", "已取消"])
        self.combo_status.setFixedWidth(78)

        btn_add = QPushButton("ADD")
        btn_add.setFixedWidth(55)
        btn_add.clicked.connect(self._add_todo)

        ag.addWidget(self.input_title)
        ag.addWidget(self.combo_priority)
        ag.addWidget(self.combo_status)
        ag.addWidget(btn_add)
        root.addWidget(add_group)

        # ── 飞书配置 ──
        cfg_group = QGroupBox("FEISHU CONFIG")
        cfg_group.setStyleSheet(_GROUP_STYLE)
        cg = QHBoxLayout(cfg_group)
        cg.setContentsMargins(10, 14, 10, 10)
        cg.setSpacing(6)

        self.input_appid     = QLineEdit(); self.input_appid.setPlaceholderText("App ID")
        self.input_appsecret = QLineEdit(); self.input_appsecret.setPlaceholderText("App Secret")
        self.input_appsecret.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_apptoken  = QLineEdit(); self.input_apptoken.setPlaceholderText("Bitable App Token")
        self.input_tableid   = QLineEdit(); self.input_tableid.setPlaceholderText("Table ID")

        self.input_appid.setText(cfg.get('feishu.app_id', ''))
        self.input_appsecret.setText(cfg.get('feishu.app_secret', ''))
        self.input_apptoken.setText(cfg.get('feishu.bitable_app_token', ''))
        self.input_tableid.setText(cfg.get('feishu.bitable_table_id', ''))

        btn_cfg_save = QPushButton("SAVE")
        btn_cfg_save.setFixedWidth(55)
        btn_cfg_save.clicked.connect(self._save_feishu_config)

        for w in [self.input_appid, self.input_appsecret, self.input_apptoken, self.input_tableid]:
            cg.addWidget(w)
        cg.addWidget(btn_cfg_save)
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

    def _render_table(self, records: list):
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        records = sorted(records, key=lambda r: (
            r.get('status') == '已完成',
            order.get(r.get('priority', 'P2'), 99)
        ))
        self.table.setRowCount(len(records))
        for ri, item in enumerate(records):
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
        if col in (3, 4):  # 按钮列不展开备注
            return
        if row < 0 or row >= len(self._records):
            return
        # 找到排序后第 row 行对应的 record（重新排序和 _render_table 一致）
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        sorted_records = sorted(self._records, key=lambda r: (
            r.get('status') == '已完成',
            order.get(r.get('priority', 'P2'), 99)
        ))
        self._selected_record = sorted_records[row]
        note = self._selected_record.get('note', '')
        title = self._selected_record.get('title', '')
        self.lbl_note_title.setText(f"备注  //  {title[:20]}")
        self.note_edit.setPlainText(note if note != 'None' else '')
        self.note_frame.show()

    def _save_note(self):
        if not self._selected_record:
            return
        note_text = self.note_edit.toPlainText().strip()
        record_id = self._selected_record.get('record_id', '')
        self._selected_record['note'] = note_text
        if record_id and cfg.get('feishu.app_id'):
            self._client.update_record(record_id, {'备注': note_text})
        self._set_status("备注已保存...", NC['cyan'])

    def _add_todo(self):
        title = self.input_title.text().strip()
        if not title:
            return
        priority = self.combo_priority.currentText()
        status   = self.combo_status.currentText()
        new_item = {
            'record_id': '', 'title': title,
            'priority': priority, 'status': status,
            'note': '', 'created': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        self._records.append(new_item)
        self._render_table(self._records)
        self.input_title.clear()
        if cfg.get('feishu.app_id'):
            self._pending_add_title = title
            self._client.add_record({'标题': title, '优先级': priority, '状态': status})

    def _mark_done(self, record: dict):
        for r in self._records:
            if r is record or (r.get('record_id') and r.get('record_id') == record.get('record_id')):
                r['status'] = '已完成'
                break
        self._render_table(self._records)
        if cfg.get('feishu.app_id') and record.get('record_id'):
            self._client.update_record(record['record_id'], {'状态': '已完成'})

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
