"""
健康行为记录数据库 (SQLite)
记录：喝水 / 站立 / 吃饭 的每次触发与响应
"""
import sqlite3
import os
from datetime import datetime, date, timedelta
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'health.db')

# 事件类型
TYPE_WATER = 'water'
TYPE_MOVE  = 'move'
TYPE_MEAL  = 'meal'

# 动作
ACT_TRIGGERED  = 'triggered'   # 提醒弹出
ACT_COMPLETED  = 'completed'   # 用户点了确认（喝了 / 动了）
ACT_SNOOZED    = 'snoozed'     # 点了"再等等"
ACT_AUTO_CLOSE = 'auto_close'  # 倒计时自动关闭


def _init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            type      TEXT    NOT NULL,
            action    TEXT    NOT NULL,
            ts        TEXT    NOT NULL,
            date      TEXT    NOT NULL,
            hour      INTEGER NOT NULL,
            note      TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON events(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON events(type)")
    conn.commit()


@contextmanager
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    _init_db(c)
    try:
        yield c
    finally:
        c.close()


# ── 写入 ─────────────────────────────────────────────────────────────────────

def log(event_type: str, action: str, note: str = ''):
    """记录一条事件"""
    now = datetime.now()
    with _conn() as c:
        c.execute(
            "INSERT INTO events(type,action,ts,date,hour,note) VALUES(?,?,?,?,?,?)",
            (event_type, action, now.isoformat(), now.strftime('%Y-%m-%d'), now.hour, note)
        )
        c.commit()


# ── 查询 ─────────────────────────────────────────────────────────────────────

def query_day(day: str = None) -> list[dict]:
    """查询某天所有记录，默认今天"""
    d = day or date.today().isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM events WHERE date=? ORDER BY ts", (d,)
        ).fetchall()
    return [dict(r) for r in rows]


def query_range(start: str, end: str) -> list[dict]:
    """查询 [start, end] 日期范围，格式 YYYY-MM-DD"""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM events WHERE date>=? AND date<=? ORDER BY ts",
            (start, end)
        ).fetchall()
    return [dict(r) for r in rows]


def query_all() -> list[dict]:
    """查询全部记录（按时间排序）"""
    with _conn() as c:
        rows = c.execute("SELECT * FROM events ORDER BY ts").fetchall()
    return [dict(r) for r in rows]


def _sanitize_events(rows: list[dict]) -> list[dict]:
    """
    过滤历史 bug 造成的伪 completed：
    当同类型 auto_close 发生后 0~3 秒内出现 completed，判定为非真实打卡。
    """
    auto_close_times: dict[str, list[datetime]] = {}
    out: list[dict] = []
    for r in sorted(rows, key=lambda x: x.get('ts', '')):
        t = r.get('type')
        action = r.get('action')
        ts = r.get('ts', '')
        try:
            dt = datetime.fromisoformat(ts)
        except Exception:
            out.append(r)
            continue

        if action == ACT_AUTO_CLOSE:
            auto_close_times.setdefault(t, []).append(dt)
            out.append(r)
            continue

        if action == ACT_COMPLETED:
            closes = auto_close_times.get(t, [])
            is_false_completed = any(
                0 <= (dt - ac).total_seconds() <= 3
                for ac in closes[-6:]
            )
            if is_false_completed:
                continue

        out.append(r)
    return out


def daily_summary(day: str = None) -> dict:
    """今日各类型统计"""
    d = day or date.today().isoformat()
    rows = _sanitize_events(query_day(d))
    result = {t: {a: 0 for a in [ACT_TRIGGERED, ACT_COMPLETED, ACT_SNOOZED, ACT_AUTO_CLOSE]}
              for t in [TYPE_WATER, TYPE_MOVE, TYPE_MEAL]}
    for r in rows:
        t, a = r['type'], r['action']
        if t in result and a in result[t]:
            result[t][a] += 1
    # 计算响应率
    for t in result:
        trig = result[t][ACT_TRIGGERED]
        comp = result[t][ACT_COMPLETED]
        result[t]['response_rate'] = round(comp / trig * 100, 1) if trig > 0 else 0
    return result


def weekly_counts(event_type: str, action: str = ACT_COMPLETED) -> list[dict]:
    """最近7天每天的完成次数"""
    today = date.today()
    out = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        rows = _sanitize_events(query_day(d))
        cnt = sum(1 for r in rows if r['type'] == event_type and r['action'] == action)
        out.append({'date': d, 'count': cnt, 'label': (today - timedelta(days=i)).strftime('%m/%d')})
    return out


def hourly_distribution(event_type: str, days: int = 30) -> list[int]:
    """过去 N 天各小时的触发/完成分布（0-23 时）"""
    start = (date.today() - timedelta(days=days)).isoformat()
    end   = date.today().isoformat()
    rows = _sanitize_events(query_range(start, end))
    dist = [0] * 24
    for r in rows:
        if r['type'] == event_type and r['action'] == ACT_COMPLETED:
            hr = int(r['hour'])
            if 0 <= hr <= 23:
                dist[hr] += 1
    return dist


def streak(event_type: str, min_per_day: int = 1) -> int:
    """连续达标天数（每天完成次数 >= min_per_day）"""
    today = date.today()
    days = 0
    for i in range(365):
        d = (today - timedelta(days=i)).isoformat()
        rows = _sanitize_events(query_day(d))
        cnt = sum(
            1 for r in rows
            if r['type'] == event_type and r['action'] == ACT_COMPLETED
        )
        if cnt >= min_per_day:
            days += 1
        else:
            break
    return days


def all_time_totals() -> dict:
    """全量统计"""
    rows = _sanitize_events(query_all())
    result = {}
    for r in rows:
        t, a = r['type'], r['action']
        result.setdefault(t, {}).setdefault(a, 0)
        result[t][a] += 1
    return result
