"""
LifeLog — 时间胶囊 + 剪贴板数据库
独立弹窗，风格与 Oxhorse-tools 完全一致（深色科技风）
从托盘菜单打开，与 HealthStatsWindow 同等地位
"""
import sys
from datetime import datetime, date

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QPushButton, QLineEdit, QTextEdit,
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsTextItem, QCalendarWidget, QSplitter,
    QStackedWidget, QTabBar, QApplication, QDialog,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QDate, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import (
    QColor, QBrush, QPen, QPainter, QFont,
    QPixmap, QTextCharFormat, QKeySequence, QShortcut,
)

import modules.lifelog_db as db
from modules.theme import NEON_COLORS as NC

# ── 本模块色彩（沿用项目 NC 体系，补充少量语义色）────────────────────────
_C = {
    "cyan":    NC["cyan"],
    "green":   NC["green"],
    "orange":  NC["orange"],
    "purple":  NC["purple"],
    "dim":     NC["dim"],
    "text":    NC["text"],
    "bg":      NC["bg_dark"],
    "bg_card": NC["bg_card"],
    "bg_mid":  NC["bg_mid"],
    "border":  NC["border"],
    "red":     NC["red"],
}

TYPE_COLOR = {
    "window":          _C["cyan"],
    "clipboard_text":  _C["purple"],
    "clipboard_image": _C["orange"],
}
TYPE_LABEL = {
    "window":          "窗口",
    "clipboard_text":  "文字",
    "clipboard_image": "图片",
}
TYPE_ICON = {
    "window":          "⊞",
    "clipboard_text":  "⎘",
    "clipboard_image": "🖼",
}


# ── 公共小组件 ────────────────────────────────────────────────────────────

def _sec_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{_C['cyan']}; font-size:10px; letter-spacing:2px;"
        f" padding:6px 0 2px 0;"
    )
    return lbl


def _h_line() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color:{_C['border']}; max-height:1px;")
    return f


def _dark_btn(text: str, color: str = None) -> QPushButton:
    c = color or _C["cyan"]
    btn = QPushButton(text)
    btn.setStyleSheet(f"""
        QPushButton {{
            background:{_C['bg_card']}; color:{c};
            border:1px solid {_C['border']}; border-radius:4px;
            padding:4px 14px; font-size:11px; letter-spacing:0.5px;
        }}
        QPushButton:hover   {{ background:#1a3a5c; border-color:{c}; color:{c}; }}
        QPushButton:pressed {{ background:#0d2a45; }}
    """)
    return btn


def _search_input(placeholder: str = "") -> QLineEdit:
    w = QLineEdit(); w.setPlaceholderText(placeholder)
    w.setStyleSheet(f"""
        QLineEdit {{
            background:{_C['bg_mid']}; color:{_C['text']};
            border:1px solid {_C['border']}; border-radius:4px;
            padding:5px 10px; font-size:12px;
        }}
        QLineEdit:focus {{ border-color:{_C['cyan']}; }}
    """)
    return w


# ── 图片放大弹窗 ──────────────────────────────────────────────────────────

class _ImageZoomDialog(QDialog):
    """全屏可缩放图片查看器，ESC / 点击关闭"""

    def __init__(self, pixmap: QPixmap, title: str = "", parent=None):
        super().__init__(parent)
        self._orig = pixmap
        self.setWindowTitle(title or "// IMAGE VIEWER")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background:transparent;")

        # 占满主屏 80%
        screen = QApplication.primaryScreen().geometry()
        w = int(screen.width()  * 0.82)
        h = int(screen.height() * 0.82)
        self.resize(w, h)
        self.move(
            screen.center().x() - w // 2,
            screen.center().y() - h // 2,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # 外层容器（深色卡片）
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background:rgba(10,14,26,245);
                border:1px solid {_C['border']};
                border-radius:10px;
            }}
        """)
        cl = QVBoxLayout(card); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        # 标题栏
        hdr = QFrame()
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(f"""
            QFrame {{
                background:#060d1c;
                border-top-left-radius:10px; border-top-right-radius:10px;
                border-bottom:1px solid {_C['border']};
            }}
        """)
        hl = QHBoxLayout(hdr); hl.setContentsMargins(12, 0, 12, 0); hl.setSpacing(8)
        for color in ['#ff5f57', '#febc2e', '#28c840']:
            dot = QFrame(); dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"QFrame {{ background:{color}; border-radius:5px; }}")
            hl.addWidget(dot)
        hl.addSpacing(8)
        lbl = QLabel(title or "// IMAGE VIEWER")
        lbl.setStyleSheet(f"color:{_C['dim']}; font-size:10px; letter-spacing:2px;")
        hl.addWidget(lbl); hl.addStretch()
        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:#ff5f57;
                border:none; font-size:16px; }}
            QPushButton:hover {{ background:rgba(255,95,87,0.15); border-radius:4px; }}
        """)
        close_btn.clicked.connect(self.close)
        hl.addWidget(close_btn)
        cl.addWidget(hdr)

        # 图片区（居中显示，保持比例）
        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet(
            f"background:{_C['bg_dark']}; border:none;"
        )
        self._img_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cl.addWidget(self._img_lbl, stretch=1)

        # 底部按钮栏
        footer = QFrame()
        footer.setFixedHeight(40)
        footer.setStyleSheet(f"""
            QFrame {{
                background:#060d1c;
                border-top:1px solid {_C['border']};
                border-bottom-left-radius:10px; border-bottom-right-radius:10px;
            }}
        """)
        fl = QHBoxLayout(footer); fl.setContentsMargins(12, 0, 12, 0); fl.setSpacing(8)
        fl.addStretch()

        hint = QLabel("ESC / 点击空白关闭")
        hint.setStyleSheet(f"color:{_C['dim']}; font-size:10px;")
        fl.addWidget(hint)

        copy_img_btn = _dark_btn("COPY IMAGE", _C["orange"])
        copy_img_btn.clicked.connect(self._copy_image)
        fl.addWidget(copy_img_btn)
        cl.addWidget(footer)

        root.addWidget(card)

        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        self._update_image()

    def _update_image(self):
        avail_w = self.width()  - 2
        avail_h = self.height() - 32 - 40 - 2
        if avail_w > 0 and avail_h > 0 and not self._orig.isNull():
            self._img_lbl.setPixmap(
                self._orig.scaled(avail_w, avail_h,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            )

    def resizeEvent(self, e):
        super().resizeEvent(e); self._update_image()

    def mousePressEvent(self, e):
        # 点击空白处关闭
        if e.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(e.position().toPoint())
            if child is None or child is self:
                self.close()
        super().mousePressEvent(e)

    def _copy_image(self):
        QApplication.clipboard().setPixmap(self._orig)


# ── 详情面板 ──────────────────────────────────────────────────────────────

class _DetailPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background:{_C['bg_card']}; border:1px solid {_C['border']};
                border-radius:6px;
            }}
        """)
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)

        self._title = QLabel("// 选择条目查看详情")
        self._title.setWordWrap(True)
        self._title.setStyleSheet(f"color:{_C['cyan']}; font-size:12px; font-weight:bold;")
        lay.addWidget(self._title)

        self._meta = QLabel("")
        self._meta.setStyleSheet(f"color:{_C['dim']}; font-size:10px; letter-spacing:1px;")
        lay.addWidget(self._meta)

        lay.addWidget(_h_line())

        self._text_box = QTextEdit()
        self._text_box.setReadOnly(True)
        self._text_box.setStyleSheet(f"""
            QTextEdit {{
                background:{_C['bg_mid']}; color:{_C['text']};
                border:none; border-radius:4px; padding:8px; font-size:12px;
            }}
        """)
        lay.addWidget(self._text_box, stretch=1)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet(
            f"background:{_C['bg_mid']}; border-radius:4px; border:none;"
        )
        self._img_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._img_lbl.hide()
        lay.addWidget(self._img_lbl, stretch=1)

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self._copy_text_btn = _dark_btn("COPY TEXT")
        self._copy_text_btn.clicked.connect(self._copy_text)
        btn_row.addWidget(self._copy_text_btn)

        self._copy_img_btn = _dark_btn("COPY IMAGE", _C["orange"])
        self._copy_img_btn.clicked.connect(self._copy_image)
        self._copy_img_btn.hide()
        btn_row.addWidget(self._copy_img_btn)

        self._zoom_btn = _dark_btn("ZOOM  ⤢", _C["cyan"])
        self._zoom_btn.clicked.connect(self._zoom_image)
        self._zoom_btn.hide()
        btn_row.addWidget(self._zoom_btn)

        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._current: dict | None = None
        self._current_pix: QPixmap | None = None

    def show_event(self, data: dict):
        self._current = data
        t  = data.get("type", "")
        dt = datetime.fromtimestamp(data["ts"])
        self._title.setText(
            data.get("window_title") or data.get("content_text", "")[:60]
            or data.get("app_name", "") or "(无内容)"
        )
        self._meta.setText(
            f"{data.get('app_name','')}   //   "
            f"{dt.strftime('%Y-%m-%d  %H:%M:%S')}   //   {TYPE_LABEL.get(t,t)}"
        )
        img_path = data.get("content_path", "") if t in ("clipboard_image", "window") else ""
        if img_path:
            pix = QPixmap(img_path)
            self._current_pix = pix if not pix.isNull() else None
            self._text_box.hide()
            self._copy_text_btn.hide()
            self._img_lbl.show()
            self._copy_img_btn.setVisible(self._current_pix is not None)
            self._zoom_btn.setVisible(self._current_pix is not None)
            if self._current_pix:
                self._img_lbl.setPixmap(
                    self._current_pix.scaled(
                        self._img_lbl.width() or 320, 300,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self._img_lbl.mousePressEvent = lambda _e: self._zoom_image()
        else:
            self._current_pix = None
            self._img_lbl.hide()
            self._copy_img_btn.hide()
            self._zoom_btn.hide()
            self._text_box.show()
            self._copy_text_btn.show()
            self._text_box.setPlainText(data.get("content_text", "") or "")

    def _copy_text(self):
        if self._current and self._current.get("content_text"):
            QApplication.clipboard().setText(self._current["content_text"])

    def _copy_image(self):
        if self._current_pix:
            QApplication.clipboard().setPixmap(self._current_pix)

    def _zoom_image(self):
        if not self._current_pix:
            return
        t = (self._current or {}).get("type", "")
        title = f"// {TYPE_LABEL.get(t,'IMAGE')}  ·  " + (
            (self._current or {}).get("window_title")
            or (self._current or {}).get("app_name", "")
            or ""
        )
        dlg = _ImageZoomDialog(self._current_pix, title, parent=self)
        dlg.exec()


# ── 事件行 ─────────────────────────────────────────────────────────────────

class _EventRow(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, data: dict, compact=False, parent=None):
        super().__init__(parent)
        self._data = data
        h = 48 if compact else 58
        self.setFixedHeight(h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background:{_C['bg_mid']}; border:1px solid {_C['border']};
                border-radius:4px;
            }}
            QFrame:hover {{
                background:#0f1e35; border-color:{_C['cyan']};
            }}
        """)
        row = QHBoxLayout(self); row.setContentsMargins(8, 4, 8, 4); row.setSpacing(8)

        # 类型标签
        t     = data.get("type", "")
        color = TYPE_COLOR.get(t, _C["dim"])
        icon  = TYPE_ICON.get(t, "•")
        ic = QLabel(icon)
        ic.setFixedSize(28, 28)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet(
            f"color:{color}; font-size:{'12' if compact else '14'}px;"
            f" background:rgba({_hex_to_rgb(color)},0.12);"
            f" border-radius:3px; border:none;"
        )
        row.addWidget(ic)

        info = QVBoxLayout(); info.setSpacing(1)
        title = (data.get("window_title") or data.get("content_text","")[:60]
                 or data.get("app_name","") or "")
        t_lbl = QLabel((title[:56] + "…") if len(title) > 56 else title)
        t_lbl.setStyleSheet(
            f"color:{_C['text']}; font-size:{'11' if compact else '12'}px;"
        )
        info.addWidget(t_lbl)

        dt  = datetime.fromtimestamp(data["ts"])
        sub = (f"{data.get('app_name','')}  ·  " if data.get("app_name") else "") \
            + dt.strftime("%H:%M:%S" if compact else "%m-%d  %H:%M")
        s_lbl = QLabel(sub)
        s_lbl.setStyleSheet(f"color:{_C['dim']}; font-size:10px;")
        info.addWidget(s_lbl)
        row.addLayout(info, stretch=1)

        if t == "clipboard_image" and data.get("content_path"):
            thumb = QLabel(); thumb.setFixedSize(36, 36)
            pix = QPixmap(data["content_path"])
            if not pix.isNull():
                thumb.setPixmap(
                    pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
            row.addWidget(thumb)

    def mousePressEvent(self, e):
        self.clicked.emit(self._data); super().mousePressEvent(e)


def _hex_to_rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    return ",".join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))


# ══════════════════════════════════════════════════════════════════════════
#  TAB 1 — 时间胶囊
# ══════════════════════════════════════════════════════════════════════════

class _TimelineScene(QGraphicsScene):
    node_clicked = pyqtSignal(dict)

    def __init__(self):
        super().__init__(); self._rows: list = []

    def load_day(self, rows: list):
        self._rows = rows; self._build()

    def _build(self):
        self.clear()
        W, H = 860, 90
        self.setSceneRect(0, 0, W, H)

        # 小时刻度
        for h in range(0, 25, 2):
            x = h / 24 * (W - 50) + 25
            self.addLine(x, 44, x, 52, QPen(QColor(_C["border"]), 1))
            lbl = QGraphicsTextItem(f"{h:02d}")
            lbl.setDefaultTextColor(QColor(_C["dim"]))
            lbl.setFont(QFont("JetBrains Mono,Consolas,monospace", 7))
            lbl.setPos(x - 8, 54)
            self.addItem(lbl)

        # 轴线
        self.addLine(25, 48, W - 25, 48, QPen(QColor(_C["border"]), 1))

        if not self._rows:
            t = QGraphicsTextItem("// no records today")
            t.setDefaultTextColor(QColor(_C["dim"]))
            t.setFont(QFont("JetBrains Mono,Consolas,monospace", 10))
            t.setPos(W // 2 - 80, 20); self.addItem(t)
            return

        by_min: dict[int, list] = {}
        for r in self._rows:
            key = (datetime.fromtimestamp(r["ts"]).hour * 60
                   + datetime.fromtimestamp(r["ts"]).minute)
            by_min.setdefault(key, []).append(r)

        for key, group in by_min.items():
            x = key / (24 * 60) * (W - 50) + 25
            for i, r in enumerate(group):
                y     = 38 - i * 12
                color = QColor(TYPE_COLOR.get(r["type"], _C["dim"]))
                dot   = QGraphicsEllipseItem(x - 4, y - 4, 8, 8)
                dot.setBrush(QBrush(color))
                dot.setPen(QPen(color.darker(130), 0.5))
                dot.setZValue(1)
                dot.setData(0, r)
                self.addItem(dot)

    def mousePressEvent(self, e):
        view = self.views()[0] if self.views() else None
        from PyQt6.QtGui import QTransform
        item = self.itemAt(e.scenePos(), view.transform() if view else QTransform())
        if isinstance(item, QGraphicsEllipseItem):
            r = item.data(0)
            if r:
                self.node_clicked.emit(r)
        super().mousePressEvent(e)


class _HourBlock(QFrame):
    event_clicked = pyqtSignal(dict)

    def __init__(self, hour: int, rows: list, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background:{_C['bg_card']}; border:1px solid {_C['border']};
                border-radius:4px;
            }}
        """)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        # 标题行（可折叠）
        hdr = QFrame()
        hdr.setStyleSheet(f"""
            QFrame {{
                background:#060d1c; border-bottom:1px solid {_C['border']};
                border-top-left-radius:4px; border-top-right-radius:4px;
            }}
        """)
        hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        hdr.setFixedHeight(28)
        hl = QHBoxLayout(hdr); hl.setContentsMargins(10, 0, 10, 0)
        t_lbl = QLabel(f"{hour:02d}:00 — {hour+1:02d}:00")
        t_lbl.setStyleSheet(f"color:{_C['cyan']}; font-size:10px; letter-spacing:2px;")
        hl.addWidget(t_lbl)
        c_lbl = QLabel(f"{len(rows)}")
        c_lbl.setStyleSheet(f"color:{_C['dim']}; font-size:10px;")
        hl.addWidget(c_lbl); hl.addStretch()
        lay.addWidget(hdr)

        self._body = QFrame()
        self._body.setStyleSheet("QFrame { background:transparent; border:none; }")
        bl = QVBoxLayout(self._body); bl.setContentsMargins(6, 4, 6, 6); bl.setSpacing(3)
        for r in rows:
            row_w = _EventRow(r, compact=True)
            row_w.clicked.connect(self.event_clicked)
            bl.addWidget(row_w)
        lay.addWidget(self._body)

        self._open = True
        hdr.mousePressEvent = lambda _e: self._toggle()

    def _toggle(self):
        self._open = not self._open
        self._body.setVisible(self._open)


class CapsuleTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{_C['bg']}; border:none;")
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── 左：日历 ──────────────────────────────────────────────────────
        left = QFrame()
        left.setFixedWidth(230)
        left.setStyleSheet(f"""
            QFrame {{
                background:{_C['bg_card']}; border:none;
                border-right:1px solid {_C['border']};
            }}
        """)
        ll = QVBoxLayout(left); ll.setContentsMargins(10, 12, 10, 10); ll.setSpacing(6)
        ll.addWidget(_sec_label("// CALENDAR"))

        self._cal = QCalendarWidget()
        self._cal.setGridVisible(False)
        self._cal.setNavigationBarVisible(True)
        self._cal.setMaximumDate(QDate.currentDate())
        self._cal.setStyleSheet(f"""
            QCalendarWidget QWidget       {{ background:{_C['bg_card']}; color:{_C['text']}; border:none; }}
            QCalendarWidget QAbstractItemView {{
                background:{_C['bg_mid']}; color:{_C['text']};
                selection-background-color:{_C['border']};
                selection-color:{_C['cyan']}; border:none;
                alternate-background-color:{_C['bg_card']};
            }}
            QCalendarWidget QToolButton   {{
                background:{_C['bg_mid']}; color:{_C['text']}; border:none;
                border-radius:3px; padding:3px 8px;
            }}
            QCalendarWidget QToolButton:hover {{ color:{_C['cyan']}; background:{_C['border']}; }}
            QCalendarWidget QSpinBox          {{ background:{_C['bg_mid']}; border:none; color:{_C['text']}; }}
            QCalendarWidget QMenu             {{ background:{_C['bg_card']}; color:{_C['text']}; }}
        """)
        self._cal.clicked.connect(self._on_day)
        ll.addWidget(self._cal)

        ll.addWidget(_sec_label("// LEGEND"))
        for lbl, color in [("窗口切换", _C["cyan"]),
                            ("剪贴板文字", _C["purple"]),
                            ("剪贴板图片", _C["orange"])]:
            row_w = QHBoxLayout(); row_w.setSpacing(6)
            dot = QLabel("●"); dot.setStyleSheet(f"color:{color}; font-size:12px;")
            row_w.addWidget(dot)
            t = QLabel(lbl); t.setStyleSheet(f"color:{_C['text']}; font-size:11px;")
            row_w.addWidget(t); row_w.addStretch()
            ll.addLayout(row_w)

        ll.addStretch()
        self._stat_lbl = QLabel("")
        self._stat_lbl.setWordWrap(True)
        self._stat_lbl.setStyleSheet(f"color:{_C['dim']}; font-size:10px;")
        ll.addWidget(self._stat_lbl)

        root.addWidget(left)

        # ── 中：时间轴 + 小时列表 ────────────────────────────────────────
        mid = QWidget(); mid.setStyleSheet(f"background:{_C['bg']}; border:none;")
        ml  = QVBoxLayout(mid); ml.setContentsMargins(12, 12, 6, 12); ml.setSpacing(8)

        self._date_lbl = QLabel("// SELECT DATE")
        self._date_lbl.setStyleSheet(
            f"color:{_C['cyan']}; font-size:13px; letter-spacing:2px; font-weight:bold;"
        )
        ml.addWidget(self._date_lbl)

        # 时间轴
        self._scene = _TimelineScene()
        self._scene.node_clicked.connect(self._on_event)
        self._view  = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setFixedHeight(90)
        self._view.setStyleSheet(f"""
            QGraphicsView {{
                background:{_C['bg_card']}; border:1px solid {_C['border']};
                border-radius:4px;
            }}
        """)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ml.addWidget(self._view)

        ml.addWidget(_sec_label("// BY HOUR"))

        self._hours_inner = QWidget(); self._hours_inner.setStyleSheet("background:transparent;")
        self._hours_lay   = QVBoxLayout(self._hours_inner)
        self._hours_lay.setContentsMargins(0, 0, 0, 0); self._hours_lay.setSpacing(4)
        self._hours_lay.addStretch()
        scroll = QScrollArea(); scroll.setWidget(self._hours_inner)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:transparent; border:none;")
        ml.addWidget(scroll, stretch=1)

        root.addWidget(mid, stretch=1)

        # ── 右：详情 ──────────────────────────────────────────────────────
        self._detail = _DetailPanel()
        self._detail.setFixedWidth(260)
        self._detail.setStyleSheet(self._detail.styleSheet()
                                   + "border-left:1px solid " + _C['border'] + ";")
        root.addWidget(self._detail)

        # 初始化
        self._refresh_cal()
        self._cal.setSelectedDate(QDate.currentDate())
        self._on_day(QDate.currentDate())

    def _refresh_cal(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setForeground(QColor(_C["cyan"]))
        for ds in db.active_dates():
            try:
                y, m, d = map(int, ds.split("-"))
                self._cal.setDateTextFormat(QDate(y, m, d), fmt)
            except Exception:
                pass

    def _on_day(self, qdate: QDate):
        d    = date(qdate.year(), qdate.month(), qdate.day())
        rows = db.query_day(d)

        weekdays = ["MON","TUE","WED","THU","FRI","SAT","SUN"]
        self._date_lbl.setText(
            f"// {d.strftime('%Y.%m.%d')}  {weekdays[d.weekday()]}"
        )

        stats = db.day_stats(d); total = sum(stats.values())
        if total:
            parts = [f"TOTAL {total}"] + [
                f"{TYPE_LABEL.get(k,k).upper()} {v}" for k, v in stats.items()
            ]
            self._stat_lbl.setText("  ·  ".join(parts))
        else:
            self._stat_lbl.setText("no records")

        self._scene.load_day(rows)
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.IgnoreAspectRatio)

        while self._hours_lay.count() > 1:
            item = self._hours_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        by_hour: dict[int, list] = {}
        for r in rows:
            h = datetime.fromtimestamp(r["ts"]).hour
            by_hour.setdefault(h, []).append(r)

        for h in sorted(by_hour.keys(), reverse=True):
            blk = _HourBlock(h, by_hour[h])
            blk.event_clicked.connect(self._on_event)
            self._hours_lay.insertWidget(0, blk)

        if not rows:
            empty = QLabel("// no records for this day")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color:{_C['dim']}; font-size:12px; padding:40px;")
            self._hours_lay.insertWidget(0, empty)

    def _on_event(self, data: dict):
        self._detail.show_event(data)

    def refresh(self):
        self._refresh_cal()
        self._on_day(self._cal.selectedDate())


# ══════════════════════════════════════════════════════════════════════════
#  TAB 2 — 剪贴板数据库
# ══════════════════════════════════════════════════════════════════════════

class ClipboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{_C['bg']}; border:none;")
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── 左：筛选侧栏 ──────────────────────────────────────────────────
        left = QFrame()
        left.setFixedWidth(160)
        left.setStyleSheet(f"""
            QFrame {{
                background:{_C['bg_card']}; border:none;
                border-right:1px solid {_C['border']};
            }}
        """)
        ll = QVBoxLayout(left); ll.setContentsMargins(10, 12, 10, 10); ll.setSpacing(4)
        ll.addWidget(_sec_label("// FILTER"))

        self._filter_btns: dict[str, QPushButton] = {}
        for key, lbl in [
            ("all",             "ALL"),
            ("clipboard_text",  "TEXT"),
            ("clipboard_image", "IMAGE"),
            ("window",          "WINDOW"),
        ]:
            btn = _dark_btn(lbl)
            btn.setCheckable(True)
            btn.setStyleSheet(btn.styleSheet())
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            ll.addWidget(btn)
            self._filter_btns[key] = btn
        self._filter_btns["all"].setChecked(True)
        self._set_filter_style("all")
        self._cur = "all"

        ll.addStretch()
        self._stat_lbl = QLabel("")
        self._stat_lbl.setWordWrap(True)
        self._stat_lbl.setStyleSheet(f"color:{_C['dim']}; font-size:10px;")
        ll.addWidget(self._stat_lbl)

        root.addWidget(left)

        # ── 中：搜索 + 列表 ───────────────────────────────────────────────
        mid = QWidget(); mid.setStyleSheet(f"background:{_C['bg']}; border:none;")
        ml  = QVBoxLayout(mid); ml.setContentsMargins(12, 12, 6, 12); ml.setSpacing(8)

        self._search = _search_input("SEARCH  //  内容 / 应用 / 标题")
        self._search.textChanged.connect(self._refresh)
        ml.addWidget(self._search)

        self._list_inner = QWidget(); self._list_inner.setStyleSheet("background:transparent;")
        self._list_lay   = QVBoxLayout(self._list_inner)
        self._list_lay.setContentsMargins(0, 0, 0, 0); self._list_lay.setSpacing(4)
        self._list_lay.addStretch()

        scroll = QScrollArea(); scroll.setWidget(self._list_inner)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent; border:none;")
        ml.addWidget(scroll, stretch=1)
        root.addWidget(mid, stretch=1)

        # ── 右：详情 ──────────────────────────────────────────────────────
        self._detail = _DetailPanel()
        self._detail.setFixedWidth(260)
        self._detail.setStyleSheet(self._detail.styleSheet()
                                   + "border-left:1px solid " + _C['border'] + ";")
        root.addWidget(self._detail)

        self._refresh()

    def _set_filter_style(self, active_key: str):
        for k, btn in self._filter_btns.items():
            if k == active_key:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background:#0f1e35; color:{_C['cyan']};
                        border:1px solid {_C['cyan']}; border-radius:4px;
                        padding:4px 14px; font-size:11px; letter-spacing:0.5px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background:{_C['bg_card']}; color:{_C['dim']};
                        border:1px solid {_C['border']}; border-radius:4px;
                        padding:4px 14px; font-size:11px; letter-spacing:0.5px;
                    }}
                    QPushButton:hover {{ background:#0f1e35; color:{_C['text']}; border-color:{_C['dim']}; }}
                """)

    def _set_filter(self, key: str):
        self._cur = key
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == key)
        self._set_filter_style(key)
        self._refresh()

    def _refresh(self):
        rows = db.query(
            search=self._search.text().strip(),
            type_filter=self._cur, limit=200,
        )
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for r in rows:
            w = _EventRow(r)
            w.clicked.connect(self._detail.show_event)
            self._list_lay.insertWidget(self._list_lay.count() - 1, w)
        counts = db.type_counts(); total = sum(counts.values())
        lines  = [f"TOTAL: {total}"] + [
            f"  {TYPE_LABEL.get(k,k).upper()}: {v}" for k, v in counts.items()
        ]
        self._stat_lbl.setText("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════
#  主窗口
# ══════════════════════════════════════════════════════════════════════════

class LifeLogWindow(QWidget):
    """入口窗口，与 HealthStatsWindow 同等地位"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LIFELOG  //  时间胶囊 · 剪贴板")
        self.resize(1060, 660)
        self.setMinimumSize(900, 560)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setStyleSheet(f"background:{_C['bg']}; color:{_C['text']};")

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── 标题栏（与浮窗风格一致）─────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(f"""
            QFrame {{
                background:#060d1c;
                border-bottom:1px solid {_C['border']};
            }}
        """)
        hl = QHBoxLayout(header); hl.setContentsMargins(12, 0, 12, 0); hl.setSpacing(8)

        for color in ['#ff5f57','#febc2e','#28c840']:
            dot = QFrame(); dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"QFrame {{ background:{color}; border-radius:5px; }}")
            hl.addWidget(dot)
        hl.addSpacing(10)

        lbl = QLabel("LIFELOG  //  时间胶囊 · 剪贴板")
        lbl.setStyleSheet(f"color:{_C['dim']}; font-size:10px; letter-spacing:2px;")
        hl.addWidget(lbl); hl.addStretch()

        self._rec_lbl = QLabel("● REC")
        self._rec_lbl.setStyleSheet(f"color:{_C['green']}; font-size:10px; letter-spacing:1px;")
        hl.addWidget(self._rec_lbl)

        root.addWidget(header)

        # ── Tab 切换 ─────────────────────────────────────────────────────
        tab_bar = QFrame()
        tab_bar.setFixedHeight(34)
        tab_bar.setStyleSheet(f"""
            QFrame {{
                background:{_C['bg_card']};
                border-bottom:1px solid {_C['border']};
            }}
        """)
        tl = QHBoxLayout(tab_bar); tl.setContentsMargins(12, 0, 12, 0); tl.setSpacing(0)

        self._tab_btns: list[QPushButton] = []
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background:{_C['bg']}; border:none;")

        self._capsule_tab   = CapsuleTab()
        self._clipboard_tab = ClipboardTab()
        self._stack.addWidget(self._capsule_tab)
        self._stack.addWidget(self._clipboard_tab)

        for i, (icon, lbl) in enumerate([("⏳", "TIME CAPSULE"), ("⎘", "CLIPBOARD")]):
            btn = QPushButton(f"{icon}  {lbl}")
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            tl.addWidget(btn)
            self._tab_btns.append(btn)
        tl.addStretch()

        root.addWidget(tab_bar)
        root.addWidget(self._stack, stretch=1)

        self._switch_tab(0)

        # 自动刷新
        self._timer = QTimer()
        self._timer.timeout.connect(self._auto_refresh)
        self._timer.start(5000)

    def _switch_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_btns):
            btn.setChecked(i == idx)
            if i == idx:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background:transparent; color:{_C['cyan']};
                        border:none; border-bottom:2px solid {_C['cyan']};
                        padding:0 16px; font-size:11px; letter-spacing:1px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background:transparent; color:{_C['dim']};
                        border:none; border-bottom:2px solid transparent;
                        padding:0 16px; font-size:11px; letter-spacing:1px;
                    }}
                    QPushButton:hover {{ color:{_C['text']}; }}
                """)

    def set_recording(self, on: bool):
        self._rec_lbl.setText("● REC" if on else "○ PAUSED")
        self._rec_lbl.setStyleSheet(
            f"color:{_C['green'] if on else _C['dim']}; font-size:10px; letter-spacing:1px;"
        )

    def _auto_refresh(self):
        if self._stack.currentIndex() == 0:
            self._capsule_tab.refresh()
        else:
            self._clipboard_tab._refresh()
