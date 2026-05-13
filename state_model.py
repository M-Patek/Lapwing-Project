from typing import List
from pydantic import BaseModel, Field

class Timeline(BaseModel):
    scene: str = "Waking up."
    next_intention: str = "Thinking about the day."
    previous_event: str = "A quiet moment."

class PADState(BaseModel):
    p: float = 0.6
    a: float = 0.3
    d: float = 0.7

class LapwingState(BaseModel):
    pad_emotional_state: PADState = Field(default_factory=PADState)
    current_timeline: Timeline = Field(default_factory=Timeline)
    energy: float = 1.0  # Range 0.0 to 1.0
    hunger: float = 0.0  # Range 0.0 to 1.0
    last_world_update_timestamp: str = ""
    last_interaction_timestamp: str = ""
    long_term_plans: List[str] = Field(default_factory=list)
    energy_conflict_counter: int = 0
    hunger_conflict_counter: int = 0
    passivity_counter: int = 0
