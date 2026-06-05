import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.json')


def load() -> dict:
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
