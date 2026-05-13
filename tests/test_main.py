"""
Tests for Lapwing core functionality.
Run with: pytest tests/test_main.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from main import Lapwing, EmotionalState
from settings import Settings


# Mark all tests as asyncio
pytestmark = pytest.mark.asyncio


class TestEmotionalState:
    """Tests for EmotionalState class."""

    def test_initial_state(self):
        """Test emotional state initialization."""
        state = EmotionalState(baseline=50.0)
        assert state.eii == 50.0
        assert state.foundation == 50.0
        assert state.baseline == 50.0

    def test_positive_impact(self):
        """Test positive emotional impact."""
        state = EmotionalState(baseline=50.0)
        state.update(5.0)
        assert state.eii > 50.0
        assert state.eii <= 100.0

    def test_negative_impact(self):
        """Test negative emotional impact."""
        state = EmotionalState(baseline=50.0)
        state.update(-5.0)
        assert state.eii < 50.0
        assert state.eii >= 0.0

    def test_clamping(self):
        """Test EII clamping to valid range."""
        state = EmotionalState(baseline=50.0)

        # Test upper bound
        state.update(100.0)
        assert state.eii <= 100.0

        # Test lower bound
        state.update(-200.0)
        assert state.eii >= 0.0

    def test_get_eii(self):
        """Test EII getter returns rounded value."""
        state = EmotionalState(baseline=50.0)
        state.eii = 53.33333
        assert state.get_eii() == 53.33


class TestLapwing:
    """Tests for Lapwing class (requires mocking)."""

    @pytest.fixture
    def mock_lapwing(self, monkeypatch, tmp_path):
        """Create a mocked Lapwing instance for testing."""

        # Mock Settings
        mock_settings = MagicMock(spec=Settings)
        mock_settings.EII_BASELINE = 53.0
        mock_settings.LAPWING_WORLD_LORE = "Test lore"
        mock_settings.LAPWING_PERSONA_PROMPT = "Test persona"
        mock_settings.SHORT_TERM_MEMORY_FILE = tmp_path / "short_term.json"
        mock_settings.MEMORY_FILE = tmp_path / "memory.json"
        mock_settings.STAGING_FILE = tmp_path / "staging.json"
        mock_settings.STATE_FILE = tmp_path / "state.json"
        mock_settings.PARIS_TZ = None

        # Patch Settings constructor
        monkeypatch.setattr("main.Settings", lambda: mock_settings)

        # Mock API manager
        mock_api_manager = MagicMock()
        mock_api_manager.chat_client = AsyncMock()
        mock_api_manager.scene_client = AsyncMock()
        mock_api_manager.embedding_client = AsyncMock()

        # Patch ApiClientManager
        monkeypatch.setattr("main.ApiClientManager", lambda s: mock_api_manager)

        # Mock MemoryManager
        mock_memory = MagicMock()
        mock_memory.working_memory = []
        mock_memory.get_formatted_working_memory = MagicMock(
            return_value="Test working memory"
        )
        mock_memory.get_formatted_short_term_memory = MagicMock(
            return_value="Test short term"
        )
        mock_memory.retrieve_long_term_memories = AsyncMock(
            return_value="Test long term"
        )
        mock_memory.retrieve_style_exemplars = AsyncMock(return_value=[])
        mock_memory.build_style_index_async = AsyncMock()

        monkeypatch.setattr("main.MemoryManager", lambda *args, **kwargs: mock_memory)

        # Mock file operations
        monkeypatch.setattr("main.load_or_initialize_json", lambda *args: {})
        monkeypatch.setattr("main.Path.exists", lambda self: True)
        monkeypatch.setattr(
            "main.Path.read_text", lambda *args, **kwargs: "Test content"
        )

        # Create instance
        lapwing = Lapwing()
        lapwing.memory_manager = mock_memory
        lapwing.api_manager = mock_api_manager

        return lapwing, mock_api_manager, mock_memory

    async def test_analyze_emotional_impact_positive(self, mock_lapwing):
        """Test analyzing positive emotional impact."""
        lapwing, api_manager, _ = mock_lapwing

        # Mock scene client to return positive
        api_manager.scene_client.generate_content = AsyncMock(return_value="7.5")

        impact = await lapwing._analyze_emotional_impact("I love you!")
        assert impact > 0
        assert impact <= 10

    async def test_analyze_emotional_impact_negative(self, mock_lapwing):
        """Test analyzing negative emotional impact."""
        lapwing, api_manager, _ = mock_lapwing

        # Mock scene client to return negative
        api_manager.scene_client.generate_content = AsyncMock(return_value="-5.0")

        impact = await lapwing._analyze_emotional_impact("I hate you")
        assert impact < 0
        assert impact >= -10

    async def test_analyze_emotional_impact_empty(self, mock_lapwing):
        """Test empty input returns 0 impact."""
        lapwing, _, _ = mock_lapwing

        impact = await lapwing._analyze_emotional_impact("")
        assert impact == 0

    async def test_analyze_emotional_impact_fallback(self, mock_lapwing):
        """Test fallback on API error."""
        lapwing, api_manager, _ = mock_lapwing

        # Mock API failure
        api_manager.scene_client.generate_content = AsyncMock(
            side_effect=Exception("API error")
        )

        impact = await lapwing._analyze_emotional_impact("test")
        assert impact == 0  # Should return 0 on failure


class TestUtils:
    """Tests for utility functions."""

    def test_safe_json_loads_valid(self):
        """Test parsing valid JSON."""
        from utils import safe_json_loads

        result = safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_safe_json_loads_markdown(self):
        """Test parsing JSON in markdown."""
        from utils import safe_json_loads

        text = '```json\n{"key": "value"}\n```'
        result = safe_json_loads(text)
        assert result == {"key": "value"}

    def test_safe_json_loads_invalid(self):
        """Test invalid JSON returns default."""
        from utils import safe_json_loads

        result = safe_json_loads("not json", default=[])
        assert result == []

    def test_safe_json_loads_custom_default(self):
        """Test custom default value."""
        from utils import safe_json_loads

        result = safe_json_loads("invalid", default=None)
        assert result is None


class TestIntegration:
    """Integration tests (may require API keys)."""

    @pytest.mark.skip(reason="Requires API keys")
    async def test_full_conversation_flow(self):
        """Test a full conversation flow (requires real API)."""
        # This would test the full flow with real APIs
        pass
