"""
TTS Client for GPT SoVITS Integration
Provides text-to-speech synthesis with emotion mapping.
"""
import asyncio
import logging
import hashlib
import time
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import aiohttp


class EmotionPreset(Enum):
    """Emotion presets for GPT SoVITS voice synthesis."""
    SAD = "sad"           # EII 0-20: 悲伤/低落
    CALM = "calm"         # EII 20-40: 平静/思考
    NEUTRAL = "neutral"   # EII 40-60: 温和/日常
    HAPPY = "happy"       # EII 60-80: 开心/活泼
    EXCITED = "excited"   # EII 80-100: 激动/兴奋


@dataclass
class TTSConfig:
    """TTS generation configuration."""
    text_lang: str = "zh"           # Text language: zh, en, ja, etc.
    top_k: int = 5
    top_p: float = 1.0
    temperature: float = 1.0
    speed_factor: float = 1.0       # Speech speed (0.5-2.0)
    how_to_cut: str = "凑四句一切"   # Text cutting method


@dataclass
class EmotionParams:
    """Emotion-derived synthesis parameters."""
    preset: EmotionPreset
    ref_audio: str                 # Path to reference audio
    ref_text: str                  # Text of reference audio
    speed_factor: float
    temperature: float


class GPTSoVITSClient:
    """
    Async client for GPT SoVITS TTS API.

    Usage:
        client = GPTSoVITSClient("http://localhost:9872")
        audio_path = await client.synthesize("你好", emotion_preset="happy")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9872",
        timeout: float = 60.0,
        output_dir: Path = Path("audio/generated")
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Reference audio configuration
        self.reference_dir = Path("gpt-sovits/reference")
        self.emotion_references = {
            EmotionPreset.SAD: self.reference_dir / "sad.wav",
            EmotionPreset.CALM: self.reference_dir / "calm.wav",
            EmotionPreset.NEUTRAL: self.reference_dir / "neutral.wav",
            EmotionPreset.HAPPY: self.reference_dir / "happy.wav",
            EmotionPreset.EXCITED: self.reference_dir / "excited.wav",
        }

        # Default reference texts (should match your reference audio content)
        self.emotion_texts = {
            EmotionPreset.SAD: "为什么……事情会变成这样呢……",
            EmotionPreset.CALM: "嗯，让我想想。",
            EmotionPreset.NEUTRAL: "你好，我是 Lapwing。",
            EmotionPreset.HAPPY: "太好了！真开心能见到你呢~",
            EmotionPreset.EXCITED: "哇！太棒了！我好激动！",
        }

        # Default config per emotion
        self.emotion_configs = {
            EmotionPreset.SAD: TTSConfig(
                speed_factor=0.85,      # Slower
                temperature=0.8,        # More stable
            ),
            EmotionPreset.CALM: TTSConfig(
                speed_factor=0.95,      # Slightly slower
                temperature=0.9,
            ),
            EmotionPreset.NEUTRAL: TTSConfig(
                speed_factor=1.0,       # Normal
                temperature=1.0,
            ),
            EmotionPreset.HAPPY: TTSConfig(
                speed_factor=1.1,       # Slightly faster
                temperature=1.1,        # More variation
            ),
            EmotionPreset.EXCITED: TTSConfig(
                speed_factor=1.2,       # Faster
                temperature=1.2,
            ),
        }

    def eii_to_emotion(self, eii: float) -> EmotionPreset:
        """
        Map EII (0-100) to emotion preset.

        Args:
            eii: Emotional Intensity Index (0-100)

        Returns:
            EmotionPreset for the given EII
        """
        if eii < 20:
            return EmotionPreset.SAD
        elif eii < 40:
            return EmotionPreset.CALM
        elif eii < 60:
            return EmotionPreset.NEUTRAL
        elif eii < 80:
            return EmotionPreset.HAPPY
        else:
            return EmotionPreset.EXCITED

    def _get_emotion_params(self, preset: EmotionPreset) -> EmotionParams:
        """Get parameters for emotion preset."""
        ref_path = self.emotion_references[preset]
        if not ref_path.exists():
            # Fallback to neutral if specific emotion not available
            logging.warning(f"Reference audio for {preset} not found, using neutral")
            ref_path = self.emotion_references[EmotionPreset.NEUTRAL]
            preset = EmotionPreset.NEUTRAL

        config = self.emotion_configs[preset]

        return EmotionParams(
            preset=preset,
            ref_audio=str(ref_path.absolute()),
            ref_text=self.emotion_texts[preset],
            speed_factor=config.speed_factor,
            temperature=config.temperature
        )

    def _generate_cache_key(self, text: str, params: EmotionParams) -> str:
        """Generate cache key for text + params combination."""
        key = f"{text}:{params.preset.value}:{params.speed_factor}:{params.temperature}"
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cached audio file path."""
        # Organize by date
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        cache_dir = self.output_dir / "cache" / date_str
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{cache_key}.wav"

    async def synthesize(
        self,
        text: str,
        emotion_preset: Optional[EmotionPreset] = None,
        eii: Optional[float] = None,
        use_cache: bool = True,
        text_lang: str = "zh"
    ) -> Path:
        """
        Synthesize speech from text.

        Args:
            text: Text to synthesize
            emotion_preset: Specific emotion (overrides EII)
            eii: EII value (0-100), used to determine emotion if preset not given
            use_cache: Whether to use cache
            text_lang: Language of the text

        Returns:
            Path to generated audio file
        """
        # Determine emotion
        if emotion_preset is None:
            if eii is None:
                emotion_preset = EmotionPreset.NEUTRAL
            else:
                emotion_preset = self.eii_to_emotion(eii)

        params = self._get_emotion_params(emotion_preset)

        # Check cache
        if use_cache:
            cache_key = self._generate_cache_key(text, params)
            cache_path = self._get_cache_path(cache_key)
            if cache_path.exists():
                logging.debug(f"TTS cache hit: {cache_path}")
                return cache_path

        # Prepare API request
        api_data = {
            "text": text,
            "text_lang": text_lang,
            "ref_audio_path": params.ref_audio,
            "prompt_text": params.ref_text,
            "prompt_lang": "zh",
            "how_to_cut": "凑四句一切",
            "top_k": 5,
            "top_p": 1.0,
            "temperature": params.temperature,
            "speed_factor": params.speed_factor,
            "ref_free": False,
        }

        logging.info(f"TTS synthesizing: '{text[:50]}...' with {emotion_preset.value}")

        # Call API
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                async with session.post(
                    f"{self.base_url}/tts",
                    json=api_data
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"TTS API error {response.status}: {error_text}")

                    # Get audio content
                    audio_data = await response.read()

                    # Save to file
                    if use_cache:
                        output_path = cache_path
                    else:
                        timestamp = int(time.time() * 1000)
                        output_path = self.output_dir / f"{timestamp}_{emotion_preset.value}.wav"

                    output_path.write_bytes(audio_data)
                    logging.info(f"TTS saved: {output_path}")

                    return output_path

            except asyncio.TimeoutError:
                raise RuntimeError(f"TTS request timeout after {self.timeout.total}s")
            except aiohttp.ClientError as e:
                raise RuntimeError(f"TTS request failed: {e}")

    async def synthesize_batch(
        self,
        texts: list[str],
        emotion_preset: Optional[EmotionPreset] = None,
        eii: Optional[float] = None,
        max_concurrent: int = 3
    ) -> list[Path]:
        """
        Synthesize multiple texts with rate limiting.

        Args:
            texts: List of texts to synthesize
            emotion_preset: Emotion to use
            eii: EII value for auto emotion
            max_concurrent: Max concurrent requests

        Returns:
            List of audio file paths
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def synth_with_semaphore(text: str) -> Path:
            async with semaphore:
                return await self.synthesize(text, emotion_preset, eii)

        tasks = [synth_with_semaphore(t) for t in texts]
        return await asyncio.gather(*tasks)

    async def health_check(self) -> dict:
        """Check if TTS service is healthy."""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        return await response.json()
                    return {"status": "unhealthy", "code": response.status}
            except Exception as e:
                return {"status": "unreachable", "error": str(e)}

    async def close(self):
        """Cleanup resources."""
        pass  # aiohttp sessions are created per-request


class LapwingTTS:
    """
    High-level TTS wrapper for Lapwing.
    Integrates with emotional state and provides convenience methods.
    """

    def __init__(self, base_url: str = "http://localhost:9872"):
        self.client = GPTSoVITSClient(base_url)

    async def speak(
        self,
        text: str,
        eii: float = 50.0,
        use_cache: bool = True
    ) -> str:
        """
        Generate speech for Lapwing's response.

        Args:
            text: Response text
            eii: Current EII value
            use_cache: Use cached audio if available

        Returns:
            URL/path to audio file (relative to static serve)
        """
        audio_path = await self.client.synthesize(
            text=text,
            eii=eii,
            use_cache=use_cache
        )

        # Convert to relative URL for API response
        # e.g., /audio/generated/cache/2025-05-12/hash.wav
        try:
            relative_path = audio_path.relative_to(Path.cwd())
            return f"/{relative_path.as_posix()}"
        except ValueError:
            return f"/{audio_path.as_posix()}"

    async def speak_sentences(
        self,
        text: str,
        eii: float = 50.0,
        sentence_endings: tuple = ('。', '！', '？', '.', '!', '?')
    ) -> list[str]:
        """
        Split text into sentences and synthesize each.
        Useful for streaming/long responses.

        Args:
            text: Full response text
            eii: Current EII
            sentence_endings: Characters that end sentences

        Returns:
            List of audio file URLs/paths
        """
        # Simple sentence splitting
        import re
        pattern = f"([{''.join(sentence_endings)}])"
        parts = re.split(pattern, text)

        # Recombine sentence with its ending
        sentences = []
        current = ""
        for part in parts:
            if part in sentence_endings:
                current += part
                if current.strip():
                    sentences.append(current.strip())
                current = ""
            else:
                current = part

        if current.strip():
            sentences.append(current.strip())

        if not sentences:
            sentences = [text]

        # Generate audio for each sentence
        results = await self.client.synthesize_batch(
            texts=sentences,
            eii=eii,
            max_concurrent=2  # Be gentle on the GPU
        )

        return [f"/{r.relative_to(Path.cwd()).as_posix()}" for r in results]

    async def close(self):
        await self.client.close()
