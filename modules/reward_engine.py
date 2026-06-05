"""
奖励引擎 — 基于行为数据给出夸夸 + 成就解锁
"""
import random
from datetime import date, timedelta
from modules import health_db as db

# ── 夸夸语句池（按场景分组，互不交叉，保持新鲜感）──────────────────────────────

_PRAISE_WATER = [
    ("💧 水分充足！", "你的细胞正在开心地游泳，皮肤都在感谢你~"),
    ("🌊 冲鸭！", "水喝够了，大脑算力提升 10%，模型收敛更快！"),
    ("✨ 优秀！", "算法工程师的血液浓度恰到好处，GPU 都为你骄傲！"),
    ("💎 自律达人！", "别人忘了喝水，你没有，这就是差距！"),
    ("🐬 水生生物认证！", "喝水喝得这么积极，鱼儿都要向你学习了~"),
    ("🌱 补水小能手！", "每一口水都是给自己充的电，续航++"),
    ("🚀 满状态！", "水分充盈，思维清晰，今天的 loss 一定会降！"),
    ("🎯 完美执行！", "提醒一响就来喝水，执行力堪比零延迟推理！"),
    ("🌈 健康小达人！", "你是今天工位上喝水最认真的那个人，没有之一！"),
    ("🧬 细胞欢呼！", "每一个细胞都在喊：谢谢你没有让我们变干！"),
    ("⚡ 活力满满！", "喝水这件小事，你坚持得比 5 sigma 精度还高！"),
    ("🎖 持续在线！", "神经元补水完毕，代码思维刷新，继续冲！"),
]

_PRAISE_MOVE = [
    ("🦸 英雄归来！", "站起来走了一圈，你的椎间盘已经感动哭了！"),
    ("🏆 运动健将！", "久坐的算法工程师里，你是最爱动的那一个，杰出！"),
    ("🔥 活力爆棚！", "血液循环一波，大脑供氧提升，下一行代码会更优雅！"),
    ("🌿 生命在于运动！", "你刚刚多活了 22 分钟——科学证实的！"),
    ("🎪 站立冠军！", "别人在坐着秃头，你在站着变强，格局完全不同！"),
    ("💪 肌肉感谢你！", "活动一下，腰不疼了，颈椎也不哭了，太好了！"),
    ("🦅 展翅高飞！", "从椅子上解放自己，你刚完成了今日最优决策之一！"),
    ("🌅 满血复活！", "站起来走走，相当于给大脑做了一次深度 GC，清爽！"),
    ("🎯 身体管理大师！", "别人只管 loss，你连身体都在 fine-tuning！"),
    ("🧘 内外兼修！", "模型调参一流，身体管理也一流，真·全栈工程师！"),
    ("🚀 起飞！", "站起来这个动作，帮你多续了 N 年的工程师生涯！"),
    ("🎊 战胜久坐！", "你刚战胜了现代人最大的健康杀手，了不起！"),
    ("⚡ 充能完毕！", "活动结束，能量值回满，冲冲冲！"),
    ("🌟 自律典范！", "提醒到，立刻执行，这种响应速度，模型服你！"),
]

_PRAISE_MILESTONE = {
    # 当日次数里程碑 → (emoji, title, body)
    'water_3':  ("🌊", "已喝 3 杯水！",    "今天的水分补充开局良好，继续保持~"),
    'water_6':  ("💦", "已喝 6 杯水！",    "超过大多数同事了，皮肤状态绝对在线！"),
    'water_8':  ("🏅", "今日喝水达标！",   "8 杯水全部完成！你的肾脏在鼓掌！"),
    'water_10': ("👑", "喝水超额完成！",   "10 杯了！真·水润算法工程师，皮肤会感谢你的！"),
    'move_3':   ("🏃", "起身 3 次！",      "腰不酸、背不痛，今天的状态绝了！"),
    'move_5':   ("⚡", "起身 5 次！",      "已经超过 90% 久坐程序员了，你在人生赢家轨道上！"),
    'move_8':   ("🏆", "今日运动达标！",   "8 次起身完成！你的颈椎想颁给你一个大奖！"),
    'move_10':  ("🥇", "运动超神！",       "10 次！脊柱精英，工位健将，未来 30 年腰不痛！"),
}

# 连续打卡成就
_STREAK_ACHIEVEMENTS = [
    (3,   "🌱 初露锋芒",  "连续 3 天坚持提醒响应，好习惯正在生根！"),
    (7,   "🔥 一周之约",  "整整 7 天！你已经超过了 80% 人的坚持时长！"),
    (14,  "💪 钢铁意志",  "两周连续打卡，这不是运气，是实力+自律！"),
    (21,  "🧬 习惯已成",  "21 天，心理学说这是习惯形成的关键周期，你做到了！"),
    (30,  "🏅 月度冠军",  "整整一个月！你是团队里最健康的算法工程师，没有之一！"),
    (60,  "👑 传奇级别",  "60 天连续！你的自律已经成为一种超能力！"),
    (100, "🌟 百天奇迹",  "100 天！你不只是算法工程师，你是自律工程师！"),
]

# 今日综合评分语
_DAILY_SCORE_COMMENTS = {
    (90, 101): ("🏆 完美今天！",      "水喝够了，身体动了，今天的你满分运行！"),
    (70,  90): ("⭐ 优秀表现！",      "今天健康管理很稳，继续这个节奏！"),
    (50,  70): ("👍 不错不错！",      "完成了大半，比昨天强就是进步！"),
    (30,  50): ("🌱 在路上了",        "今天开了个好头，明天让数据更好看！"),
    ( 0,  30): ("💡 还有提升空间",    "身体是最好的武器，多喝水多动动！"),
}


# ── 奖励计算 ───────────────────────────────────────────────────────────────────

def get_praise(event_type: str, count_today: int) -> tuple[str, str, str | None]:
    """
    返回 (emoji_title, body, milestone_key_or_None)
    event_type: TYPE_WATER | TYPE_MOVE
    count_today: 今日完成次数（含本次）
    """
    # 先检查里程碑
    milestone_key = f"{event_type}_{count_today}"
    if milestone_key in _PRAISE_MILESTONE:
        e, t, b = _PRAISE_MILESTONE[milestone_key]
        return t, b, milestone_key

    # 普通夸夸
    pool = _PRAISE_WATER if event_type == db.TYPE_WATER else _PRAISE_MOVE
    t, b = random.choice(pool)
    return t, b, None


def check_streak_achievement(event_type: str) -> tuple[str, str, str] | None:
    """
    检查是否刚达到连续打卡成就，返回 (badge, title, body) 或 None
    """
    days = db.streak(event_type, min_per_day=1)
    for threshold, badge, body in _STREAK_ACHIEVEMENTS:
        if days == threshold:
            return badge, f"连续 {threshold} 天打卡！", body
    return None


def daily_score() -> tuple[int, str, str]:
    """
    今日综合健康得分 0-100，返回 (score, title, body)
    """
    summary = db.daily_summary()

    water_comp = summary[db.TYPE_WATER][db.ACT_COMPLETED]
    move_comp  = summary[db.TYPE_MOVE][db.ACT_COMPLETED]
    meal_comp  = summary[db.TYPE_MEAL][db.ACT_COMPLETED]

    water_score = min(water_comp / 8,  1.0) * 40   # 满分 40
    move_score  = min(move_comp  / 8,  1.0) * 40   # 满分 40
    meal_score  = min(meal_comp  / 2,  1.0) * 20   # 满分 20
    total = int(water_score + move_score + meal_score)

    for (lo, hi), (title, body) in _DAILY_SCORE_COMMENTS.items():
        if lo <= total < hi:
            return total, title, body
    return total, "继续加油！", "每一天都是新的开始~"


def get_encouragement_for_count(event_type: str, count: int) -> str:
    """给当日次数一句简短鼓励（用于卡片里的小提示）"""
    targets = {db.TYPE_WATER: 8, db.TYPE_MOVE: 8}
    target = targets.get(event_type, 8)
    remaining = max(target - count, 0)
    if remaining == 0:
        return "🎊 今日目标已达成，太棒了！"
    if count == 0:
        return "💪 第一次最难，迈出去就赢了！"
    pct = count / target
    if pct < 0.4:
        msgs = ["起步很好，继续冲！", "开门红！节奏保持住！", "好的开始是成功的一半~"]
    elif pct < 0.7:
        msgs = ["过半了！收尾阶段加把劲！", "稳住！快到终点了！", "超过一半了，优秀！"]
    else:
        msgs = [f"还差 {remaining} 次就满了，冲！", "快满了！最后一口气！", "就差临门一脚了！"]
    return random.choice(msgs)
