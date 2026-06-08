"""
LifeLog 数据库层 (SQLite / WAL)
存储：窗口切换快照 / 剪贴板文字 / 剪贴板图片
"""
import sqlite3, threading, time
from pathlib import Path
from datetime import datetime, date
from contextlib import contextmanager

_BASE     = Path(__file__).parent.parent
DATA_DIR  = Path.home() / ".local" / "share" / "lifelog"
DB_PATH   = DATA_DIR / "lifelog.db"
SHOTS_DIR = DATA_DIR / "screenshots"
CLIPS_DIR = DATA_DIR / "clipboard_images"

for _d in (DATA_DIR, SHOTS_DIR, CLIPS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_conn_obj: sqlite3.Connection | None = None


@contextmanager
def _conn():
    global _conn_obj
    if _conn_obj is None:
        _conn_obj = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn_obj.execute("PRAGMA journal_mode=WAL")
        _conn_obj.execute("""
            CREATE TABLE IF NOT EXISTS ll_events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            REAL    NOT NULL,
                type          TEXT    NOT NULL,
                app_name      TEXT    DEFAULT '',
                window_title  TEXT    DEFAULT '',
                content_text  TEXT    DEFAULT '',
                content_path  TEXT    DEFAULT ''
            )
        """)
        _conn_obj.execute("CREATE INDEX IF NOT EXISTS ll_idx_ts   ON ll_events(ts)")
        _conn_obj.execute("CREATE INDEX IF NOT EXISTS ll_idx_type ON ll_events(type)")
        _conn_obj.commit()
    yield _conn_obj


def insert(type_: str, app_name='', window_title='',
           content_text='', content_path=''):
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO ll_events(ts,type,app_name,window_title,"
            "content_text,content_path) VALUES(?,?,?,?,?,?)",
            (time.time(), type_, app_name, window_title,
             content_text, content_path),
        )
        c.commit()


def query(search='', type_filter='all', limit=200, offset=0) -> list[dict]:
    parts, params = ["SELECT * FROM ll_events"], []
    conds: list[str] = []
    if type_filter != 'all':
        conds.append("type=?"); params.append(type_filter)
    if search:
        conds.append("(content_text LIKE ? OR window_title LIKE ? OR app_name LIKE ?)")
        like = f"%{search}%"; params += [like, like, like]
    if conds:
        parts.append("WHERE " + " AND ".join(conds))
    parts.append("ORDER BY ts DESC LIMIT ? OFFSET ?"); params += [limit, offset]
    with _lock, _conn() as c:
        rows = c.execute(" ".join(parts), params).fetchall()
    cols = ['id','ts','type','app_name','window_title','content_text','content_path']
    return [dict(zip(cols, r)) for r in rows]


def query_day(day: date) -> list[dict]:
    lo = datetime(day.year, day.month, day.day).timestamp()
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT * FROM ll_events WHERE ts>=? AND ts<? ORDER BY ts ASC",
            (lo, lo + 86400),
        ).fetchall()
    cols = ['id','ts','type','app_name','window_title','content_text','content_path']
    return [dict(zip(cols, r)) for r in rows]


def active_dates() -> set[str]:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT date(ts,'unixepoch','localtime') FROM ll_events"
        ).fetchall()
    return {r[0] for r in rows}


def day_stats(day: date) -> dict:
    lo = datetime(day.year, day.month, day.day).timestamp()
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT type, COUNT(*) FROM ll_events WHERE ts>=? AND ts<? GROUP BY type",
            (lo, lo + 86400),
        ).fetchall()
    return dict(rows)


def type_counts() -> dict:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT type, COUNT(*) FROM ll_events GROUP BY type"
        ).fetchall()
    return dict(rows)
