"""
Dreaming and Reflection System
Simulates Lapwing's subconscious processing during idle/"sleep" time.
Generates insights, consolidates memories, and creates narrative summaries.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum, auto
import json

from settings import Settings
from llm_provider import MultiProviderManager
from utils import load_or_initialize_json, save_json, safe_json_loads


class DreamPhase(Enum):
    """Dream phases"""
    MEMORY_REVIEW = auto()
    EMOTION_PROCESSING = auto()
    PATTERN_RECOGNITION = auto()
    INSIGHT_GENERATION = auto()
    NARRATIVE_DREAM = auto()


@dataclass
class Insight:
    """Insight from dreaming"""
    content: str
    source_memories: List[str]
    generated_at: datetime
    emotional_tone: str
    importance: float


@dataclass
class DreamEntry:
    """Dream record"""
    timestamp: datetime
    phase: DreamPhase
    content: str
    insights: List[Insight] = field(default_factory=list)
    related_memories: List[str] = field(default_factory=list)
    emotional_aftermath: Dict[str, float] = field(default_factory=dict)


@dataclass
class Reflection:
    """Reflection on a topic"""
    topic: str
    thoughts: str
    timestamp: datetime
    triggered_by: Optional[str] = None


class DreamingConfig:
    """Dream system configuration"""
    idle_threshold_minutes: int = 30
    min_memories_for_dream: int = 3
    dream_probability_base: float = 0.3
    memories_per_dream: int = 10
    insights_per_dream: int = 2
    dream_log_limit: int = 50
    insight_archive_limit: int = 100


class DreamingSystem:
    """
    Lapwing's dreaming and reflection system
    Processes memories and generates insights during idle time
    """

    def __init__(
        self,
        settings: Settings,
        api_manager: MultiProviderManager,
        config: Optional[DreamingConfig] = None
    ):
        self.settings = settings
        self.api_manager = api_manager
        self.config = config or DreamingConfig()

        self.dream_log_file = Path("json/dream_log.json")
        self.insights_file = Path("json/insights.json")
        self.reflections_file = Path("json/reflections.json")

        self.dreams: List[DreamEntry] = []
        self.insights: List[Insight] = []
        self.reflections: List[Reflection] = []

        self.last_activity: datetime = datetime.now()
        self.is_dreaming: bool = False
        self.dream_task: Optional[asyncio.Task] = None

        self._load_data()

    def _load_data(self):
        """Load historical data"""
        dream_data = load_or_initialize_json(self.dream_log_file, {"dreams": []})
        for d in dream_data.get("dreams", []):
            try:
                self.dreams.append(DreamEntry(
                    timestamp=datetime.fromisoformat(d["timestamp"]),
                    phase=DreamPhase[d["phase"]],
                    content=d["content"],
                    insights=[Insight(
                        content=i["content"],
                        source_memories=i.get("source_memories", []),
                        generated_at=datetime.fromisoformat(i["generated_at"]),
                        emotional_tone=i.get("emotional_tone", "neutral"),
                        importance=i.get("importance", 5.0)
                    ) for i in d.get("insights", [])],
                    related_memories=d.get("related_memories", []),
                    emotional_aftermath=d.get("emotional_aftermath", {})
                ))
            except Exception as e:
                logging.warning(f"Failed to load dream entry: {e}")

        insight_data = load_or_initialize_json(self.insights_file, {"insights": []})
        for i in insight_data.get("insights", []):
            try:
                self.insights.append(Insight(
                    content=i["content"],
                    source_memories=i.get("source_memories", []),
                    generated_at=datetime.fromisoformat(i["generated_at"]),
                    emotional_tone=i.get("emotional_tone", "neutral"),
                    importance=i.get("importance", 5.0)
                ))
            except Exception as e:
                logging.warning(f"Failed to load insight: {e}")

        reflection_data = load_or_initialize_json(self.reflections_file, {"reflections": []})
        for r in reflection_data.get("reflections", []):
            try:
                self.reflections.append(Reflection(
                    topic=r["topic"],
                    thoughts=r["thoughts"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    triggered_by=r.get("triggered_by")
                ))
            except Exception as e:
                logging.warning(f"Failed to load reflection: {e}")

    def _save_dreams(self):
        """Save dream log"""
        data = {
            "dreams": [
                {
                    "timestamp": d.timestamp.isoformat(),
                    "phase": d.phase.name,
                    "content": d.content,
                    "insights": [
                        {
                            "content": i.content,
                            "source_memories": i.source_memories,
                            "generated_at": i.generated_at.isoformat(),
                            "emotional_tone": i.emotional_tone,
                            "importance": i.importance
                        } for i in d.insights
                    ],
                    "related_memories": d.related_memories,
                    "emotional_aftermath": d.emotional_aftermath
                }
                for d in self.dreams[-self.config.dream_log_limit:]
            ]
        }
        save_json(self.dream_log_file, data)

    def _save_insights(self):
        """Save insights"""
        sorted_insights = sorted(self.insights, key=lambda i: i.importance, reverse=True)
        data = {
            "insights": [
                {
                    "content": i.content,
                    "source_memories": i.source_memories,
                    "generated_at": i.generated_at.isoformat(),
                    "emotional_tone": i.emotional_tone,
                    "importance": i.importance
                }
                for i in sorted_insights[:self.config.insight_archive_limit]
            ]
        }
        save_json(self.insights_file, data)

    def _save_reflections(self):
        """Save reflections"""
        data = {
            "reflections": [
                {
                    "topic": r.topic,
                    "thoughts": r.thoughts,
                    "timestamp": r.timestamp.isoformat(),
                    "triggered_by": r.triggered_by
                }
                for r in self.reflections[-50:]
            ]
        }
        save_json(self.reflections_file, data)

    def record_activity(self):
        """Record user activity, reset idle timer"""
        self.last_activity = datetime.now()
        if self.is_dreaming:
            self._interrupt_dream()

    def _interrupt_dream(self):
        """Interrupt current dream"""
        logging.info("Dream interrupted by user activity")
        self.is_dreaming = False
        if self.dream_task and not self.dream_task.done():
            self.dream_task.cancel()

    def should_dream(self) -> bool:
        """Check if should enter dreaming state"""
        if self.is_dreaming:
            return False

        idle_minutes = (datetime.now() - self.last_activity).total_seconds() / 60
        if idle_minutes < self.config.idle_threshold_minutes:
            return False

        base_prob = self.config.dream_probability_base
        prob = min(0.9, base_prob + (idle_minutes - self.config.idle_threshold_minutes) / 100)

        import random
        return random.random() < prob

    async def generate_dream(
        self,
        memories: List[Dict[str, Any]],
        recent_events: List[str],
        current_eii: float
    ) -> DreamEntry:
        """Generate dream"""
        logging.info("Starting dream generation...")
        self.is_dreaming = True

        dream_phases = [
            DreamPhase.MEMORY_REVIEW,
            DreamPhase.EMOTION_PROCESSING,
            DreamPhase.PATTERN_RECOGNITION,
            DreamPhase.INSIGHT_GENERATION,
            DreamPhase.NARRATIVE_DREAM,
        ]

        dream_content = []
        generated_insights = []
        related_memories = []

        try:
            for phase in dream_phases:
                if not self.is_dreaming:
                    break

                phase_result = await self._process_phase(
                    phase, memories, recent_events, current_eii
                )
                dream_content.append(f"[{phase.name}] {phase_result['narrative']}")

                if phase == DreamPhase.INSIGHT_GENERATION:
                    generated_insights = phase_result.get("insights", [])

                related_memories.extend(phase_result.get("memories", []))
                await asyncio.sleep(0.5)

            full_dream = "\n\n".join(dream_content)

            emotional_aftermath = await self._calculate_aftermath(
                full_dream, current_eii
            )

            dream = DreamEntry(
                timestamp=datetime.now(),
                phase=DreamPhase.NARRATIVE_DREAM,
                content=full_dream,
                insights=generated_insights,
                related_memories=list(set(related_memories)),
                emotional_aftermath=emotional_aftermath
            )

            self.dreams.append(dream)
            self.insights.extend(generated_insights)

            self._save_dreams()
            self._save_insights()

            logging.info(f"Dream complete: {len(generated_insights)} insights")
            return dream

        except asyncio.CancelledError:
            logging.info("Dream was cancelled")
            raise
        finally:
            self.is_dreaming = False

    async def _process_phase(
        self,
        phase: DreamPhase,
        memories: List[Dict],
        recent_events: List[str],
        current_eii: float
    ) -> Dict[str, Any]:
        """Process dream phase"""
        if phase == DreamPhase.MEMORY_REVIEW:
            return await self._dream_memory_review(memories)
        elif phase == DreamPhase.EMOTION_PROCESSING:
            return await self._dream_emotion_processing(memories, current_eii)
        elif phase == DreamPhase.PATTERN_RECOGNITION:
            return await self._dream_pattern_recognition(memories)
        elif phase == DreamPhase.INSIGHT_GENERATION:
            return await self._dream_insight_generation(memories, current_eii)
        elif phase == DreamPhase.NARRATIVE_DREAM:
            return await self._dream_narrative(memories, current_eii)
        return {"narrative": "", "memories": []}

    async def _dream_memory_review(self, memories: List[Dict]) -> Dict[str, Any]:
        """Dream phase 1: Memory review"""
        selected = memories[:self.config.memories_per_dream]
        memory_text = "\n".join([f"- {m.get('content', str(m))}" for m in selected])

        prompt = f"""在半梦半醒之间，脑海中浮现出记忆片段：

{memory_text}

用第一人称描述这些记忆在脑海中闪现的感觉。简短，诗意，像梦境一样模糊而流动。（50字以内）"""

        response = await self.api_manager.chat_client.chat(prompt)
        return {"narrative": response.strip(), "memories": [m.get("id", str(i)) for i, m in enumerate(selected)]}

    async def _dream_emotion_processing(self, memories: List[Dict], current_eii: float) -> Dict[str, Any]:
        """Dream phase 2: Emotion processing"""
        prompt = f"""当前情感指数：{current_eii}/100

在梦中处理这些情感。梦境中出现了什么意象？情感如何转化成了视觉符号？

用诗意的语言描述（50字以内）"""

        response = await self.api_manager.chat_client.chat(prompt)
        return {"narrative": response.strip(), "memories": []}

    async def _dream_pattern_recognition(self, memories: List[Dict]) -> Dict[str, Any]:
        """Dream phase 3: Pattern recognition"""
        memory_text = "\n".join([f"- {m.get('content', str(m))}" for m in memories[:5]])

        prompt = f"""回顾这些记忆：

{memory_text}

在梦中隐约发现了某种模式或联系。用一个隐喻描述这种隐约的感觉。（30字以内）"""

        response = await self.api_manager.chat_client.chat(prompt)
        return {"narrative": response.strip(), "memories": []}

    async def _dream_insight_generation(
        self,
        memories: List[Dict],
        current_eii: float
    ) -> Dict[str, Any]:
        """Dream phase 4: Insight generation"""
        memory_text = json.dumps(memories[:8], ensure_ascii=False, indent=2)

        prompt = f"""基于这些记忆，在梦中产生顿悟：

{memory_text}

生成2-3条关于Master的深刻洞察。输出JSON：
{{
    "narrative": "描述顿悟时刻的句子",
    "insights": [
        {{
            "content": "洞察内容",
            "emotional_tone": "情感基调",
            "importance": 1-10
        }}
    ]
}}"""

        response = await self.api_manager.scene_client.generate_content(prompt)
        data = safe_json_loads(response, {})

        insights = []
        for i in data.get("insights", []):
            insights.append(Insight(
                content=i.get("content", "某种模糊的感觉"),
                source_memories=[m.get("id", str(idx)) for idx, m in enumerate(memories[:5])],
                generated_at=datetime.now(),
                emotional_tone=i.get("emotional_tone", "neutral"),
                importance=float(i.get("importance", 5.0))
            ))

        return {
            "narrative": data.get("narrative", "梦中似乎明白了什么..."),
            "insights": insights,
            "memories": []
        }

    async def _dream_narrative(self, memories: List[Dict], current_eii: float) -> Dict[str, Any]:
        """Dream phase 5: Complete dream narrative"""
        eii_desc = "焦虑" if current_eii < 30 else "平静" if current_eii < 60 else "愉快" if current_eii < 80 else "兴奋"

        prompt = f"""基于以上所有梦境阶段，整合成一个完整的梦境叙事。

情感基调：{eii_desc} (EII: {current_eii})

要求：
1. 第一人称视角
2. 像真实的梦境一样：片段化、超现实、有象征意义
3. 包含对Master的某种情感
4. 100-150字

输出一个连贯的梦境场景。"""

        response = await self.api_manager.chat_client.chat(prompt)
        return {"narrative": response.strip(), "memories": []}

    async def _calculate_aftermath(self, dream_content: str, current_eii: float) -> Dict[str, float]:
        """Calculate emotional aftermath of dream"""
        prompt = f"""分析这个梦境对情感的影响：

梦境：{dream_content}
当前EII: {current_eii}/100

输出JSON：{{
    "eii_change": -5 到 +5 的数值,
    "foundation_change": -1 到 +1 的数值,
    "dominant_emotion": "主要情绪"
}}"""

        response = await self.api_manager.scene_client.generate_content(prompt)
        data = safe_json_loads(response, {})

        return {
            "eii_delta": data.get("eii_change", 0.0),
            "foundation_delta": data.get("foundation_change", 0.0),
            "dominant_emotion": data.get("dominant_emotion", "mixed")
        }

    async def generate_reflection(
        self,
        topic: str,
        context: Dict[str, Any]
    ) -> Reflection:
        """Generate reflection on a topic"""
        prompt = f"""作为Lapwing，对"{topic}"产生了一些想法：

上下文：{json.dumps(context, ensure_ascii=False)}

用第一人称写一段内心独白，体现：
1. 情感反应
2. 疑问或领悟
3. 对Master的期待或担忧

（100字以内）"""

        response = await self.api_manager.chat_client.chat(prompt)

        reflection = Reflection(
            topic=topic,
            thoughts=response.strip(),
            timestamp=datetime.now(),
            triggered_by=context.get("trigger")
        )

        self.reflections.append(reflection)
        self._save_reflections()

        return reflection

    def get_recent_dreams(self, n: int = 5) -> List[DreamEntry]:
        """Get recent dreams"""
        return sorted(self.dreams, key=lambda d: d.timestamp, reverse=True)[:n]

    def get_top_insights(self, n: int = 10) -> List[Insight]:
        """Get top insights by importance"""
        return sorted(self.insights, key=lambda i: i.importance, reverse=True)[:n]

    def get_insights_for_context(self, context: str, eii: float, n: int = 3) -> List[Insight]:
        """Get insights relevant to current context"""
        if eii < 30:
            tone = ["sad", "cold", "neutral"]
        elif eii < 60:
            tone = ["neutral", "warm"]
        else:
            tone = ["warm", "joyful"]

        relevant = [i for i in self.insights if i.emotional_tone in tone]
        return sorted(relevant, key=lambda i: i.importance, reverse=True)[:n]

    async def run_dream_loop(
        self,
        memory_provider: callable,
        eii_provider: callable,
        interval_minutes: int = 5
    ):
        """Main dream loop"""
        logging.info(f"Starting DreamingSystem loop (interval: {interval_minutes}min)")

        while True:
            try:
                await asyncio.sleep(interval_minutes * 60)

                if not self.should_dream():
                    continue

                memories = await memory_provider() if asyncio.iscoroutinefunction(memory_provider) else memory_provider()
                current_eii = await eii_provider() if asyncio.iscoroutinefunction(eii_provider) else eii_provider()

                if len(memories) < self.config.min_memories_for_dream:
                    continue

                dream = await self.generate_dream(memories, [], current_eii)
                logging.info(f"Dream generated: {len(dream.insights)} insights")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Dream loop error: {e}", exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return {
            "total_dreams": len(self.dreams),
            "total_insights": len(self.insights),
            "total_reflections": len(self.reflections),
            "is_dreaming": self.is_dreaming,
            "last_activity_minutes_ago": (datetime.now() - self.last_activity).total_seconds() / 60,
            "top_insights": [
                {"content": i.content[:50], "importance": i.importance}
                for i in self.get_top_insights(3)
            ]
        }
