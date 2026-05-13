from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
from zoneinfo import ZoneInfo


class Settings(BaseSettings):
    # Provider selection
    LLM_PROVIDER: str = "deepseek"

    # DeepSeek Configuration (OpenAI compatible)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # OpenAI Configuration
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Anthropic Configuration
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"

    # Model Configuration
    CHAT_MODEL: str = "deepseek-v4-flash"
    SCENE_MODEL: str = "deepseek-v4-flash"

    # File Paths
    MEMORY_FILE: Path = Path("json/lapwing_memory.json")
    STAGING_FILE: Path = Path("json/staging_memory.json")
    SHORT_TERM_MEMORY_FILE: Path = Path("json/short_term_memory.json")
    STATE_FILE: Path = Path("json/lapwing_state.json")

    # Model Parameters
    TEMPERATURE: float = 0.95
    MAX_TOKENS: int = 4096

    # Thresholds and constants
    SIMILARITY_THRESHOLD: float = 0.9
    EII_BASELINE: int = 53

    # These will be loaded from external files
    LAPWING_WORLD_LORE: Optional[str] = None
    LAPWING_PERSONA_PROMPT: Optional[str] = None

    # Weather API Configuration
    WEATHER_API_URL: str = "https://api-open-meteo.com/v1/forecast"
    WEATHER_LATITUDE: float = 48.8566
    WEATHER_LONGITUDE: float = 2.3522
    PARIS_TZ: ZoneInfo = ZoneInfo("Europe/Paris")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
