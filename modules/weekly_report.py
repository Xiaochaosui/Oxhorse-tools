"""
周报模块 — 从飞书 TODO 自动生成本周工作总结
支持：自动生成草稿 / 编辑 / 写入飞书文档 / 发给自己
"""
import threading
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTextEdit, QGroupBox, QLineEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont

from modules.theme import NEON_COLORS as NC
import modules.config_manager as cfg
from modules.feishu_client import FeishuClient as _SDK
from modules.todo_feishu import _parse_record


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


def _week_range():
    """返回本周 (Mon, Sun) 的 date 对象。"""
    today = datetime.today()
    mon = today - timedelta(days=today.weekday())
    sun = mon + timedelta(days=6)
    return mon.date(), sun.date()


def _build_draft(records: list[dict]) -> str:
    mon, sun = _week_range()
    done    = [r for r in records if r.get('status') == '已完成']
    pending = [r for r in records if r.get('status') in ('待处理', '进行中')]

    lines = [
        f"本周工作总结（{mon.strftime('%Y-%m-%d')} ~ {sun.strftime('%Y-%m-%d')}）",
        "",
        "【已完成】",
    ]
    if done:
        for r in done:
            note = r.get('note', '')
            note_part = f"  备注：{note}" if note and note != 'None' else ''
            lines.append(f"  [{r.get('priority','P2')}] {r.get('title','')}{note_part}")
    else:
        lines.append("  （本周暂无已完成任务）")

    lines += ["", "【待处理 / 进行中】"]
    if pending:
        for r in pending:
            lines.append(f"  [{r.get('priority','P2')}] {r.get('title','')}  [{r.get('status','')}]")
    else:
        lines.append("  （无）")

    lines += ["", "【下周计划】", "  （请补充）"]
    return "\n".join(lines)


class _Client(QObject):
    gen_done = pyqtSignal(str)
    op_done  = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._sdk = _SDK()

    def _refresh(self):
        self._sdk.configure(
            cfg.get('feishu.app_id', ''),
            cfg.get('feishu.app_secret', ''),
        )

    # ── 生成 ────────────────────────────────────────────────────────────────

    def fetch_and_gen(self):
        self._refresh()
        threading.Thread(target=self._gen_run, daemon=True).start()

    def _gen_run(self):
        try:
            app_token = cfg.get('feishu.bitable_app_token', '')
            table_id  = cfg.get('feishu.bitable_table_id', '')
            if app_token and table_id:
                raw = self._sdk.bitable_list(app_token, table_id)
                records = [_parse_record(item) for item in raw]
            else:
                records = []
            self.gen_done.emit(_build_draft(records))
        except Exception as e:
            self.gen_done.emit(_build_draft([]))

    # ── 写入文档 ─────────────────────────────────────────────────────────────

    def write_doc(self, text: str):
        self._refresh()
        threading.Thread(target=self._doc_run, args=(text,), daemon=True).start()

    def _doc_run(self, text: str):
        try:
            doc_id = cfg.get('feishu.weekly_report_doc_id', '')
            if not doc_id:
                self.op_done.emit(False, '未配置文档 ID')
                return
            self._sdk.doc_append_text(doc_id, text)
            self.op_done.emit(True, '已写入飞书文档')
        except Exception as e:
            self.op_done.emit(False, str(e))

    # ── 发给自己 ──────────────────────────────────────────────────────────────

    def send_self(self, text: str):
        self._refresh()
        threading.Thread(target=self._msg_run, args=(text,), daemon=True).start()

    def _msg_run(self, text: str):
        try:
            open_id = cfg.get('feishu.self_open_id', '')
            if not open_id:
                self.op_done.emit(False, '未配置 open_id')
                return
            self._sdk.msg_send_text(open_id, text)
            self.op_done.emit(True, '已发送给自己')
        except Exception as e:
            self.op_done.emit(False, str(e))


class WeeklyReportWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = _Client()
        self._client.gen_done.connect(self._on_gen)
        self._client.op_done.connect(self._on_op)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # ── 顶栏 ──
        top = QHBoxLayout()
        self.lbl_status = QLabel("WEEKLY REPORT  //  周报")
        self.lbl_status.setStyleSheet(
            f"color:{NC['dim']}; font-size:11px; letter-spacing:2px;"
        )
        btn_gen = QPushButton("⟳  生成")
        btn_gen.setFixedWidth(80)
        btn_gen.clicked.connect(self._generate)
        top.addWidget(self.lbl_status)
        top.addStretch()
        top.addWidget(btn_gen)
        root.addLayout(top)

        # ── 日期范围栏 ──
        mon, sun = _week_range()
        date_frame = QFrame()
        date_frame.setStyleSheet(f"""
            QFrame {{
                background: #07111f;
                border: 1px solid {NC['border']};
                border-radius: 6px;
            }}
        """)
        date_layout = QHBoxLayout(date_frame)
        date_layout.setContentsMargins(12, 6, 12, 6)
        lbl_week = QLabel(f"本周：{mon.strftime('%Y-%m-%d')}  ~  {sun.strftime('%Y-%m-%d')}")
        lbl_week.setStyleSheet(f"color:{NC['cyan']}; font-size:11px; letter-spacing:1px;")
        date_layout.addWidget(lbl_week)
        date_layout.addStretch()
        root.addWidget(date_frame)

        # ── 可编辑文本区 ──
        self.report_edit = QTextEdit()
        self.report_edit.setPlaceholderText("点击「生成」从飞书 TODO 自动生成周报草稿，生成后可在此编辑...")
        self.report_edit.setStyleSheet(f"""
            QTextEdit {{
                background: #050d18;
                border: 1px solid {NC['border']};
                border-radius: 6px;
                color: {NC['text']};
                font-size: 12px;
                padding: 8px;
            }}
        """)
        font = QFont("Monospace", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.report_edit.setFont(font)
        root.addWidget(self.report_edit, 1)

        # ── 操作按钮 ──
        btn_row = QHBoxLayout()
        btn_doc = QPushButton("写入文档")
        btn_doc.setFixedHeight(30)
        btn_doc.setStyleSheet(f"""
            QPushButton {{
                background: #071a07; color: {NC['green']};
                border: 1px solid #1a3a1a; border-radius: 4px;
                font-size: 12px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: #0d2a0d; }}
        """)
        btn_doc.clicked.connect(self._write_doc)

        btn_msg = QPushButton("发给自己")
        btn_msg.setFixedHeight(30)
        btn_msg.setStyleSheet(f"""
            QPushButton {{
                background: #07101a; color: {NC['cyan']};
                border: 1px solid #1a2e3a; border-radius: 4px;
                font-size: 12px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: #0d1e2a; }}
        """)
        btn_msg.clicked.connect(self._send_self)

        btn_row.addWidget(btn_doc)
        btn_row.addWidget(btn_msg)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── 配置区 ──
        cfg_group = QGroupBox("FEISHU CONFIG")
        cfg_group.setStyleSheet(_GROUP_STYLE)
        cg = QHBoxLayout(cfg_group)
        cg.setContentsMargins(10, 14, 10, 10)
        cg.setSpacing(6)

        self.input_doc_id  = QLineEdit()
        self.input_doc_id.setPlaceholderText("周报文档 ID（doc_id）")
        self.input_doc_id.setText(cfg.get('feishu.weekly_report_doc_id', ''))

        self.input_open_id = QLineEdit()
        self.input_open_id.setPlaceholderText("自己的 open_id")
        self.input_open_id.setText(cfg.get('feishu.self_open_id', ''))

        btn_cfg_save = QPushButton("SAVE")
        btn_cfg_save.setFixedWidth(55)
        btn_cfg_save.clicked.connect(self._save_config)

        cg.addWidget(self.input_doc_id)
        cg.addWidget(self.input_open_id)
        cg.addWidget(btn_cfg_save)
        root.addWidget(cfg_group)

    # ── 操作 ─────────────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str = None):
        self.lbl_status.setText(text)
        if color:
            self.lbl_status.setStyleSheet(f"color:{color}; font-size:11px;")

    def _generate(self):
        self._set_status("⟳ 正在从飞书拉取数据...", NC['dim'])
        self._client.fetch_and_gen()

    def _on_gen(self, draft: str):
        self.report_edit.setPlainText(draft)
        self._set_status("✓  草稿已生成，可编辑后发送", NC['green'])

    def _write_doc(self):
        text = self.report_edit.toPlainText().strip()
        if not text:
            self._set_status("✗  内容为空", NC['red'])
            return
        self._set_status("⟳ 写入文档中...", NC['dim'])
        self._client.write_doc(text)

    def _send_self(self):
        text = self.report_edit.toPlainText().strip()
        if not text:
            self._set_status("✗  内容为空", NC['red'])
            return
        self._set_status("⟳ 发送中...", NC['dim'])
        self._client.send_self(text)

    def _on_op(self, ok: bool, msg: str):
        self._set_status(
            f"✓  {msg}" if ok else f"✗  {msg}",
            NC['green'] if ok else NC['red'],
        )

    def _save_config(self):
        s = cfg.load()
        s['feishu']['weekly_report_doc_id'] = self.input_doc_id.text().strip()
        s['feishu']['self_open_id']         = self.input_open_id.text().strip()
        cfg.save(s)
        self._set_status("✓  配置已保存", NC['cyan'])
