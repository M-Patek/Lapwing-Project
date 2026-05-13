"""
Lapwing Core - AI Character with Emotional Intelligence
Main orchestrator for conversation, emotion tracking, and memory management.
Includes Proactive Behavior, Weighted Memory, and Dreaming systems.
"""

import re
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any
from jinja2 import Environment, FileSystemLoader

from settings import Settings
from memory_weighted import WeightedMemoryManager, MemoryConfig
from llm_provider import MultiProviderManager
from world_events import WorldStateUpdater
from proactive_system import BoredomSystem, BoredomConfig
from dreaming_system import DreamingSystem, DreamingConfig
from event_bus import (
    get_event_bus,
    emit_eii_changed,
    emit_memory_added,
    emit_proactive_triggered,
)
from utils import safe_json_loads, load_or_initialize_json, save_json


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging with file and console handlers."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "lapwing.log"

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if logger.handlers:
        logger.handlers.clear()

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    ch.setFormatter(formatter)
    logger.addHandler(ch)


class EmotionalState:
    """Tracks Lapwing's emotional state."""

    def __init__(self, baseline: float = 53.0):
        self.eii = baseline
        self.foundation = baseline
        self.baseline = baseline

    def update(self, impact: float) -> None:
        if impact < 0:
            impact *= 1 - (self.foundation / 200)
        self.eii += impact
        self.eii += (self.baseline - self.eii) * 0.05
        self.eii = max(0.0, min(100.0, self.eii))
        self.foundation += (self.eii - self.foundation) * 0.01

    def get_eii(self) -> float:
        return round(self.eii, 2)


class Lapwing:
    """
    Main Lapwing character class.
    Orchestrates conversation, emotional tracking, memory systems,
    proactive behavior, and dreaming.
    """

    def __init__(self):
        logging.info("Waking Lapwing's soul...")

        # Settings
        self.settings = Settings()

        # Event Bus
        self.event_bus = get_event_bus()

        # Multi-provider LLM Manager (replaces ApiClientManager)
        self.api_manager = MultiProviderManager(self.settings)

        # Memory Manager (Weighted)
        self.memory_manager = WeightedMemoryManager(
            self.settings, self.api_manager, MemoryConfig()
        )

        # Emotional State
        self.emotional_state = EmotionalState(self.settings.EII_BASELINE)

        # World State Updater
        # World State Updater
        self.world_updater = WorldStateUpdater(self.settings, self.api_manager)

        # Proactive Behavior System (NEW)
        self.proactive_system = BoredomSystem(self.settings, BoredomConfig())
        self.proactive_system.on_proactive_trigger = self._on_proactive_trigger

        # Dreaming System (NEW)
        self.dreaming_system = DreamingSystem(
            self.settings, self.api_manager, DreamingConfig()
        )

        # Jinja2 Templates
        self.jinja_env = Environment(
            loader=FileSystemLoader("prompts"), autoescape=True
        )
        self.cot_template = self.jinja_env.get_template("cot_prompt.jinja2")
        self.context_template = self.jinja_env.get_template("base_context.jinja2")

        # State
        self.lapwing_state = load_or_initialize_json(self.settings.STATE_FILE, {})
        self.user_tz: Optional[ZoneInfo] = self._detect_user_timezone()

        # Proactive message queue
        self._proactive_messages: List[str] = []

        # Load prompts
        self._load_prompts()

        logging.info("Lapwing is awake and ready.")

    def _on_proactive_trigger(self, message: str):
        """Callback when proactive system triggers a message"""
        self._proactive_messages.append(message)
        logging.info(f"Proactive message queued: {message[:50]}...")

        # Emit event for WebSocket broadcast
        asyncio.create_task(
            emit_proactive_triggered(message, "unknown", "proactive_system")
        )

    def get_pending_proactive_messages(self) -> List[str]:
        """Get and clear pending proactive messages"""
        messages = self._proactive_messages.copy()
        self._proactive_messages.clear()
        return messages

    def _detect_user_timezone(self) -> Optional[ZoneInfo]:
        """Detect user's local timezone."""
        try:
            return datetime.now().astimezone().tzinfo
        except Exception:
            return None

    def _load_prompts(self) -> None:
        """Load persona and world lore from files."""
        try:
            prompts_dir = Path("prompts")

            world_lore_path = prompts_dir / "world_lore.txt"
            if world_lore_path.exists():
                self.settings.LAPWING_WORLD_LORE = world_lore_path.read_text(
                    encoding="utf-8"
                )

            persona_path = prompts_dir / "persona.txt"
            if persona_path.exists():
                self.settings.LAPWING_PERSONA_PROMPT = persona_path.read_text(
                    encoding="utf-8"
                )

            logging.info("Prompt templates loaded successfully.")

        except FileNotFoundError as e:
            logging.critical(f"Fatal: Prompt file not found: {e}")
            raise

    async def initialize(self):
        """Async initialization."""
        await self.memory_manager.build_style_index_async()
        await self._handle_session_start()

    async def start_background_tasks(self):
        """Start all background loops."""
        # Start event bus
        await self.event_bus.start()

        # World updater
        asyncio.create_task(
            self.world_updater.run_loop(interval_minutes=15), name="world_updater"
        )

        # Proactive behavior loop
        asyncio.create_task(
            self.proactive_system.run_loop(
                interval_seconds=60, context_provider=self._get_proactive_context
            ),
            name="proactive_system",
        )

        # Dreaming loop
        asyncio.create_task(
            self.dreaming_system.run_dream_loop(
                memory_provider=self._get_dream_memories,
                eii_provider=lambda: self.emotional_state.get_eii(),
                interval_minutes=5,
            ),
            name="dreaming_system",
        )

        logging.info("All background tasks started")

    async def _get_proactive_context(self) -> Dict[str, Any]:
        """Provide context for proactive system"""
        return {
            "eii": self.emotional_state.get_eii(),
            "has_memories": len(self.memory_manager.long_term_memories) > 0,
            "has_active_goals": len(
                self.proactive_system.goal_manager.get_active_goals()
            )
            > 0,
            "active_goal": self.proactive_system.goal_manager.get_random_goal(),
            "memories": list(
                self.memory_manager.short_term_memory.get("recent_events", [])
            )[-5:],
            "questions": [
                "今天有什么让你开心的事吗？",
                "你在想什么呢？",
                "有什么想和我分享的吗？",
                "最近过得怎么样？",
            ],
        }

    def _get_dream_memories(self) -> List[Dict]:
        """Provide memories for dreaming system"""
        # Convert WeightedMemory to dict format
        memories = []
        for mem_id, mem in list(self.memory_manager.long_term_memories.items())[-20:]:
            memories.append(
                {
                    "id": mem_id,
                    "content": mem.content,
                    "eii_snapshot": mem.eii_snapshot,
                    "emotional_intensity": mem.emotional_intensity,
                    "created_at": mem.created_at.isoformat(),
                }
            )
        return memories

    async def _analyze_emotional_impact(self, user_input: str) -> float:
        if not user_input.strip():
            return 0.0

        prompt = f'''Analyze the emotional impact of this sentence on Lapwing, who loves her master.
Rate from -10 (very negative) to +10 (very positive).

Input: "{user_input}"

Return only a number between -10 and +10.'''

        try:
            response = await self.api_manager.scene_client.generate_content(prompt)
            numbers = re.findall(r"-?\d+\.?\d*", response)
            if numbers:
                impact = float(numbers[0])
                return max(-10.0, min(10.0, impact))
            return 0.0
        except Exception as e:
            logging.error(f"Emotional impact analysis failed: {e}")
            return 0.0

    async def _extract_memories(
        self, user_input: str, lapwing_response: str
    ) -> Optional[dict]:
        prompt = f'''From the conversation, extract key information worth remembering:
Master's preferences, dislikes, or significant shared events.

Conversation:
Master: "{user_input}"
Lapwing: "{lapwing_response}"

Output JSON format:
{{"new_preferences": [], "new_dislikes": [], "new_shared_memories": []}}

Return empty arrays if nothing significant.'''

        try:
            response = await self.api_manager.scene_client.generate_content(prompt)
            return safe_json_loads(response, {})
        except Exception as e:
            logging.error(f"Memory extraction failed: {e}")
            return None

    async def _stage_memory(self, user_input: str, lapwing_response: str) -> None:
        extracted = await self._extract_memories(user_input, lapwing_response)

        if not extracted or not any(v for v in extracted.values() if v):
            return

        # Add to weighted memory system with emotional metadata
        if extracted.get("new_shared_memories"):
            for mem in extracted["new_shared_memories"]:
                self.memory_manager.add_weighted_memory(
                    content=mem,
                    eii_snapshot=self.emotional_state.get_eii(),
                    emotional_intensity=abs(
                        self.emotional_state.eii - self.emotional_state.baseline
                    ),
                )
                # Emit event
                await emit_memory_added(
                    mem, self.emotional_state.get_eii(), "memory_system"
                )

        # Also stage for traditional consolidation
        staging_data = load_or_initialize_json(
            self.settings.STAGING_FILE, {"potential_memories": []}
        )

        memory_entry = {
            "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "context": f"When Master said '{user_input}'",
            "extracted_info": extracted,
            "eii_snapshot": self.emotional_state.get_eii(),
        }

        staging_data["potential_memories"].append(memory_entry)
        save_json(self.settings.STAGING_FILE, staging_data)
        logging.info(
            f"Staged new memory: {len(staging_data['potential_memories'])} total"
        )

    async def _handle_session_start(self) -> str:
        self.lapwing_state = load_or_initialize_json(self.settings.STATE_FILE, {})

        if "eii" in self.lapwing_state:
            self.emotional_state.eii = self.lapwing_state.get(
                "eii", self.settings.EII_BASELINE
            )
        if "emotional_foundation" in self.lapwing_state:
            self.emotional_state.foundation = self.lapwing_state.get(
                "emotional_foundation", self.settings.EII_BASELINE
            )

        # Record activity for proactive system
        self.proactive_system.on_user_interaction()

        timeline = self.lapwing_state.get("current_timeline", {})
        return timeline.get("scene", "This is our first conversation.")

    def _save_session_state(self) -> None:
        old_eii = self.lapwing_state.get("eii", self.settings.EII_BASELINE)
        self.lapwing_state["eii"] = self.emotional_state.eii
        self.lapwing_state["emotional_foundation"] = self.emotional_state.foundation
        save_json(self.settings.STATE_FILE, self.lapwing_state)

        # Emit EII change event if significant
        if abs(old_eii - self.emotional_state.eii) > 5:
            asyncio.create_task(
                emit_eii_changed(
                    old_eii, self.emotional_state.get_eii(), "emotional_state"
                )
            )

    async def _build_context(self, user_input: str, memory_anchor: str) -> str:
        # Use weighted memory retrieval with current EII
        long_term_results = await self.memory_manager.retrieve_long_term_memories(
            query=user_input or " ", k=3, current_eii=self.emotional_state.get_eii()
        )
        long_term_memories = (
            " ".join([content for content, _ in long_term_results])
            if long_term_results
            else ""
        )

        style_exemplars = await self.memory_manager.retrieve_style_exemplars(
            user_input or " "
        )

        # Get relevant insights from dreaming system
        insights = self.dreaming_system.get_insights_for_context(
            user_input, self.emotional_state.get_eii(), n=2
        )
        insight_text = (
            "\n".join([f"- {i.content}" for i in insights]) if insights else ""
        )

        user_time_str = (
            datetime.now(self.user_tz).strftime("%Y-%m-%d %H:%M")
            if self.user_tz
            else "Unknown"
        )
        paris_time_str = datetime.now(self.settings.PARIS_TZ).strftime("%Y-%m-%d %H:%M")

        context_data = {
            "world_lore": self.settings.LAPWING_WORLD_LORE or "",
            "working_memory": self.memory_manager.get_formatted_working_memory(),
            "short_term_memory": self.memory_manager.get_formatted_short_term_memory(),
            "long_term_memory": long_term_memories,
            "insights": insight_text,
            "memory_anchor": memory_anchor,
            "paris_time": paris_time_str,
            "user_time": user_time_str,
            "timeline": self.lapwing_state.get("current_timeline", {}),
            "eii": f"{self.emotional_state.get_eii():.2f}",
            "persona_prompt": self.settings.LAPWING_PERSONA_PROMPT or "",
            "style_exemplars": style_exemplars,
        }

        return self.context_template.render(context_data)

    async def _generate_response(self, context: str, user_input: str) -> str:
        cot_prompt = self.cot_template.render(
            full_context=context, user_input=user_input
        )

        response = await self.api_manager.chat_client.chat(
            prompt=cot_prompt,
            temperature=self.settings.TEMPERATURE,
            max_tokens=self.settings.MAX_TOKENS,
        )

        match = re.search(
            r"<final_response>(.*?)</final_response>", response, re.DOTALL
        )
        if match:
            return match.group(1).strip()

        if "<final_response>" in response:
            return (
                response.split("<final_response>")[-1]
                .replace("</final_response>", "")
                .strip()
            )

        return response.strip()

    async def get_response(self, user_input: str) -> str:
        try:
            # Update proactive system on interaction
            self.proactive_system.on_user_interaction()

            impact = await self._analyze_emotional_impact(user_input)
            self.emotional_state.update(impact)

            input_for_model = (
                user_input
                if user_input.strip()
                else "[Master is silent, just looking at you quietly.]"
            )

            memory_anchor = await self._handle_session_start()
            context = await self._build_context(user_input, memory_anchor)
            response_text = await self._generate_response(context, input_for_model)

            if user_input.strip():
                self.memory_manager.add_to_working_memory(user_input, response_text)
                await self._stage_memory(user_input, response_text)

            self._save_session_state()

            return response_text

        except Exception as e:
            logging.error(f"Error generating response: {e}", exc_info=True)
            return "......I seem to have gotten a little distracted."

    async def get_stats(self) -> dict:
        """Get comprehensive statistics."""
        return {
            "emotional_state": {
                "eii": self.emotional_state.get_eii(),
                "foundation": round(self.emotional_state.foundation, 2),
            },
            "memory": self.memory_manager.get_stats(),
            "proactive": self.proactive_system.get_status(),
            "dreaming": self.dreaming_system.get_stats(),
            "world_state": self.lapwing_state.get("current_timeline", {}),
        }

    async def create_goal(self, description: str, priority: int = 5) -> str:
        """Create a new goal for Lapwing"""
        goal = self.proactive_system.goal_manager.create_goal(description, priority)
        return f"Goal created: {goal.description} (priority: {priority})"

    async def get_goals(self) -> List[Dict]:
        """Get active goals"""
        goals = self.proactive_system.goal_manager.get_active_goals()
        return [
            {
                "id": g.id,
                "description": g.description,
                "priority": g.priority,
                "progress": g.progress,
                "created_at": g.created_at.isoformat(),
            }
            for g in goals
        ]
