"""Emotional State Tracking for Lapwing Agent."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any


@dataclass
class EmotionalState:
    """Tracks Lapwing's emotional state with EII (Emotional Intensity Index)."""

    baseline: float = 53.0
    eii: float = field(default=53.0)  # Emotional Intensity Index 0-100
    foundation: float = field(default=53.0)
    last_update: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.eii == self.baseline:
            self.eii = self.baseline
        if self.foundation == self.baseline:
            self.foundation = self.baseline

    def update(self, impact: float) -> None:
        """Update emotional state based on impact (-10 to +10)."""
        # Negative impact is dampened by foundation
        if impact < 0:
            impact *= 1 - (self.foundation / 200)

        self.eii += impact

        # Gradual return to baseline
        self.eii += (self.baseline - self.eii) * 0.05

        # Clamp to valid range
        self.eii = max(0.0, min(100.0, self.eii))

        # Foundation slowly follows EII
        self.foundation += (self.eii - self.foundation) * 0.01
        self.last_update = datetime.now()

    def get_eii(self) -> float:
        """Get current EII value."""
        return round(self.eii, 2)

    def get_mood_description(self) -> str:
        """Get human-readable mood description."""
        eii = self.get_eii()
        if eii >= 80:
            return "ecstatic"
        elif eii >= 65:
            return "happy"
        elif eii >= 50:
            return "content"
        elif eii >= 35:
            return "melancholic"
        elif eii >= 20:
            return "sad"
        else:
            return "distressed"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize emotional state."""
        return {
            "eii": self.eii,
            "foundation": self.foundation,
            "baseline": self.baseline,
            "last_update": self.last_update.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmotionalState":
        """Deserialize emotional state."""
        state = cls(baseline=data.get("baseline", 53.0))
        state.eii = data.get("eii", state.baseline)
        state.foundation = data.get("foundation", state.baseline)
        if "last_update" in data:
            state.last_update = datetime.fromisoformat(data["last_update"])
        return state
