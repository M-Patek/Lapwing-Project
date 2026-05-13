"""Lapwing Agent - AI Character with Emotional Intelligence."""

from .lapwing_agent import LapwingAgent
from .emotional_state import EmotionalState
from .weighted_memory import WeightedMemoryManager, MemoryConfig
from .dreaming_system import DreamingSystem
from .proactive_system import BoredomSystem, BoredomConfig

__all__ = [
    "LapwingAgent",
    "EmotionalState",
    "WeightedMemoryManager",
    "MemoryConfig",
    "DreamingSystem",
    "BoredomSystem",
    "BoredomConfig",
]
