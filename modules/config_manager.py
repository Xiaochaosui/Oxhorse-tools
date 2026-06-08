import json
import os

CONFIG_DIR  = os.path.join(os.path.dirname(__file__), '..', 'config')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'settings.json')

_DEFAULTS = {
    'settings.json': {
        "work": {
            "start_time": "09:30",
            "end_time": "18:30",
            "monthly_salary": 0.0,
            "salary_day": 15
        },
        "reminders": {
            "water_interval_minutes": 45,
            "lunch_time": "12:00",
            "dinner_time": "18:30",
            "move_interval_minutes": 60
        },
        "feishu": {
            "app_id": "",
            "app_secret": "",
            "bitable_app_token": "",
            "bitable_table_id": ""
        },
        "stock": {
            "watchlist": [],
            "watchlist_names": [],
            "refresh_interval_seconds": 10,
            "alert_threshold_pct": 3.0
        },
        "ui": {
            "opacity": 0.95,
            "always_on_top": True,
            "theme": "dark_tech"
        }
    },
    'session.json': {
        "state": None,
        "date": None,
        "start": None,
        "lunch_start": None,
        "lunch_end": None,
        "end": None
    },
    'window_positions.json': {},
}


def ensure_defaults():
    """首次运行时为缺失的 config/*.json 创建默认文件，已存在则不覆盖。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    for filename, default in _DEFAULTS.items():
        path = os.path.join(CONFIG_DIR, filename)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(default, f, ensure_ascii=False, indent=2)


def load() -> dict:
    ensure_defaults()
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save(data: dict):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get(key_path: str, default=None):
    """dot-separated key path, e.g. 'work.start_time'"""
    cfg = load()
    keys = key_path.split('.')
    for k in keys:
        if isinstance(cfg, dict) and k in cfg:
            cfg = cfg[k]
        else:
            return default
    return cfg


def set(key_path: str, value):
    cfg = load()
    keys = key_path.split('.')
    d = cfg
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value
    save(cfg)
