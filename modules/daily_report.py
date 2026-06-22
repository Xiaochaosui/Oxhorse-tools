"""
每日收盘报告 — 腾讯财经HTTP日K + AI分析 + HTML输出
触发时机：每个交易日 16:30 后自动生成，也可手动触发
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
# 东方财富行情/资金流接口（HTTPS，非交易时段也稳定）
EM_BASE    = "https://push2.eastmoney.com/api/qt"
EM_HEADERS = {
    "Referer":    "https://data.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
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


def _code_to_secid(code: str) -> str:
    """sh000001 → 1.000001 / sz002281 → 0.002281"""
    code = code.lower()
    prefix = "1" if code.startswith("sh") else "0"
    return f"{prefix}.{code[2:]}"


def _fetch_money_flow(code: str) -> dict:
    """
    从东方财富获取单只股票当日资金流数据。
    返回: {main_net, main_net_pct, amount, super_net, big_net, mid_net, small_net}
    全部获取失败时返回空字典 {}。
    字段说明:
        f62  = 主力净流入(元) = 超大单 + 大单
        f184 = 主力净流入占比(%)
        f48  = 成交额(元)
        f66  = 超大单净流入(元)  f69 = 超大单净占比
        f72  = 大单净流入(元)    f75 = 大单净占比
        f78  = 中单净流入(元)    f81 = 中单净占比
        f84  = 小单净流入(元)    f87 = 小单净占比
    """
    import json as _json
    secid = _code_to_secid(code)
    fields = "f43,f48,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87"
    try:
        r = requests.get(
            f"{EM_BASE}/stock/get",
            params={"secid": secid, "fields": fields},
            headers=EM_HEADERS, timeout=8,
        )
        d = r.json().get("data", {})
        if not d:
            return {}
        def _val(key):
            v = d.get(key)
            return float(v) if isinstance(v, (int, float)) else None
        return {
            "amount":       _val("f48"),   # 成交额(元)
            "main_net":     _val("f62"),   # 主力净流入(元)
            "main_net_pct": _val("f184"),  # 主力净流入占比(%)
            "super_net":    _val("f66"),   # 超大单净流入(元)
            "super_pct":    _val("f69"),
            "big_net":      _val("f72"),   # 大单净流入(元)
            "big_pct":      _val("f75"),
            "mid_net":      _val("f78"),   # 中单净流入(元)
            "mid_pct":      _val("f81"),
            "small_net":    _val("f84"),   # 小单净流入(元)
            "small_pct":    _val("f87"),
        }
    except Exception:
        return {}


def _fetch_hot_sectors(top_n: int = 5) -> list[dict]:
    """
    获取今日主力净流入 TOP-N 板块。
    返回: [{"name": "电力设备", "main_net": 7.7e9, "main_net_pct": 4.14}, ...]
    """
    try:
        r = requests.get(
            f"{EM_BASE}/clist/get",
            params={
                "pn": 1, "pz": top_n, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f62",
                "fs": "m:90+t:2",
                "fields": "f12,f14,f62,f184",
            },
            headers=EM_HEADERS, timeout=8,
        )
        items = r.json().get("data", {}).get("diff", [])
        return [
            {"name": it["f14"], "main_net": it.get("f62", 0), "main_net_pct": it.get("f184", 0)}
            for it in items if it.get("f62") is not None
        ]
    except Exception:
        return []


EM_DC_URL = "https://datacenter.eastmoney.com/securities/api/data/get"


def _fetch_lhb_data(days_back: int = 2) -> dict:
    """
    获取最近 N 个交易日龙虎榜数据。
    返回:
        {
          "date": "2026-06-16",
          "top_buy":  [{"name","code","change_rate","net_amt","reason","d1","d5"}, ...],  # 净买入TOP10
          "top_sell": [{"name","code","change_rate","net_amt","reason"}, ...],            # 净卖出TOP5
          "watchlist_hit": [{"name","code","change_rate","net_amt","reason"}, ...]        # 自选股中上榜
        }
    """
    since = (date.today() - timedelta(days=days_back + 2)).strftime('%Y-%m-%d')
    watchlist_codes = set(cfg.get('stock.watchlist', []))
    # 去掉 sh/sz 前缀，龙虎榜用纯数字代码
    watch_nums = {c[2:] for c in watchlist_codes if len(c) > 2}

    try:
        r = requests.get(
            EM_DC_URL,
            params={
                "type": "RPT_DAILYBILLBOARD_DETAILS",
                "sty":  "ALL",
                "p": 1, "ps": 100,
                "st": "TRADE_DATE,BILLBOARD_NET_AMT",
                "sr": "-1,-1",
                "filter": f"(TRADE_DATE>'{since}')",
            },
            headers=EM_HEADERS, timeout=12,
        )
        rows = r.json().get("result", {}).get("data") or []
    except Exception:
        return {}

    if not rows:
        return {}

    # 取最新交易日
    latest_date = rows[0]["TRADE_DATE"][:10]
    today_rows  = [x for x in rows if x["TRADE_DATE"][:10] == latest_date]

    def _row_to_item(x: dict) -> dict:
        return {
            "name":        x.get("SECURITY_NAME_ABBR", ""),
            "code":        x.get("SECURITY_CODE", ""),
            "change_rate": x.get("CHANGE_RATE") or 0,
            "net_amt":     (x.get("BILLBOARD_NET_AMT") or 0) / 1e8,   # 元→亿
            "buy_amt":     (x.get("BILLBOARD_BUY_AMT")  or 0) / 1e8,
            "sell_amt":    (x.get("BILLBOARD_SELL_AMT") or 0) / 1e8,
            "reason":      x.get("EXPLANATION", ""),
            "d1":          x.get("D1_CLOSE_ADJCHRATE") or 0,
            "d5":          x.get("D5_CLOSE_ADJCHRATE") or 0,
        }

    sorted_rows = sorted(today_rows, key=lambda x: x.get("BILLBOARD_NET_AMT") or 0, reverse=True)
    top_buy  = [_row_to_item(x) for x in sorted_rows[:10] if (x.get("BILLBOARD_NET_AMT") or 0) > 0]
    top_sell = [_row_to_item(x) for x in reversed(sorted_rows[-5:]) if (x.get("BILLBOARD_NET_AMT") or 0) < 0]
    watchlist_hit = [_row_to_item(x) for x in today_rows if x.get("SECURITY_CODE", "") in watch_nums]

    return {
        "date":          latest_date,
        "top_buy":       top_buy,
        "top_sell":      top_sell,
        "watchlist_hit": watchlist_hit,
    }


def _fetch_all_stocks() -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """并发获取所有自选股 K 线 + 资金流，返回 (klines_map, flow_map)"""
    codes = cfg.get('stock.watchlist', [])
    klines_map: dict[str, list[dict]] = {}
    flow_map:   dict[str, dict]       = {}
    threads = []

    def _worker(c):
        klines_map[c] = _fetch_klines(c, days=20)
        flow_map[c]   = _fetch_money_flow(c)

    for code in codes:
        t = threading.Thread(target=_worker, args=(code,), daemon=True)
        threads.append(t); t.start()
    for t in threads:
        t.join(timeout=25)
    return klines_map, flow_map


# ── Claude 分析 ─────────────────────────────────────────────────────────────

def _fmt_yuan(v) -> str:
    """将元数值格式化为易读字符串，None 返回 '-'"""
    if v is None:
        return "-"
    sign = "+" if v >= 0 else ""
    abs_v = abs(v)
    if abs_v >= 1e8:
        return f"{sign}{v/1e8:.2f}亿"
    if abs_v >= 1e4:
        return f"{sign}{v/1e4:.0f}万"
    return f"{sign}{v:.0f}"


def _build_prompt(
    stocks_data: dict[str, list[dict]],
    flow_map:    dict[str, dict]  | None = None,
    lhb_data:    dict             | None = None,
) -> str:
    today    = date.today().strftime('%Y-%m-%d')
    flow_map = flow_map or {}
    lhb_data = lhb_data or {}

    # ── 板块资金热度 ──────────────────────────────────────────────────────────
    hot_sectors  = _fetch_hot_sectors(top_n=5)
    sector_lines = [
        f"  - {s['name']}：主力净流入 {_fmt_yuan(s['main_net'])}（占比 {s['main_net_pct']:+.2f}%）"
        for s in hot_sectors
    ]

    lines = [
        f"你是一位专业的A股量化分析师。今天是 {today}，以下是完整的市场数据，"
        f"请给出精准、有操作价值的收盘分析报告，包含龙虎榜解读、行情预测和买入推荐。",
        "",
    ]

    # ── 1. 板块资金背景 ───────────────────────────────────────────────────────
    if sector_lines:
        lines += ["## 一、今日板块资金热度（主力净流入 TOP5）", *sector_lines, ""]

    # ── 2. 龙虎榜数据 ─────────────────────────────────────────────────────────
    if lhb_data:
        lhb_date = lhb_data.get("date", today)
        lines += [f"## 二、龙虎榜数据（{lhb_date}）", ""]

        # 净买入榜
        top_buy = lhb_data.get("top_buy", [])
        if top_buy:
            lines.append("### 主力净买入 TOP（机构/游资主动建仓信号）")
            lines.append("股票 | 涨跌幅 | 净买入(亿) | 买入(亿) | 卖出(亿) | 上榜原因 | 次日涨跌 | 5日涨跌")
            lines.append("-----|--------|-----------|--------|--------|---------|---------|--------")
            for x in top_buy:
                d1_str = f"{x['d1']:+.2f}%" if x['d1'] else "-"
                d5_str = f"{x['d5']:+.2f}%" if x['d5'] else "-"
                lines.append(
                    f"{x['name']}({x['code']}) | {x['change_rate']:+.2f}% | "
                    f"+{x['net_amt']:.2f} | {x['buy_amt']:.2f} | {x['sell_amt']:.2f} | "
                    f"{x['reason'][:25]} | {d1_str} | {d5_str}"
                )
            lines.append("")

        # 净卖出榜
        top_sell = lhb_data.get("top_sell", [])
        if top_sell:
            lines.append("### 主力净卖出 TOP（主力出货/机构减仓信号）")
            lines.append("股票 | 涨跌幅 | 净卖出(亿) | 上榜原因")
            lines.append("-----|--------|-----------|--------")
            for x in top_sell:
                lines.append(
                    f"{x['name']}({x['code']}) | {x['change_rate']:+.2f}% | "
                    f"{x['net_amt']:.2f} | {x['reason'][:30]}"
                )
            lines.append("")

        # 自选股命中
        wl_hit = lhb_data.get("watchlist_hit", [])
        if wl_hit:
            lines.append("### 自选股中上榜个股（重点关注）")
            for x in wl_hit:
                lines.append(
                    f"- **{x['name']}**（{x['code']}）涨跌 {x['change_rate']:+.2f}%  "
                    f"净买入 {x['net_amt']:+.2f}亿  原因：{x['reason']}"
                )
            lines.append("")
        else:
            lines.append("*自选股今日无龙虎榜上榜记录*\n")

    # ── 3. 持仓/自选股数据 ────────────────────────────────────────────────────
    lines += ["## 三、持仓/自选股行情数据", "K线格式：日期 | 开盘 | 收盘 | 最高 | 最低 | 成交量(万股) | 成交额 | 涨跌幅"]

    for code, klines in stocks_data.items():
        if not klines:
            lines.append(f"\n### {code} — 数据获取失败，跳过")
            continue
        name = klines[-1].get('name', code)
        flow = flow_map.get(code, {})
        lines.append(f"\n### {name}（{code}）")

        if flow:
            amt       = _fmt_yuan(flow.get("amount"))
            main_net  = _fmt_yuan(flow.get("main_net"))
            main_pct  = f"{flow['main_net_pct']:+.2f}%" if flow.get("main_net_pct") is not None else "-"
            super_net = _fmt_yuan(flow.get("super_net"))
            big_net   = _fmt_yuan(flow.get("big_net"))
            mid_net   = _fmt_yuan(flow.get("mid_net"))
            small_net = _fmt_yuan(flow.get("small_net"))
            lines.append(
                f"**今日资金流**：成交额={amt} | 主力净={main_net}({main_pct}) | "
                f"超大单净={super_net} | 大单净={big_net} | 中单净={mid_net} | 小单净={small_net}"
            )

        lines.append("近20日K线：")
        for k in klines:
            vol_wan = k['volume'] / 100
            amt_str = _fmt_yuan(k.get('amount') or k['volume'] * k['close'])
            lines.append(
                f"{k['date']} | {k['open']:.2f} | {k['close']:.2f} | "
                f"{k['high']:.2f} | {k['low']:.2f} | "
                f"{vol_wan:.0f}万股 | {amt_str} | {k['chg_pct']:+.2f}%"
            )

    # ── 4. 分析要求 ───────────────────────────────────────────────────────────
    lines += [
        "",
        "## 四、分析要求",
        "",
        "### A. 自选股逐一分析（数据失败的跳过）",
        "",
        "对每只有数据的标的输出：",
        "1. **今日量价与资金** — 涨跌幅、放量/缩量、主力净流入方向与力度、超大单与大单是否一致、有无量价背离",
        "2. **近期趋势** — 5/10/20日均线方向与多空排列、当前关键支撑/压力位、是否处于突破/回踩/震荡位",
        "3. **操作建议** — 明确给出：买入/持有/减仓/观望/止损，附简短理由（≤3句）+ 主要下行风险",
        "",
        "### B. 龙虎榜深度解读",
        "",
        "基于上方龙虎榜数据：",
        "1. **净买入榜解读** — 哪几只是机构主动建仓信号？哪几只是游资炒作？结合上榜原因和次日/5日表现判断成功率",
        "2. **净卖出榜解读** — 是主力出货还是对倒？散户应回避哪些？",
        "3. **龙虎榜规律总结** — 今日龙虎榜整体透露什么市场信号（资金偏好哪类标的/板块）",
        "",
        "### C. 明日行情预测",
        "",
        "综合板块资金热度 + 自选股表现 + 龙虎榜信号，预测：",
        "1. **大盘方向** — 明日上证/创业板大概率走势（涨/跌/震荡），给出概率判断（如：上涨60%/震荡30%/下跌10%）",
        "2. **热点板块** — 明日最可能持续活跃的1-2个板块，说明逻辑",
        "3. **风险提示** — 明日最主要的1个下行风险（政策/外盘/技术面）",
        "",
        "### D. 最值得买入推荐（最重要）",
        "",
        "从以下维度综合评分，给出 **TOP 3 买入推荐**：",
        "- 维度1：资金流持续流入（主力+超大单同向）",
        "- 维度2：技术形态良好（均线多头/突破/回踩支撑）",
        "- 维度3：龙虎榜机构净买入（若有）",
        "- 维度4：板块景气（所在板块今日资金净流入为正）",
        "- 维度5：性价比（涨幅不过大、仍有上行空间）",
        "",
        "每条推荐格式：",
        "**【买入推荐 #N】股票名（代码）**",
        "- 综合评分：X/5",
        "- 买入理由：（2-3句，引用具体数据）",
        "- 建议买入区间：X.XX ~ X.XX 元",
        "- 目标价：X.XX 元（预期涨幅 X%）",
        "- 止损位：X.XX 元",
        "- 持有周期：短线（1-3日）/ 中线（1-2周）/ 波段（1个月以上）",
        "",
        "⚠️ 注意：推荐必须基于数据，不能无中生有；若数据不足以支撑推荐，直接说明原因。",
        "",
        "输出用 Markdown 格式，语气专业直接，量化具体数字，不要泛泛而谈。",
    ]
    return '\n'.join(lines)


def _call_claude(prompt: str, on_progress=None) -> str:
    """使用 streaming 调用 AI API，避免长请求被网关 524 超时"""
    llm = cfg.get_llm()
    api_key  = llm['api_key']
    base_url = llm['base_url'].rstrip('/')
    model    = llm['model']
    max_tok  = llm['max_tokens']
    timeout  = llm['timeout']
    if not api_key:
        return "⚠️ 未找到 API Key，请在 config/llm.json 中配置 api_key"
    if on_progress:
        on_progress(f"正在调用 {model} 分析（流式输出，约30-60秒）...")
    try:
        import json as _json
        url = f"{base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": max_tok,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        }
        r = requests.post(url, headers=headers, json=body, timeout=timeout, stream=True)
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


# ── 结论词提取 ───────────────────────────────────────────────────────────────

def _extract_conclusion(analysis: str) -> str:
    """
    从 AI 分析文本中提取一个结论词（2-3字），用于文件名。
    扫描"整体市场研判"附近段落，按优先级匹配关键词。
    匹配不到则返回"分析"。
    """
    # 优先从整体研判段落附近取，取不到就全文搜
    anchor = re.search(r'整体市场研判.*', analysis)
    scope = analysis[anchor.start():anchor.start() + 300] if anchor else analysis

    candidates = [
        # 强势偏多
        ("强势", ["强势", "强烈看多", "大涨"]),
        ("看多", ["看多", "偏多", "做多", "多头"]),
        ("上攻", ["上攻", "突破", "上行"]),
        # 弱势偏空
        ("弱势", ["弱势", "强烈看空", "大跌"]),
        ("看空", ["看空", "偏空", "做空", "空头"]),
        ("下行", ["下行", "回落", "下跌"]),
        # 中性
        ("震荡", ["震荡", "盘整", "横盘", "区间"]),
        ("谨慎", ["谨慎", "观望", "等待信号"]),
        ("分化", ["分化", "结构性"]),
    ]
    for label, keywords in candidates:
        if any(kw in scope for kw in keywords):
            return label
    return "分析"


# ── HTML 报告渲染 ─────────────────────────────────────────────────────────────

def _md_to_html(md: str) -> str:
    import html as h

    def _fmt(c: str) -> str:
        c = h.escape(c)
        c = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', c)
        c = re.sub(r'`(.+?)`', r'<code>\1</code>', c)
        return c

    def _parse_row(r: str) -> list[str]:
        return [c.strip() for c in r.strip().strip('|').split('|')]

    def _is_sep(r: str) -> bool:
        return bool(re.match(r'^[\|\-\s:]+$', r.strip()))

    lines = md.split('\n')
    out = []
    in_code = False
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith('```'):
            in_code = not in_code
            out.append('<pre>' if in_code else '</pre>')
            i += 1
            continue

        if in_code:
            out.append(h.escape(line))
            i += 1
            continue

        # ── Markdown 表格 ───────────────────────────────────────────────────
        s = line.strip()
        if s.startswith('|') and s.endswith('|') and s.count('|') >= 2:
            tbl = []
            while i < len(lines):
                ls = lines[i].strip()
                if ls.startswith('|') and ls.endswith('|'):
                    tbl.append(lines[i])
                    i += 1
                else:
                    break
            rows = [r for r in tbl if not _is_sep(r)]
            if rows:
                out.append('<table class="md-table">')
                out.append(
                    '<thead><tr>'
                    + ''.join(f'<th>{_fmt(c)}</th>' for c in _parse_row(rows[0]))
                    + '</tr></thead>'
                )
                out.append('<tbody>')
                for row in rows[1:]:
                    out.append(
                        '<tr>'
                        + ''.join(f'<td>{_fmt(c)}</td>' for c in _parse_row(row))
                        + '</tr>'
                    )
                out.append('</tbody></table>')
            continue

        # ── 普通行 ──────────────────────────────────────────────────────────
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
                cleaned = re.sub(r"^- |^\d+\. ", "", line)
                out.append(f'<li>{cleaned}</li>')
            elif line.strip() == '':
                out.append('<p style="margin:4px 0"></p>')
            else:
                out.append(f'<p>{line}</p>')
        i += 1

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
.hd .meta {{ font-size:11px; color:#3a5a7a; margin-top:5px; font-family:'Consolas','Courier New',monospace; }}
.chips {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:24px; }}
.chip {{ background:#07111f; border:1px solid #1a3a5c; border-radius:8px;
         padding:8px 14px; display:flex; flex-direction:column; align-items:center; min-width:88px; }}
.cn {{ font-size:10px; color:#5a8aaa; margin-bottom:2px; }}
.cp {{ font-size:15px; color:#e8f4ff; font-weight:bold; font-family:'Consolas','Courier New',monospace; }}
.cc {{ font-size:12px; font-weight:bold; font-family:'Consolas','Courier New',monospace; }}
.body {{ background:#07111f; border:1px solid #1a3a5c; border-radius:10px; padding:24px 28px; }}
h1 {{ font-size:19px; color:#4fc3f7; margin:20px 0 8px; }}
h2 {{ font-size:16px; color:#4fc3f7; margin:20px 0 8px;
      border-left:3px solid #4fc3f7; padding-left:10px; }}
h3 {{ font-size:14px; color:#90caf9; margin:14px 0 6px; }}
p {{ margin:5px 0; color:#b8cce0; }}
li {{ margin:4px 0 4px 22px; color:#b8cce0; }}
strong {{ color:#ffd740; }}
code {{ background:#0a1a2a; border:1px solid #1a3a5c; border-radius:3px;
        padding:1px 5px; font-family:'Consolas','Courier New',monospace; font-size:12px; color:#00e676; }}
pre {{ background:#0a1a2a; border:1px solid #1a3a5c; border-radius:6px;
       padding:12px; font-family:'Consolas','Courier New',monospace; font-size:12px; overflow-x:auto; color:#aed6f1; }}
.md-table {{ border-collapse:collapse; width:100%; margin:10px 0; font-size:13px; }}
.md-table th {{ background:#0a1e38; color:#4fc3f7; font-weight:600; text-align:left;
                padding:7px 10px; border:1px solid #1a3a5c; white-space:nowrap; }}
.md-table td {{ padding:6px 10px; border:1px solid #0d2540; color:#b8cce0; vertical-align:top; }}
.md-table tr:nth-child(even) td {{ background:#060f1c; }}
.md-table tr:hover td {{ background:#0e1f35; }}
.ft {{ margin-top:24px; font-size:11px; color:#2a4a6a; text-align:center; font-family:'Consolas','Courier New',monospace; }}
</style>
</head>
<body>
<div class="hd">
  <h1>📊 每日收盘分析报告</h1>
  <div class="meta">❯ generated at {generated_at} &nbsp;// powered by DeepSeek</div>
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
            if on_progress: on_progress("正在获取行情数据、资金流与龙虎榜...")

            # 并发拉取：K线/资金流 + 龙虎榜
            lhb_result: dict = {}
            def _lhb_worker():
                nonlocal lhb_result
                lhb_result = _fetch_lhb_data(days_back=2)

            lhb_thread = threading.Thread(target=_lhb_worker, daemon=True)
            lhb_thread.start()
            klines_map, flow_map = _fetch_all_stocks()
            lhb_thread.join(timeout=15)

            success = sum(1 for v in klines_map.values() if v)
            flow_ok = sum(1 for v in flow_map.values() if v)
            lhb_ok  = len(lhb_result.get("top_buy", [])) + len(lhb_result.get("top_sell", []))
            if on_progress: on_progress(
                f"获取完成（K线 {success}/{len(klines_map)} 只，资金流 {flow_ok} 只，"
                f"龙虎榜 {lhb_ok} 条），正在分析..."
            )

            prompt      = _build_prompt(klines_map, flow_map, lhb_result)
            analysis    = _call_claude(prompt, on_progress)
            stocks_data = klines_map

            if on_progress: on_progress("正在生成 HTML...")
            now_str    = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            html       = _build_html(analysis, stocks_data, now_str)
            conclusion = _extract_conclusion(analysis)
            fname      = REPORTS_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}_{conclusion}.html"
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

        self.lbl = QLabel("📋 收盘报告  //  每日 16:30 自动生成")
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
            self._set_status("📋 收盘报告已开启  //  每日 16:30 自动生成", NC['dim'])
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
