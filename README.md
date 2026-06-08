# OxHorse Tools

上班族桌面效率小工具，深色科技风 UI，常驻系统托盘。

## 功能一览

| 窗口 | 功能 |
|------|------|
| ⏰ CLOCK | 上下班打卡 · 工作倒计时 · 今日实时工资 · 发薪倒计时 |
| 🔔 REMIND | 喝水/起身定时提醒 · 全屏粒子爆炸弹窗 · 午饭/晚饭倒计时 |
| 📊 STOCK | A 股行情盯盘 · 每日收盘 Claude 分析报告 · 伪装成终端浮窗 |
| ✓ TODO | 飞书多维表格（Bitable）双向同步任务清单 |
| 📈 STATS | 健康统计：喝水/起身/吃饭完成率 · 连续打卡 · 7 日趋势 · 时段热力图 |
| 🕰 LIFELOG | 时间胶囊：自动记录活跃应用 + 剪贴板内容 · 日历回溯 · 气泡时间轴 |
| ⚙️ SETTINGS | 独立设置窗口：上下班时间 / 薪资 / 提醒间隔 / 飞书配置 |

## 界面预览

### ⏰ CLOCK · 工作时钟

![CLOCK](assets/imgs/CLOCK.png)

### 🔔 REMIND · 提醒

![REMIND](assets/imgs/REMIND.png)

### 📊 STOCK · 盯盘

![STOCK](assets/imgs/STOCK.png)

### ✓ TODO · 飞书

![TODO](assets/imgs/TODO.png)

### 📈 STATS · 健康统计

![STATS](assets/imgs/STATS.png)

---

## 环境要求

| 依赖 | 版本 |
|------|------|
| Python | 3.10+ |
| PyQt6 | 6.x |
| akshare | 最新 |
| requests | 任意 |
| notify-send | Linux 桌面通知（通常已内置） |

一键安装：

```bash
pip install PyQt6 akshare requests
```

---

## 启动方式

```bash
# 直接运行
python3 main.py

# 或用脚本
bash run.sh
```

首次启动后窗口出现在屏幕右下角，关闭按钮不退出程序，而是缩进系统托盘。

**快捷键：**

| 快捷键 | 作用 |
|--------|------|
| `Ctrl+Shift+W` | 切换所有窗口显示 / 隐藏 |
| 托盘图标单击 | 同上 |
| 托盘右键菜单 | 显示/隐藏 · 设置 · 健康统计 · 时间胶囊 · 退出 |

---

## 初始配置

所有配置存储在 `config/settings.json`（不纳入 git），可直接编辑，也可通过托盘菜单 → **设置** 修改。

### 1. 上下班时间 & 薪资

```json
"work": {
  "start_time": "09:00",
  "end_time": "18:00",
  "monthly_salary": 30000,
  "salary_day": 30
}
```

### 2. 健康提醒间隔

```json
"reminders": {
  "water_interval_minutes": 60,
  "stand_interval_minutes": 60,
  "lunch_time": "12:00",
  "dinner_time": "18:30"
}
```

提醒到点后点击「✓ 喝了 / 动了 / 吃了」重置计时器；同时会弹出全屏粒子特效提醒窗口，并通过 `notify-send` 推送桌面通知。

### 3. A 股自选股

默认已添加上证指数、沪深300、创业板指。

- **添加个股：** 在底部输入框填入代码后回车（如 `sh600519` / `sz000001` / 纯数字自动判断交易所）
- **删除：** 选中行后点 DEL
- **刷新频率：** 交易时段每 10 秒自动刷新；非交易时段不发请求
- **收盘报告：** 每个交易日 15:05 后自动生成，调用 Claude 分析当日行情，输出 HTML 报告

**隐蔽说明：** 窗口标题栏伪装成 `python3 data_pipeline.py --monitor`，表格使用终端配色。

### 4. 飞书 TODO

在 TODO 标签页底部的 FEISHU CONFIG 区域填入后点 SAVE：

| 字段 | 说明 | 获取方式 |
|------|------|----------|
| App ID | 飞书应用 ID | 飞书开放平台 → 我的应用 → 应用凭据 |
| App Secret | 飞书应用密钥 | 同上 |
| Bitable App Token | 多维表格应用 Token | 打开多维表格 → URL 中 `/base/` 后面那段 |
| Table ID | 表格 ID | 多维表格 → 扩展字段 → API → 复制 tableId |

**多维表格字段要求：**

| 字段名 | 类型 |
|--------|------|
| 标题 | 文本 |
| 优先级 | 单选（P0 / P1 / P2 / P3） |
| 状态 | 单选（待处理 / 进行中 / 已完成 / 已取消） |
| 备注 | 文本 |

配置完成后点「⟳ SYNC」手动拉取；之后每 5 分钟自动同步一次。

### 5. 时间胶囊（LifeLog）

从托盘菜单 → **时间胶囊** 打开。自动记录：

- **活跃应用**：每隔一段时间记录当前前台窗口（应用名 + 标题 + 截图路径）
- **剪贴板**：监控剪贴板变化，自动保存文本 / 图片内容

数据存储在本地 SQLite（`config/health.db`），通过日历选择日期后可在气泡时间轴中回溯当天活动记录。

---

## 项目结构

```
Oxhorse-tools/
├── main.py                    # 主入口：无边框多窗口 + 系统托盘 + 快捷键
├── run.sh                     # 启动脚本
├── config/                    # 本地运行时数据（不纳入 git）
│   ├── settings.json          # 用户配置
│   ├── session.json           # 当日打卡状态（跨重启恢复）
│   ├── window_positions.json  # 各窗口位置记忆
│   └── health.db              # SQLite：健康记录 + LifeLog
└── modules/
    ├── theme.py               # QSS 深色科技风主题 + 颜色常量
    ├── config_manager.py      # 配置文件读写
    ├── salary_clock.py        # CLOCK：时钟 / 工资 / 发薪
    ├── reminders.py           # REMIND：喝水 / 吃饭 / 站起来
    ├── fullscreen_alert.py    # 全屏粒子爆炸提醒弹窗
    ├── punch_panel.py         # 打卡大按钮面板（带光晕粒子动效）
    ├── work_session.py        # 工作状态机（BEFORE→WORKING→OVERTIME）
    ├── stock_monitor.py       # STOCK：A 股行情
    ├── daily_report.py        # 每日收盘 Claude 分析报告
    ├── todo_feishu.py         # TODO：飞书 Bitable 同步
    ├── health_db.py           # 健康数据 SQLite 读写
    ├── health_stats.py        # STATS：健康统计弹窗
    ├── reward_engine.py       # 奖励引擎：夸夸语句 + 成就解锁
    ├── reward_popup.py        # 奖励弹窗
    ├── lifelog_db.py          # LifeLog SQLite 读写
    ├── lifelog.py             # 时间胶囊弹窗（日历 + 气泡时间轴）
    ├── lifelog_monitor.py     # 后台监控：活跃应用 + 剪贴板
    └── settings_window.py     # 独立设置窗口
```

---

## 常见问题

**Q: 启动报 `No module named 'PyQt6'`**
```bash
pip install PyQt6
```

**Q: 股票数据拉不到**
- 非交易时段（9:30前、11:30-13:00、15:00后及周末）不拉数据，这是正常的
- 检查网络是否能访问新浪财经

**Q: 桌面通知不弹**
```bash
which notify-send        # 检查是否安装
sudo apt install libnotify-bin   # 没有则安装
```

**Q: 飞书同步失败**
- 确认应用已开通 `bitable:app` 读写权限
- App Token 是 URL 里 `/base/` 后、`?` 前的那段（如 `BMxxxxxxxxx`）
- Table ID 在多维表格 → 右上角「···」→「API」中复制

**Q: 窗口不见了**
- 点系统托盘图标，或按 `Ctrl+Shift+W`

**Q: 收盘报告生成失败**
- 检查 `config/settings.json` 中是否配置了 Claude API Key（`claude_api_key` 字段）
