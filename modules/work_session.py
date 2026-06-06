"""
工作会话状态机
状态：BEFORE_WORK → WORKING → LUNCH_BREAK → WORKING → OVERTIME / OFF_WORK
支持：周末直接进入加班模式
持久化到 config/session.json（跨重启恢复当日状态）
"""
import json
import os
from datetime import datetime, date
from enum import Enum
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

SESSION_FILE = Path(__file__).parent.parent / "config" / "session.json"


class WorkState(Enum):
    BEFORE_WORK  = "before_work"   # 未上班（或今日还未打卡）
    WORKING      = "working"       # 工作中
    LUNCH_BREAK  = "lunch_break"   # 午休中（= 中午的下班）
    OVERTIME     = "overtime"      # 加班中
    OFF_WORK     = "off_work"      # 下班（正常）


class WorkSession(QObject):
    """单例，全程管理今日工作状态，改变时发信号。"""

    state_changed = pyqtSignal(str)   # 发送新状态名称

    _instance = None

    @classmethod
    def instance(cls) -> "WorkSession":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._state   = WorkState.BEFORE_WORK
        self._start   = None    # 当日上班打卡时间（datetime）
        self._lunch_start = None
        self._lunch_end   = None
        self._end     = None    # 下班/加班结束打卡时间
        self._date    = None    # 打卡日期（防跨天）
        self._load()

    # ── 属性 ──────────────────────────────────────────────────────────────────

    @property
    def state(self) -> WorkState:
        return self._state

    @property
    def is_working(self) -> bool:
        return self._state in (WorkState.WORKING, WorkState.OVERTIME)

    @property
    def work_start(self) -> datetime | None:
        return self._start

    @property
    def lunch_start(self) -> datetime | None:
        return self._lunch_start

    @property
    def lunch_end(self) -> datetime | None:
        return self._lunch_end

    @property
    def work_end(self) -> datetime | None:
        return self._end

    def is_weekend(self) -> bool:
        return datetime.today().weekday() >= 5

    def today_punched(self) -> bool:
        """今天是否已经打过上班卡"""
        return self._date == date.today() and self._start is not None

    # ── 动作 ──────────────────────────────────────────────────────────────────

    def punch_in(self):
        """上班打卡（普通工作日 / 加班日首次打卡）"""
        now = datetime.now()
        self._date  = now.date()
        self._start = now
        self._lunch_start = None
        self._lunch_end   = None
        self._end   = None
        new_state = WorkState.OVERTIME if self.is_weekend() else WorkState.WORKING
        self._set_state(new_state)

    def punch_lunch_start(self):
        """开始午休（= 午间下班）"""
        self._lunch_start = datetime.now()
        self._set_state(WorkState.LUNCH_BREAK)

    def punch_lunch_end(self):
        """午休结束（= 下午上班）"""
        self._lunch_end = datetime.now()
        self._set_state(WorkState.WORKING)

    def punch_overtime(self):
        """下班后继续加班（不重置开始时间）"""
        self._set_state(WorkState.OVERTIME)

    def punch_out(self):
        """正式下班"""
        self._end = datetime.now()
        self._set_state(WorkState.OFF_WORK)

    def reset_for_new_day(self):
        """强制重置（跨天时调用）"""
        self._state   = WorkState.BEFORE_WORK
        self._start   = None
        self._lunch_start = None
        self._lunch_end   = None
        self._end     = None
        self._date    = None
        self._save()
        self.state_changed.emit(self._state.value)

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def _set_state(self, new_state: WorkState):
        self._state = new_state
        self._save()
        self.state_changed.emit(new_state.value)

    def _save(self):
        def _fmt(dt): return dt.isoformat() if dt else None
        data = {
            "state":       self._state.value,
            "date":        self._date.isoformat() if self._date else None,
            "start":       _fmt(self._start),
            "lunch_start": _fmt(self._lunch_start),
            "lunch_end":   _fmt(self._lunch_end),
            "end":         _fmt(self._end),
        }
        try:
            SESSION_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
        except Exception:
            pass

    def _load(self):
        try:
            data = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
            saved_date = date.fromisoformat(data["date"]) if data.get("date") else None
            if saved_date != date.today():
                return  # 跨天，不恢复
            self._date  = saved_date
            self._state = WorkState(data.get("state", "before_work"))
            def _parse(v): return datetime.fromisoformat(v) if v else None
            self._start       = _parse(data.get("start"))
            self._lunch_start = _parse(data.get("lunch_start"))
            self._lunch_end   = _parse(data.get("lunch_end"))
            self._end         = _parse(data.get("end"))
        except Exception:
            pass
