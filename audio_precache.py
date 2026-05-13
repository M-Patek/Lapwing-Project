"""
Audio Pre-caching System
Pre-generates common phrases to reduce latency.
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta

from tts_client import LapwingTTS, EmotionPreset


@dataclass
class PreCacheConfig:
    """Configuration for pre-caching"""
    # Common phrases to pre-cache
    greetings: List[str] = None
    farewells: List[str] = None
    affirmations: List[str] = None
    thinking_phrases: List[str] = None

    # Emotions to pre-cache for each phrase
    emotions: List[str] = None

    # Cache expiration (days)
    cache_expiry_days: int = 7

    # Max concurrent generation
    max_concurrent: int = 2

    def __post_init__(self):
        if self.greetings is None:
            self.greetings = [
                "你好呀~",
                "早上好！",
                "晚上好~",
                "好久不见！",
                "欢迎回来~",
            ]
        if self.farewells is None:
            self.farewells = [
                "再见~",
                "晚安~",
                "一路顺风！",
                "记得想我哦~",
            ]
        if self.affirmations is None:
            self.affirmations = [
                "好的~",
                "明白了！",
                "嗯嗯~",
                "是的呢~",
                "我知道了~",
            ]
        if self.thinking_phrases is None:
            self.thinking_phrases = [
                "让我想想...",
                "嗯...",
                "这个嘛...",
                "让我考虑一下...",
            ]
        if self.emotions is None:
            self.emotions = ["neutral", "happy", "calm"]


class AudioPreCache:
    """
    Pre-caches common TTS phrases to reduce latency.

    Usage:
        cache = AudioPreCache(tts_client)
        await cache.initialize()  # Pre-generate all phrases
        await cache.warm_up()      # Ensure cache is ready
    """

    def __init__(self, tts_client: LapwingTTS, config: PreCacheConfig = None):
        self.tts = tts_client
        self.config = config or PreCacheConfig()
        self._cache_status: Dict[str, datetime] = {}  # path -> last_accessed
        self._preloading = False

    async def initialize(self):
        """Pre-generate all common phrases"""
        if self._preloading:
            return

        self._preloading = True
        logging.info("[AudioPreCache] Starting pre-cache initialization...")

        # Collect all phrases
        all_phrases = []
        for category in [self.config.greetings, self.config.farewells,
                        self.config.affirmations, self.config.thinking_phrases]:
            all_phrases.extend(category)

        # Generate with rate limiting
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        async def cache_phrase(phrase: str, emotion: str):
            async with semaphore:
                try:
                    # Map emotion string to preset
                    try:
                        preset = EmotionPreset(emotion)
                    except ValueError:
                        preset = EmotionPreset.NEUTRAL

                    # Generate audio
                    path = await self.tts.client.synthesize(
                        text=phrase,
                        emotion_preset=preset,
                        use_cache=True
                    )

                    self._cache_status[str(path)] = datetime.now()
                    logging.debug(f"[AudioPreCache] Cached: {phrase} ({emotion})")

                except Exception as e:
                    logging.error(f"[AudioPreCache] Failed to cache '{phrase}': {e}")

        # Create tasks
        tasks = []
        for phrase in all_phrases:
            for emotion in self.config.emotions:
                tasks.append(cache_phrase(phrase, emotion))

        # Run all tasks
        await asyncio.gather(*tasks, return_exceptions=True)

        self._preloading = False
        logging.info(f"[AudioPreCache] Pre-cached {len(tasks)} audio files")

    async def warm_up(self):
        """
        Ensure cache is ready by preloading if needed.
        Call this periodically (e.g., on startup or hourly).
        """
        if not self._cache_status:
            await self.initialize()

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            "cached_files": len(self._cache_status),
            "last_preload": max(self._cache_status.values()) if self._cache_status else None,
            "is_preloading": self._preloading,
        }

    async def cleanup_expired(self):
        """Remove expired cache entries"""
        expiry = timedelta(days=self.config.cache_expiry_days)
        now = datetime.now()

        expired = [
            path for path, last_access in self._cache_status.items()
            if now - last_access > expiry
        ]

        for path in expired:
            try:
                Path(path).unlink(missing_ok=True)
                del self._cache_status[path]
            except Exception as e:
                logging.warning(f"[AudioPreCache] Failed to remove {path}: {e}")

        if expired:
            logging.info(f"[AudioPreCache] Cleaned up {len(expired)} expired files")

    async def run_maintenance_loop(self, interval_hours: int = 1):
        """Run periodic cache maintenance"""
        while True:
            await asyncio.sleep(interval_hours * 3600)
            await self.cleanup_expired()
            await self.warm_up()
