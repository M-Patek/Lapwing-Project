"""
Test suite for Lapwing
"""
import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime

from main import EmotionalState
from memory_weighted import TimeDecayCalculator, EmotionalWeightCalculator, WeightedMemory
from event_bus import EventBus, EventType, Event


class TestEmotionalState:
    """Tests for EmotionalState"""

    def test_initial_state(self):
        state = EmotionalState(baseline=50.0)
        assert state.eii == 50.0
        assert state.foundation == 50.0

    def test_positive_impact(self):
        state = EmotionalState(baseline=50.0)
        state.update(5.0)
        assert state.eii > 50.0
        assert state.eii <= 100.0

    def test_negative_impact(self):
        state = EmotionalState(baseline=50.0)
        state.update(-5.0)
        assert state.eii < 50.0
        assert state.eii >= 0.0

    def test_clamping(self):
        state = EmotionalState(baseline=50.0)
        state.update(100.0)
        assert state.eii <= 100.0
        state.update(-200.0)
        assert state.eii >= 0.0


class TestTimeDecayCalculator:
    """Tests for TimeDecayCalculator"""

    def test_decay_calculation(self):
        calc = TimeDecayCalculator(half_life_days=30.0)
        decay = calc.calculate_decay(30.0)  # 30 days
        assert 0.4 < decay < 0.6  # Should be around 0.5

    def test_weighted_decay(self):
        calc = TimeDecayCalculator()
        created = datetime.now()
        accessed = datetime.now()
        decay = calc.calculate_weighted_decay(created, accessed)
        assert 0 < decay <= 1.0


class TestEmotionalWeightCalculator:
    """Tests for EmotionalWeightCalculator"""

    def test_weight_calculation(self):
        calc = EmotionalWeightCalculator()
        weight = calc.calculate_weight(60.0, 60.0, 80.0)
        assert weight > 1.0  # Should be boosted

    def test_mood_mismatch(self):
        calc = EmotionalWeightCalculator()
        weight = calc.calculate_weight(20.0, 80.0, 50.0)
        assert weight < 1.5  # Should be reduced due to mismatch


class TestEventBus:
    """Tests for EventBus"""

    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        bus = EventBus()
        await bus.start()

        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.EII_CHANGED, handler)
        await bus.publish(EventType.EII_CHANGED, {"eii": 65.5})

        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0].data["eii"] == 65.5

        await bus.stop()

    @pytest.mark.asyncio
    async def test_decorator_subscription(self):
        bus = EventBus()
        await bus.start()

        received = []

        @bus.on(EventType.MEMORY_ADDED)
        async def handler(event: Event):
            received.append(event)

        await bus.publish(EventType.MEMORY_ADDED, {"content": "test"})
        await asyncio.sleep(0.1)

        assert len(received) == 1
        await bus.stop()


class TestWeightedMemory:
    """Tests for WeightedMemory"""

    def test_creation(self):
        mem = WeightedMemory(
            content="Test memory",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
            emotional_intensity=70.0,
            eii_snapshot=60.0
        )
        assert mem.content == "Test memory"
        assert mem.emotional_intensity == 70.0

    def test_serialization(self):
        mem = WeightedMemory(
            content="Test",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            last_accessed=datetime(2024, 1, 1, 12, 0, 0),
            emotional_intensity=50.0,
            eii_snapshot=50.0
        )
        data = mem.to_dict()
        assert data["content"] == "Test"
        assert "created_at" in data


# Integration tests
@pytest.mark.integration
class TestLapwingIntegration:
    """Integration tests"""

    @pytest.mark.asyncio
    async def test_emotional_response(self):
        """Test that emotional state affects responses"""
        # This would require mocking the API
        pass

    @pytest.mark.asyncio
    async def test_memory_retrieval(self):
        """Test memory retrieval with weights"""
        # This would require mocking embeddings
        pass
