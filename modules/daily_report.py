"""
每日收盘报告 — 腾讯财经HTTP日K + Claude分析 + HTML输出
触发时机：每个交易日 15:05 后自动生成，也可手动触发
"""
import re
import threading
import requests
from datetime import datetime, date, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

from modules.theme import NEON_COLORS as NC
import modules.config_manager as cfg

# 腾讯财经日K（HTTP，可穿透代理）
TENCENT_KLINE_URL = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ── 数据获取 ────────────────────────────────────────────────────────────────

def _to_tencent_code(code: str) -> str:
    """sh000001 → sh000001 (腾讯格式和新浪一样直接用)"""
    return code.lower()


def _fetch_klines(code: str, days: int = 20) -> list[dict]:
    """从腾讯财经获取日K线，带重试"""
    import json as _json
    tc = _to_tencent_code(code)
    end = date.today().strftime('%Y-%m-%d')
    start = (date.today() - timedelta(days=days * 2)).strftime('%Y-%m-%d')
    params = {
        '_var': f'kline_dayqfq_{tc}',
        'param': f'{tc},day,{start},{end},{days},qfq',
        'r': '0.1',
    }
    headers = {
        'Referer': 'http://gu.qq.com',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    }
    for _attempt in range(3):
        try:
            r = requests.get(TENCENT_KLINE_URL, params=params, headers=headers, timeout=12)
            r.encoding = 'utf-8'
            text = r.text
            json_str = text[text.index('=') + 1:] if '=' in text else text
            d = _json.loads(json_str)
            if d.get('code') != 0:
                continue
            data_node = d.get('data', {}).get(tc, {})
            raw_list = data_node.get('qfqday') or data_node.get('day') or []
            if not raw_list:
                continue
            name = _get_name(code)
            result = []
            for item in raw_list[-days:]:
                try:
                    open_p  = float(item[1])
                    close_p = float(item[2])
                    high_p  = float(item[3])
                    low_p   = float(item[4])
                    vol     = float(item[5])
                    prev_close = result[-1]['close'] if result else open_p
                    chg_pct = (close_p - prev_close) / prev_close * 100 if prev_close else 0
                    result.append({
                        'date':    item[0],
                        'open':    open_p,
                        'close':   close_p,
                        'high':    high_p,
                        'low':     low_p,
                        'volume':  vol,
                        'chg_pct': chg_pct,
                        'name':    name,
                    })
                except (ValueError, IndexError):
                    continue
            if result:
                return _supplement_today(code, result)
        except Exception:
            continue
    return []


def _supplement_today(code: str, klines: list[dict]) -> list[dict]:
    """若K线最新日期不是今天（收盘后API延迟），用新浪实时数据补齐当日条目"""
    today_str = date.today().strftime('%Y-%m-%d')
    if klines[-1]['date'] == today_str:
        return klines
    now = datetime.now()
    # 周末或开盘前不补充
    if now.weekday() >= 5 or now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return klines
    try:
        url = f"http://hq.sinajs.cn/list={code}"
        r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        r.encoding = 'gbk'
        m = re.search(r'"([^"]*)"', r.text)
        if not m:
            return klines
        parts = m.group(1).split(',')
        if len(parts) < 9:
            return klines
        price  = float(parts[3]) if parts[3] else 0
        open_p = float(parts[1]) if parts[1] else price
        high_p = float(parts[4]) if parts[4] else price
        low_p  = float(parts[5]) if parts[5] else price
        vol    = float(parts[8]) * 100 if parts[8] else 0  # 手 → 股
        if price <= 0:
            return klines
        prev_close = klines[-1]['close']
        chg_pct = (price - prev_close) / prev_close * 100 if prev_close else 0
        klines.append({
            'date':    today_str,
            'open':    open_p,
            'close':   price,
            'high':    high_p,
            'low':     low_p,
            'volume':  vol,
            'chg_pct': chg_pct,
            'name':    klines[-1]['name'],
        })
    except Exception:
        pass
    return klines


def _get_name(code: str) -> str:
    """通过新浪实时接口获取股票名称"""
    try:
        url = f"http://hq.sinajs.cn/list={code}"
        r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        r.encoding = 'gbk'
        m = re.search(r'"([^,]+)', r.text)
        return m.group(1).strip() if m else code
    except Exception:
        return code


def _fetch_all_stocks() -> dict[str, list[dict]]:
    """并发获取所有自选股 K 线"""
    codes = cfg.get('stock.watchlist', [])
    results = {}
    threads = []

    def _worker(c):
        results[c] = _fetch_klines(c, days=20)

    for code in codes:
        t = threading.Thread(target=_worker, args=(code,), daemon=True)
        threads.append(t); t.start()
    for t in threads:
        t.join(timeout=20)
    return results


# ── Claude 分析 ─────────────────────────────────────────────────────────────

def _build_prompt(stocks_data: dict[str, list[dict]]) -> str:
    today = date.today().strftime('%Y-%m-%d')
    lines = [
        f"今天是 {today}，以下是我关注的A股/ETF标的近20个交易日的日K数据，请给出专业收盘分析报告。",
        "",
        "## 各标的数据（格式：日期 | 开盘 | 收盘 | 最高 | 最低 | 成交量亿 | 涨跌幅%）",
    ]
    for code, klines in stocks_data.items():
        if not klines:
            lines.append(f"\n### {code} — 数据获取失败，请忽略")
            continue
        name = klines[-1].get('name', code)
        lines.append(f"\n### {name}（{code}）")
        for k in klines:
            lines.append(
                f"{k['date']} | {k['open']:.3f} | {k['close']:.3f} | "
                f"{k['high']:.3f} | {k['low']:.3f} | "
                f"{k['volume']/1e8:.2f}亿 | {k['chg_pct']:+.2f}%"
            )

    lines += [
        "",
        "## 分析要求",
        "请用中文，对每个有数据的标的分别分析（跳过数据失败的）：",
        "1. **今日表现**：涨跌幅评价、量价配合情况、有无异常信号",
        "2. **近期趋势**：5/10/20日均线方向，当前关键支撑位和压力位",
        "3. **操作建议**：持有/关注/谨慎，给出简洁理由",
        "",
        "最后输出：",
        "- **整体市场研判**（2-3句，概括今日大盘与板块情绪）",
        "- **明日重点关注**（3-5条 bullet，具体说明关注点）",
        "",
        "输出用 Markdown 格式，语气专业直接，不要过分保守，给出明确判断。",
    ]
    return '\n'.join(lines)


def _call_claude(prompt: str, on_progress=None) -> str:
    """使用 streaming 调用 Claude API，避免长请求被网关 524 超时"""
    import os
    api_key = os.environ.get('ANTHROPIC_AUTH_TOKEN') or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return "⚠️ 未找到 Claude API Key，请设置环境变量 ANTHROPIC_AUTH_TOKEN 或 ANTHROPIC_API_KEY"
    base_url = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com').rstrip('/')
    if on_progress:
        on_progress("正在调用 Claude 分析（流式输出，约30-60秒）...")
    try:
        import json as _json
        url = f"{base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 4096,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        }
        r = requests.post(url, headers=headers, json=body, timeout=120, stream=True)
        r.raise_for_status()
        text = ""
        for line in r.iter_lines():
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                d = _json.loads(line[6:])
                if d.get("type") == "content_block_delta":
                    text += d["delta"].get("text", "")
            except Exception:
                continue
        return text if text else "⚠️ Claude 返回内容为空"
    except Exception as e:
        return f"⚠️ Claude API 调用失败：{e}"


# ── HTML 报告渲染 ─────────────────────────────────────────────────────────────

def _md_to_html(md: str) -> str:
    import html as h
    lines = md.split('\n')
    out = []
    in_code = False
    for line in lines:
        if line.startswith('```'):
            in_code = not in_code
            out.append('<pre>' if in_code else '</pre>')
            continue
        if in_code:
            out.append(h.escape(line)); continue
        line = h.escape(line)
        if line.startswith('### '):
            out.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('## '):
            out.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('# '):
            out.append(f'<h1>{line[2:]}</h1>')
        else:
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'`(.+?)`', r'<code>\1</code>', line)
            if re.match(r'^- |^\d+\. ', line):
                out.append(f'<li>{re.sub(r"^- |^\d+\. ", "", line)}</li>')
            elif line.strip() == '':
                out.append('<p style="margin:4px 0"></p>')
            else:
                out.append(f'<p>{line}</p>')
    return '\n'.join(out)


def _build_html(analysis: str, stocks_data: dict, generated_at: str) -> str:
    chips = []
    for code, klines in stocks_data.items():
        if not klines:
            continue
        k = klines[-1]
        name = k.get('name', code)
        chg = k['chg_pct']
        color = '#ff4c4c' if chg > 0 else ('#00e676' if chg < 0 else '#aaa')
        sign = '+' if chg > 0 else ''
        chips.append(
            f'<div class="chip">'
            f'<span class="cn">{name}</span>'
            f'<span class="cp">{k["close"]:.3f}</span>'
            f'<span class="cc" style="color:{color}">{sign}{chg:.2f}%</span>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>收盘报告 {generated_at[:10]}</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#050d18; color:#c8d8e8; font-family:'PingFang SC','Microsoft YaHei',sans-serif;
        font-size:14px; line-height:1.75; padding:28px 32px; max-width:900px; margin:0 auto; }}
.hd {{ border-bottom:1px solid #1a3a5c; padding-bottom:16px; margin-bottom:20px; }}
.hd h1 {{ font-size:22px; color:#4fc3f7; letter-spacing:2px; }}
.hd .meta {{ font-size:11px; color:#3a5a7a; margin-top:5px; font-family:monospace; }}
.chips {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:24px; }}
.chip {{ background:#07111f; border:1px solid #1a3a5c; border-radius:8px;
         padding:8px 14px; display:flex; flex-direction:column; align-items:center; min-width:88px; }}
.cn {{ font-size:10px; color:#5a8aaa; margin-bottom:2px; }}
.cp {{ font-size:15px; color:#e8f4ff; font-weight:bold; font-family:monospace; }}
.cc {{ font-size:12px; font-weight:bold; font-family:monospace; }}
.body {{ background:#07111f; border:1px solid #1a3a5c; border-radius:10px; padding:24px 28px; }}
h1 {{ font-size:19px; color:#4fc3f7; margin:20px 0 8px; }}
h2 {{ font-size:16px; color:#4fc3f7; margin:20px 0 8px;
      border-left:3px solid #4fc3f7; padding-left:10px; }}
h3 {{ font-size:14px; color:#90caf9; margin:14px 0 6px; }}
p {{ margin:5px 0; color:#b8cce0; }}
li {{ margin:4px 0 4px 22px; color:#b8cce0; }}
strong {{ color:#ffd740; }}
code {{ background:#0a1a2a; border:1px solid #1a3a5c; border-radius:3px;
        padding:1px 5px; font-family:monospace; font-size:12px; color:#00e676; }}
pre {{ background:#0a1a2a; border:1px solid #1a3a5c; border-radius:6px;
       padding:12px; font-family:monospace; font-size:12px; overflow-x:auto; color:#aed6f1; }}
.ft {{ margin-top:24px; font-size:11px; color:#2a4a6a; text-align:center; font-family:monospace; }}
</style>
</head>
<body>
<div class="hd">
  <h1>📊 每日收盘分析报告</h1>
  <div class="meta">❯ generated at {generated_at} &nbsp;// powered by Claude Sonnet</div>
</div>
<div class="chips">{''.join(chips)}</div>
<div class="body">{_md_to_html(analysis)}</div>
<div class="ft">── Oxhorse Tools · Daily Market Report ──</div>
</body>
</html>"""


def generate_report(on_progress=None, on_done=None):
    """后台线程生成报告；on_progress(msg:str)，on_done(path:str, err:str|None)"""
    def _run():
        try:
            if on_progress: on_progress("正在获取行情数据...")
            stocks_data = _fetch_all_stocks()

            success = sum(1 for v in stocks_data.values() if v)
            if on_progress: on_progress(f"获取完成（{success}/{len(stocks_data)} 只成功），正在分析...")

            prompt   = _build_prompt(stocks_data)
            analysis = _call_claude(prompt, on_progress)

            if on_progress: on_progress("正在生成 HTML...")
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            html    = _build_html(analysis, stocks_data, now_str)
            fname   = REPORTS_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
            fname.write_text(html, encoding='utf-8')

            if on_done: on_done(str(fname))
        except Exception as e:
            if on_done: on_done(None, str(e))

    threading.Thread(target=_run, daemon=True).start()


# ── 自动触发器 ───────────────────────────────────────────────────────────────

class ReportTrigger(QObject):
    trigger = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._today_done = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(30_000)

    def _check(self):
        if not cfg.get('stock.report_enabled', True):
            return
        now = datetime.now()
        if now.weekday() >= 5:
            return
        t = now.hour * 60 + now.minute
        if t >= 16 * 60 + 30 and self._today_done != date.today():
            self._today_done = date.today()
            self.trigger.emit()


# ── 报告面板（嵌在 StockWidget 底部）────────────────────────────────────────

class _Worker(QObject):
    """跨线程信号桥，把后台回调安全传回主线程"""
    progress = pyqtSignal(str)
    done     = pyqtSignal(str, str)   # path, err (空串=成功)


class ReportPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_path: str | None = None
        self._worker = _Worker()
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._build_ui()
        self._trigger = ReportTrigger(self)
        self._trigger.trigger.connect(self._on_auto_trigger)
        self._check_existing()

    def _build_ui(self):
        self.setStyleSheet(f"QFrame{{border:1px solid {NC['border']};border-radius:6px;background:#050d18;}}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8); lay.setSpacing(8)

        self.lbl = QLabel("📋 收盘报告  //  每日 15:05 自动生成")
        self.lbl.setStyleSheet(f"color:{NC['dim']};font-size:11px;border:none;")

        # 开关按钮
        self._enabled = cfg.get('stock.report_enabled', True)
        self.btn_toggle = QPushButton()
        self.btn_toggle.setFixedWidth(52)
        self.btn_toggle.setStyleSheet(self._toggle_style())
        self.btn_toggle.setText("ON" if self._enabled else "OFF")
        self.btn_toggle.clicked.connect(self._toggle)

        self.btn_gen = QPushButton("立即生成")
        self.btn_gen.setFixedWidth(82)
        self.btn_gen.setEnabled(self._enabled)
        self.btn_gen.setStyleSheet(f"""
            QPushButton{{background:#0a1a2a;color:{NC['cyan']};border:1px solid {NC['border']};
                         border-radius:4px;padding:5px;font-size:11px;}}
            QPushButton:hover{{background:#1a3a5c;border-color:{NC['cyan']};}}
            QPushButton:disabled{{color:{NC['dim']};border-color:#0a1a2a;}}
        """)
        self.btn_gen.clicked.connect(self._start)

        self.btn_open = QPushButton("查看报告")
        self.btn_open.setFixedWidth(82)
        self.btn_open.setEnabled(False)
        self.btn_open.setStyleSheet(f"""
            QPushButton{{background:#0a1a0a;color:{NC['green']};border:1px solid #1a3a1a;
                         border-radius:4px;padding:5px;font-size:11px;}}
            QPushButton:hover{{background:#0f2a0f;border-color:{NC['green']};}}
            QPushButton:disabled{{color:{NC['dim']};border-color:#0a1a2a;background:#050d18;}}
        """)
        self.btn_open.clicked.connect(self._open)

        lay.addWidget(self.lbl); lay.addStretch()
        lay.addWidget(self.btn_toggle)
        lay.addWidget(self.btn_gen); lay.addWidget(self.btn_open)

    def _toggle_style(self) -> str:
        if self._enabled:
            return (f"QPushButton{{background:#0a2a1a;color:{NC['green']};border:1px solid #1a4a2a;"
                    f"border-radius:4px;padding:5px;font-size:11px;font-weight:bold;}}"
                    f"QPushButton:hover{{background:#0f3a1f;border-color:{NC['green']};}}")
        else:
            return (f"QPushButton{{background:#1a0a0a;color:{NC['dim']};border:1px solid #2a1a1a;"
                    f"border-radius:4px;padding:5px;font-size:11px;font-weight:bold;}}"
                    f"QPushButton:hover{{background:#2a1010;border-color:#aa3333;}}")

    def _toggle(self):
        self._enabled = not self._enabled
        cfg.set('stock.report_enabled', self._enabled)
        self.btn_toggle.setText("ON" if self._enabled else "OFF")
        self.btn_toggle.setStyleSheet(self._toggle_style())
        self.btn_gen.setEnabled(self._enabled)
        if self._enabled:
            self._set_status("📋 收盘报告已开启  //  每日 15:05 自动生成", NC['dim'])
        else:
            self._set_status("📋 收盘报告已关闭", NC['dim'])

    def _check_existing(self):
        today = date.today().strftime('%Y%m%d')
        reports = sorted(REPORTS_DIR.glob(f"report_{today}_*.html"))
        if reports:
            self._latest_path = str(reports[-1])
            self.btn_open.setEnabled(True)
            self._set_status("📋 今日报告已就绪", NC['green'])

    def _on_auto_trigger(self):
        self._set_status("⏰ 已收盘，自动生成报告...", NC['orange'])
        self._start()

    def _start(self):
        self.btn_gen.setEnabled(False)
        self.btn_gen.setText("生成中...")
        self._set_status("⏳ 正在准备...", NC['cyan'])

        w = self._worker
        generate_report(
            on_progress=lambda msg: w.progress.emit(msg),
            on_done=lambda path, err='': w.done.emit(path or '', err or ''),
        )

    def _on_progress(self, msg: str):
        self._set_status(f"⏳ {msg}", NC['cyan'])

    def _on_done(self, path: str, err: str):
        if err:
            self._set_status(f"❌ {err[:50]}", NC['red'])
        else:
            self._latest_path = path
            self.btn_open.setEnabled(True)
            self._set_status("✅ 报告生成完成，点击查看", NC['green'])
        self.btn_gen.setEnabled(True)
        self.btn_gen.setText("立即生成")

    def _set_status(self, msg: str, color: str):
        self.lbl.setText(msg)
        self.lbl.setStyleSheet(f"color:{color};font-size:11px;border:none;")

    def _open(self):
        if self._latest_path and Path(self._latest_path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_path))
