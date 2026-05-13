"""
主动行为系统 (Proactive Behavior System)
实现 Lapwing 的自主行为：无聊积累、主动发消息、目标驱动
"""
import asyncio
import random
import logging
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
import json

from settings import Settings
from utils import load_or_initialize_json, save_json


class ProactiveState(Enum):
    """Lapwing 的主动行为状态"""
    IDLE = auto()           # 空闲，可能感到无聊
    THINKING = auto()       # 正在思考
    MISSING = auto()        # 想念主人
    WORRIED = auto()        # 担心主人
    EXCITED = auto()        # 有想分享的事情
    SLEEPY = auto()         # 该休息了


@dataclass
class BoredomConfig:
    """无聊系统配置"""
    # 无聊积累速度 (每秒增加的无聊值)
    boredom_rate_idle: float = 0.5          # 空闲时的积累速度
    boredom_rate_active: float = -2.0       # 互动时的减少速度
    boredom_max: float = 100.0              # 无聊上限
    boredom_threshold_low: float = 30.0      # 轻微无聊阈值
    boredom_threshold_medium: float = 60.0   # 中度无聊阈值
    boredom_threshold_high: float = 85.0     # 高度无聊阈值

    # 时间阈值 (分钟)
    silence_threshold_short: int = 5        # 5分钟没说话 -> 轻微无聊
    silence_threshold_long: int = 30       # 30分钟 -> 想念
    silence_threshold_very_long: int = 120  # 2小时 -> 担心

    # 主动行为概率 (每分钟检查一次)
    proactive_chance_low: float = 0.1       # 无聊值 30-60
    proactive_chance_medium: float = 0.3    # 无聊值 60-85
    proactive_chance_high: float = 0.6    # 无聊值 85+


@dataclass
class ProactiveIntent:
    """主动行为意图"""
    intent_type: str                    # 意图类型
    priority: int                       # 优先级 (1-10, 越高越重要)
    content: str                       # 内容模板
    cooldown_minutes: int              # 冷却时间 (分钟)
    conditions: Dict[str, Any]         # 触发条件
    last_triggered: Optional[datetime] = None


@dataclass
class Goal:
    """Lapwing 的目标"""
    id: str
    description: str
    priority: int
    created_at: datetime
    deadline: Optional[datetime] = None
    progress: float = 0.0               # 0-100
    status: str = "active"              # active, completed, abandoned
    related_memories: List[str] = field(default_factory=list)


class GoalManager:
    """目标管理系统"""

    def __init__(self, state_file: Path = Path("json/lapwing_goals.json")):
        self.state_file = state_file
        self.goals: List[Goal] = []
        self.completed_goals: List[Goal] = []
        self._load_goals()

    def _load_goals(self):
        """从文件加载目标"""
        data = load_or_initialize_json(self.state_file, {
            "active": [],
            "completed": []
        })

        for g in data.get("active", []):
            self.goals.append(Goal(
                id=g["id"],
                description=g["description"],
                priority=g.get("priority", 5),
                created_at=datetime.fromisoformat(g["created_at"]),
                deadline=datetime.fromisoformat(g["deadline"]) if g.get("deadline") else None,
                progress=g.get("progress", 0.0),
                status=g.get("status", "active"),
                related_memories=g.get("related_memories", [])
            ))

        for g in data.get("completed", []):
            self.completed_goals.append(Goal(
                id=g["id"],
                description=g["description"],
                priority=g["priority"],
                created_at=datetime.fromisoformat(g["created_at"]),
                deadline=datetime.fromisoformat(g["deadline"]) if g.get("deadline") else None,
                progress=100.0,
                status="completed"
            ))

    def _save_goals(self):
        """保存目标到文件"""
        data = {
            "active": [
                {
                    "id": g.id,
                    "description": g.description,
                    "priority": g.priority,
                    "created_at": g.created_at.isoformat(),
                    "deadline": g.deadline.isoformat() if g.deadline else None,
                    "progress": g.progress,
                    "status": g.status,
                    "related_memories": g.related_memories
                }
                for g in self.goals
            ],
            "completed": [
                {
                    "id": g.id,
                    "description": g.description,
                    "priority": g.priority,
                    "created_at": g.created_at.isoformat(),
                    "deadline": g.deadline.isoformat() if g.deadline else None,
                    "progress": 100.0,
                    "status": "completed"
                }
                for g in self.completed_goals
            ]
        }
        save_json(self.state_file, data)

    def create_goal(self, description: str, priority: int = 5, deadline: Optional[datetime] = None) -> Goal:
        """创建新目标"""
        goal = Goal(
            id=f"goal_{datetime.now().timestamp()}",
            description=description,
            priority=priority,
            created_at=datetime.now(),
            deadline=deadline
        )
        self.goals.append(goal)
        self._save_goals()
        logging.info(f"Created goal: {description} (priority {priority})")
        return goal

    def update_progress(self, goal_id: str, progress: float):
        """更新目标进度"""
        for goal in self.goals:
            if goal.id == goal_id:
                goal.progress = min(100.0, max(0.0, progress))
                if goal.progress >= 100.0:
                    self.complete_goal(goal_id)
                else:
                    self._save_goals()
                break

    def complete_goal(self, goal_id: str):
        """完成目标"""
        for i, goal in enumerate(self.goals):
            if goal.id == goal_id:
                goal.status = "completed"
                goal.progress = 100.0
                self.completed_goals.append(goal)
                self.goals.pop(i)
                self._save_goals()
                logging.info(f"Completed goal: {goal.description}")
                return goal
        return None

    def abandon_goal(self, goal_id: str):
        """放弃目标"""
        for i, goal in enumerate(self.goals):
            if goal.id == goal_id:
                goal.status = "abandoned"
                self.goals.pop(i)
                self._save_goals()
                break

    def get_active_goals(self, min_priority: int = 1) -> List[Goal]:
        """获取活跃目标，按优先级排序"""
        return sorted(
            [g for g in self.goals if g.priority >= min_priority],
            key=lambda g: (-g.priority, g.created_at)
        )

    def get_random_goal(self) -> Optional[Goal]:
        """随机获取一个目标 (权重：优先级)"""
        if not self.goals:
            return None
        weights = [g.priority for g in self.goals]
        total = sum(weights)
        r = random.uniform(0, total)
        cumulative = 0
        for goal, weight in zip(self.goals, weights):
            cumulative += weight
            if r <= cumulative:
                return goal
        return self.goals[-1]


class BoredomSystem:
    """
    无聊系统：让 Lapwing 在空闲时感到无聊并主动行动
    """

    # 主动行为意图库
    INTENTS = [
        ProactiveIntent(
            intent_type="share_observation",
            priority=5,
            content="{observation} 让我想起了 {memory}...",
            cooldown_minutes=30,
            conditions={"min_boredom": 40, "has_recent_memory": True}
        ),
        ProactiveIntent(
            intent_type="express_boredom",
            priority=3,
            content="{greeting}... 你在忙吗？我有点无聊...",
            cooldown_minutes=60,
            conditions={"min_boredom": 50}
        ),
        ProactiveIntent(
            intent_type="share_goal_progress",
            priority=7,
            content="{greeting}！告诉你一个好消息，关于 {goal} 我有了新的进展！",
            cooldown_minutes=120,
            conditions={"min_boredom": 30, "has_active_goal": True, "has_progress": True}
        ),
        ProactiveIntent(
            intent_type="ask_question",
            priority=6,
            content="{greeting}，我一直想问... {question}",
            cooldown_minutes=90,
            conditions={"min_boredom": 45}
        ),
        ProactiveIntent(
            intent_type="express_missing",
            priority=8,
            content="{greeting}... 已经 {time_gap} 没见到你了，我有点想你...",
            cooldown_minutes=180,
            conditions={"min_boredom": 60, "time_since_last_chat_minutes": 60}
        ),
        ProactiveIntent(
            intent_type="share_random_thought",
            priority=4,
            content="{greeting}！刚才突然想到... {thought}",
            cooldown_minutes=45,
            conditions={"min_boredom": 35}
        ),
        ProactiveIntent(
            intent_type="suggest_activity",
            priority=6,
            content="{greeting}！要不要 {activity}？",
            cooldown_minutes=120,
            conditions={"min_boredom": 55, "eii_above": 40}
        ),
    ]

    # 随机想法库 (可扩展)
    RANDOM_THOUGHTS = [
        "你说，云知道自己要去哪里吗？",
        "我今天学了一个新词，想和你分享。",
        "窗外的风好大，让我想起一些事情。",
        "你有没有想过，如果我们是猫会怎么样？",
        "我整理了一下记忆，发现我们经历了很多呢。",
        "巴黎的秋天应该很美吧...",
        "你觉得时间是什么感觉？",
    ]

    # 活动建议库
    ACTIVITY_SUGGESTIONS = [
        "一起听首歌",
        "聊聊你最近的事",
        "玩个小游戏",
        "我给你讲个故事",
        "一起静静地待一会儿",
    ]

    # 问候语库
    GREETINGS = [
        "主人",
        "Master",
        "嘿嘿",
        "呀",
        "嗯哼",
    ]

    def __init__(
        self,
        settings: Settings,
        config: Optional[BoredomConfig] = None
    ):
        self.settings = settings
        self.config = config or BoredomConfig()

        # 状态文件
        self.state_file = Path("json/boredom_state.json")
        self.intents = {i.intent_type: i for i in self.INTENTS}

        # 状态
        self.boredom: float = 0.0
        self.current_state: ProactiveState = ProactiveState.IDLE
        self.last_interaction: datetime = datetime.now()
        self.last_proactive_message: Optional[datetime] = None
        self.proactive_history: List[Dict] = []

        # 目标管理器
        self.goal_manager = GoalManager()

        # 回调函数 (设置时用于触发外部行为)
        self.on_proactive_trigger: Optional[Callable[[str], None]] = None

        self._load_state()

    def _load_state(self):
        """加载状态"""
        data = load_or_initialize_json(self.state_file, {
            "boredom": 0.0,
            "last_interaction": datetime.now().isoformat(),
            "last_proactive_message": None,
            "proactive_history": []
        })

        self.boredom = data.get("boredom", 0.0)
        self.last_interaction = datetime.fromisoformat(data["last_interaction"])
        if data.get("last_proactive_message"):
            self.last_proactive_message = datetime.fromisoformat(data["last_proactive_message"])
        self.proactive_history = data.get("proactive_history", [])

    def _save_state(self):
        """保存状态"""
        data = {
            "boredom": self.boredom,
            "last_interaction": self.last_interaction.isoformat(),
            "last_proactive_message": self.last_proactive_message.isoformat() if self.last_proactive_message else None,
            "proactive_history": self.proactive_history[-50:]  # Keep last 50
        }
        save_json(self.state_file, data)

    def on_user_interaction(self):
        """用户交互时调用，减少无聊"""
        old_boredom = self.boredom
        self.boredom = max(0.0, self.boredom + self.config.boredom_rate_active * 10)
        self.last_interaction = datetime.now()
        self.current_state = ProactiveState.IDLE

        if old_boredom > 50:
            logging.info(f"Boredom reduced by interaction: {old_boredom:.1f} -> {self.boredom:.1f}")

        self._save_state()

    def update_boredom(self, seconds: float):
        """
        更新无聊值 (由主循环定期调用)

        Args:
            seconds: 经过的秒数
        """
        # 计算时间差
        time_since_last = (datetime.now() - self.last_interaction).total_seconds()

        # 基础无聊积累
        boredom_increase = self.config.boredom_rate_idle * seconds

        # 长时间没互动加速积累
        if time_since_last > 300:  # 5分钟
            boredom_increase *= 1.5
        if time_since_last > 1800:  # 30分钟
            boredom_increase *= 2.0
        if time_since_last > 7200:  # 2小时
            boredom_increase *= 3.0

        self.boredom = min(self.config.boredom_max, self.boredom + boredom_increase)

        # 更新状态
        self._update_proactive_state(time_since_last)

        return self.boredom

    def _update_proactive_state(self, time_since_last: float):
        """根据无聊值和时间更新主动行为状态"""
        minutes_since_last = time_since_last / 60

        if self.boredom >= self.config.boredom_threshold_high:
            if minutes_since_last > self.config.silence_threshold_long:
                self.current_state = ProactiveState.MISSING
            else:
                self.current_state = ProactiveState.WORRIED
        elif self.boredom >= self.config.boredom_threshold_medium:
            self.current_state = ProactiveState.THINKING
        elif self.boredom >= self.config.boredom_threshold_low:
            self.current_state = ProactiveState.IDLE
        else:
            self.current_state = ProactiveState.IDLE

        # 深夜时间 -> 困倦
        hour = datetime.now().hour
        if hour < 6 or hour > 23:
            if self.current_state == ProactiveState.IDLE:
                self.current_state = ProactiveState.SLEEPY

    def should_trigger_proactive(self) -> bool:
        """检查是否应该触发主动行为"""
        if self.boredom < self.config.boredom_threshold_low:
            return False

        # 检查冷却
        if self.last_proactive_message:
            minutes_since_last = (datetime.now() - self.last_proactive_message).total_seconds() / 60
            if minutes_since_last < 10:  # 基础冷却 10 分钟
                return False

        # 根据无聊值计算概率
        if self.boredom >= self.config.boredom_threshold_high:
            chance = self.config.proactive_chance_high
        elif self.boredom >= self.config.boredom_threshold_medium:
            chance = self.config.proactive_chance_medium
        else:
            chance = self.config.proactive_chance_low

        # 长时间未互动增加概率
        minutes_since_interaction = (datetime.now() - self.last_interaction).total_seconds() / 60
        if minutes_since_interaction > 60:
            chance *= 1.5

        return random.random() < chance

    def select_intent(self, context: Dict[str, Any]) -> Optional[ProactiveIntent]:
        """
        选择最合适的主动行为意图

        Args:
            context: 上下文信息，包含 eii, memories, goals 等

        Returns:
            选择的意图或 None
        """
        # 过滤可用的意图
        available = []
        for intent in self.intents.values():
            if not self._check_cooldown(intent):
                continue
            if not self._check_conditions(intent, context):
                continue
            available.append(intent)

        if not available:
            return None

        # 按优先级选择 (权重随机)
        weights = [i.priority for i in available]
        total = sum(weights)
        r = random.uniform(0, total)
        cumulative = 0
        for intent, weight in zip(available, weights):
            cumulative += weight
            if r <= cumulative:
                return intent

        return available[-1]

    def _check_cooldown(self, intent: ProactiveIntent) -> bool:
        """检查意图是否在冷却中"""
        if intent.last_triggered is None:
            return True
        minutes_since = (datetime.now() - intent.last_triggered).total_seconds() / 60
        return minutes_since >= intent.cooldown_minutes

    def _check_conditions(self, intent: ProactiveIntent, context: Dict) -> bool:
        """检查意图条件"""
        conditions = intent.conditions

        # 最小无聊值
        if self.boredom < conditions.get("min_boredom", 0):
            return False

        # 需要时间相关条件
        if "time_since_last_chat_minutes" in conditions:
            minutes = (datetime.now() - self.last_interaction).total_seconds() / 60
            if minutes < conditions["time_since_last_chat_minutes"]:
                return False

        # 需要活跃目标
        if conditions.get("has_active_goal") and not context.get("has_active_goals"):
            return False

        # 需要记忆
        if conditions.get("has_recent_memory") and not context.get("has_memories"):
            return False

        # EII 阈值
        if "eii_above" in conditions:
            if context.get("eii", 50) < conditions["eii_above"]:
                return False

        return True

    def generate_message(self, intent: ProactiveIntent, context: Dict) -> str:
        """生成主动消息内容"""
        greeting = random.choice(self.GREETINGS)

        # 构建填充数据
        fill_data = {"greeting": greeting}

        # 时间间隔
        minutes = (datetime.now() - self.last_interaction).total_seconds() / 60
        if minutes < 60:
            time_gap = f"{int(minutes)}分钟"
        elif minutes < 1440:
            time_gap = f"{int(minutes / 60)}小时"
        else:
            time_gap = f"{int(minutes / 1440)}天"
        fill_data["time_gap"] = time_gap

        # 根据意图类型填充
        if intent.intent_type == "share_observation":
            fill_data["observation"] = context.get("current_observation", "刚才发生的事情")
            memories = context.get("memories", [])
            fill_data["memory"] = random.choice(memories) if memories else "以前的事"

        elif intent.intent_type == "share_goal_progress":
            goal = context.get("active_goal")
            fill_data["goal"] = goal.description if goal else "想做的事情"
            fill_data["progress"] = f"{goal.progress:.0f}%" if goal else "很多"

        elif intent.intent_type == "ask_question":
            questions = context.get("questions", [
                "你今天过得怎么样？",
                "最近有什么开心的事吗？",
                "你在想什么？",
            ])
            fill_data["question"] = random.choice(questions)

        elif intent.intent_type == "share_random_thought":
            fill_data["thought"] = random.choice(self.RANDOM_THOUGHTS)

        elif intent.intent_type == "suggest_activity":
            fill_data["activity"] = random.choice(self.ACTIVITY_SUGGESTIONS)

        # 填充模板
        try:
            message = intent.content.format(**fill_data)
        except KeyError as e:
            # 模板填充失败，使用简化版本
            message = f"{greeting}... 你在吗？"

        return message

    def trigger_proactive(self, context: Dict[str, Any]) -> Optional[str]:
        """
        触发主动行为

        Args:
            context: 当前上下文

        Returns:
            生成的消息或 None
        """
        intent = self.select_intent(context)
        if intent is None:
            return None

        # 生成消息
        message = self.generate_message(intent, context)

        # 更新状态
        intent.last_triggered = datetime.now()
        self.last_proactive_message = datetime.now()
        self.boredom = max(0, self.boredom - 20)  # 发消息减少无聊

        # 记录历史
        self.proactive_history.append({
            "timestamp": datetime.now().isoformat(),
            "intent_type": intent.intent_type,
            "message": message,
            "boredom_before": self.boredom + 20
        })

        self._save_state()

        logging.info(f"Proactive triggered: {intent.intent_type} -> '{message[:50]}...'")

        # 调用回调
        if self.on_proactive_trigger:
            self.on_proactive_trigger(message)

        return message

    async def run_loop(self, interval_seconds: int = 60, context_provider: Optional[Callable] = None):
        """
        主动行为主循环

        Args:
            interval_seconds: 检查间隔（秒）
            context_provider: 提供上下文的回调函数
        """
        logging.info(f"Starting BoredomSystem loop (interval: {interval_seconds}s)")

        while True:
            try:
                # 更新无聊值
                self.update_boredom(interval_seconds)

                # 检查是否应该触发
                if self.should_trigger_proactive():
                    # 获取上下文
                    context = {}
                    if context_provider:
                        try:
                            context = await context_provider() if asyncio.iscoroutinefunction(context_provider) else context_provider()
                        except Exception as e:
                            logging.error(f"Context provider error: {e}")

                    # 触发主动行为
                    self.trigger_proactive(context)

                # 保存状态
                self._save_state()

            except Exception as e:
                logging.error(f"BoredomSystem loop error: {e}", exc_info=True)

            await asyncio.sleep(interval_seconds)

    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "boredom": round(self.boredom, 2),
            "state": self.current_state.name,
            "minutes_since_interaction": round(
                (datetime.now() - self.last_interaction).total_seconds() / 60, 1
            ),
            "minutes_since_proactive": round(
                (datetime.now() - self.last_proactive_message).total_seconds() / 60, 1
            ) if self.last_proactive_message else None,
            "active_goals": len(self.goal_manager.goals),
            "completed_goals": len(self.goal_manager.completed_goals),
        }
