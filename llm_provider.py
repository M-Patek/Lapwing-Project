"""
Abstract LLM Provider Interface
Supports multiple providers: Anthropic, DeepSeek, OpenAI, etc.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass
from enum import Enum, auto
import logging


class ProviderType(Enum):
    """Supported LLM provider types"""
    ANTHROPIC = auto()
    DEEPSEEK = auto()
    OPENAI = auto()
    CUSTOM = auto()


@dataclass
class LLMResponse:
    """Standardized LLM response"""
    text: str
    model: str
    provider: ProviderType
    usage: Optional[Dict[str, int]] = None  # {"input_tokens": int, "output_tokens": int}
    raw_response: Any = None  # Provider-specific raw response


@dataclass
class LLMConfig:
    """Configuration for LLM requests"""
    temperature: float = 0.95
    max_tokens: int = 4096
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    system_prompt: Optional[str] = None
    stream: bool = False


@dataclass
class EmbeddingResponse:
    """Standardized embedding response"""
    embeddings: List[List[float]]
    model: str
    provider: ProviderType


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    All providers must implement these methods.
    """

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._chat_history: List[Dict[str, str]] = []

    @abstractmethod
    async def chat(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        """
        Send a chat message and get response.

        Args:
            prompt: User message
            config: Request configuration

        Returns:
            Standardized LLMResponse
        """
        pass

    @abstractmethod
    async def chat_stream(
        self, prompt: str, config: Optional[LLMConfig] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response.

        Args:
            prompt: User message
            config: Request configuration

        Yields:
            Text chunks as they arrive
        """
        pass

    @abstractmethod
    async def get_embeddings(self, texts: List[str]) -> EmbeddingResponse:
        """
        Get embeddings for texts.

        Args:
            texts: List of texts to embed

        Returns:
            Standardized EmbeddingResponse
        """
        pass

    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type"""
        pass

    async def chat_with_history(
        self, prompt: str, config: Optional[LLMConfig] = None, clear_history: bool = False
    ) -> LLMResponse:
        """
        Chat with conversation history maintenance.
        Default implementation - providers can override for optimization.
        """
        if clear_history:
            self._chat_history.clear()

        self._chat_history.append({"role": "user", "content": prompt})

        # Build full context from history
        full_prompt = self._build_history_prompt()

        response = await self.chat(full_prompt, config)

        if response.text:
            self._chat_history.append({"role": "assistant", "content": response.text})

        # Trim history if too long
        if len(self._chat_history) > 20:
            self._chat_history = self._chat_history[-20:]

        return response

    def _build_history_prompt(self) -> str:
        """Build prompt from chat history"""
        lines = []
        for msg in self._chat_history:
            role = "Human" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)

    def clear_history(self):
        """Clear chat history"""
        self._chat_history.clear()


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider"""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(api_key, base_url, model or "claude-opus-4-7")
        self._client = None

    def _get_client(self):
        """Lazy initialization of Anthropic client"""
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def provider_type(self) -> ProviderType:
        return ProviderType.ANTHROPIC

    async def chat(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        cfg = config or LLMConfig()
        client = self._get_client()

        try:
            response = await client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                system=cfg.system_prompt if cfg.system_prompt else None,
            )

            text = response.content[0].text if response.content else ""

            return LLMResponse(
                text=text,
                model=self.model,
                provider=ProviderType.ANTHROPIC,
                usage={
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logging.error(f"Anthropic API error: {e}")
            raise

    async def chat_stream(
        self, prompt: str, config: Optional[LLMConfig] = None
    ) -> AsyncGenerator[str, None]:
        cfg = config or LLMConfig()
        client = self._get_client()

        try:
            async with client.messages.stream(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                system=cfg.system_prompt if cfg.system_prompt else None,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            logging.error(f"Anthropic streaming error: {e}")
            raise

    async def get_embeddings(self, texts: List[str]) -> EmbeddingResponse:
        """
        Anthropic doesn't have an embedding API.
        Use a fallback or raise an error.
        """
        logging.warning("Anthropic doesn't support embeddings, using fallback")
        # Return deterministic pseudo-embeddings
        import hashlib
        import random

        embeddings = []
        for text in texts:
            hash_val = hashlib.md5(text.encode()).hexdigest()
            seed = int(hash_val, 16)
            random.seed(seed)
            vec = [random.gauss(0, 1) for _ in range(1536)]
            norm = sum(x*x for x in vec) ** 0.5
            vec = [x/norm for x in vec]
            embeddings.append(vec)
            random.seed()

        return EmbeddingResponse(
            embeddings=embeddings,
            model="fallback-anthropic",
            provider=ProviderType.ANTHROPIC,
        )


class DeepSeekProvider(LLMProvider):
    """DeepSeek provider - uses OpenAI compatible API"""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(api_key, base_url or "https://api.deepseek.com", model or "deepseek-v4-flash")
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI-compatible client for DeepSeek"""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def provider_type(self) -> ProviderType:
        return ProviderType.DEEPSEEK

    async def chat(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        cfg = config or LLMConfig()
        client = self._get_client()

        messages = []
        if cfg.system_prompt:
            messages.append({"role": "system", "content": cfg.system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
            )

            text = response.choices[0].message.content if response.choices else ""

            return LLMResponse(
                text=text,
                model=self.model,
                provider=ProviderType.DEEPSEEK,
                usage={
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logging.error(f"DeepSeek API error: {e}")
            raise

    async def chat_stream(
        self, prompt: str, config: Optional[LLMConfig] = None
    ) -> AsyncGenerator[str, None]:
        cfg = config or LLMConfig()
        client = self._get_client()

        messages = []
        if cfg.system_prompt:
            messages.append({"role": "system", "content": cfg.system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                stream=True,
            )

            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logging.error(f"DeepSeek streaming error: {e}")
            raise

    async def get_embeddings(self, texts: List[str]) -> EmbeddingResponse:
        """
        DeepSeek embedding API (if available) or fallback.
        DeepSeek may support embeddings through OpenAI compatible endpoint.
        """
        client = self._get_client()

        try:
            # Try DeepSeek embedding endpoint
            response = await client.embeddings.create(
                model="deepseek-embedding",  # or similar
                input=[t for t in texts if t and t.strip()],
            )

            embeddings = [item.embedding for item in response.data]

            return EmbeddingResponse(
                embeddings=embeddings,
                model="deepseek-embedding",
                provider=ProviderType.DEEPSEEK,
            )
        except Exception as e:
            logging.warning(f"DeepSeek embedding failed: {e}, using fallback")
            # Fallback: use deterministic hashing
            import hashlib
            import random

            embeddings = []
            for text in texts:
                hash_val = hashlib.md5(text.encode()).hexdigest()
                seed = int(hash_val, 16)
                random.seed(seed)
                vec = [random.gauss(0, 1) for _ in range(1536)]
                norm = sum(x*x for x in vec) ** 0.5
                vec = [x/norm for x in vec]
                embeddings.append(vec)
                random.seed()

            return EmbeddingResponse(
                embeddings=embeddings,
                model="fallback-deepseek",
                provider=ProviderType.DEEPSEEK,
            )


class OpenAIProvider(LLMProvider):
    """OpenAI provider"""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(api_key, base_url or "https://api.openai.com/v1", model or "gpt-4o")
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client"""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def provider_type(self) -> ProviderType:
        return ProviderType.OPENAI

    async def chat(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        cfg = config or LLMConfig()
        client = self._get_client()

        messages = []
        if cfg.system_prompt:
            messages.append({"role": "system", "content": cfg.system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
            )

            text = response.choices[0].message.content if response.choices else ""

            return LLMResponse(
                text=text,
                model=self.model,
                provider=ProviderType.OPENAI,
                usage={
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logging.error(f"OpenAI API error: {e}")
            raise

    async def chat_stream(
        self, prompt: str, config: Optional[LLMConfig] = None
    ) -> AsyncGenerator[str, None]:
        cfg = config or LLMConfig()
        client = self._get_client()

        messages = []
        if cfg.system_prompt:
            messages.append({"role": "system", "content": cfg.system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                stream=True,
            )

            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logging.error(f"OpenAI streaming error: {e}")
            raise

    async def get_embeddings(self, texts: List[str]) -> EmbeddingResponse:
        """OpenAI has native embedding support"""
        client = self._get_client()

        try:
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=[t for t in texts if t and t.strip()],
            )

            embeddings = [item.embedding for item in response.data]

            return EmbeddingResponse(
                embeddings=embeddings,
                model="text-embedding-3-small",
                provider=ProviderType.OPENAI,
            )
        except Exception as e:
            logging.error(f"OpenAI embedding error: {e}")
            raise


class LLMProviderFactory:
    """Factory for creating LLM providers"""

    _providers: Dict[ProviderType, type] = {
        ProviderType.ANTHROPIC: AnthropicProvider,
        ProviderType.DEEPSEEK: DeepSeekProvider,
        ProviderType.OPENAI: OpenAIProvider,
    }

    @classmethod
    def create(
        cls,
        provider_type: ProviderType,
        api_key: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> LLMProvider:
        """Create a provider instance"""
        if provider_type not in cls._providers:
            raise ValueError(f"Unknown provider type: {provider_type}")

        provider_class = cls._providers[provider_type]
        return provider_class(api_key, base_url, model)

    @classmethod
    def create_from_config(cls, settings: "Settings") -> "MultiProviderManager":
        """Create provider manager from settings"""
        return MultiProviderManager(settings)


class MultiProviderManager:
    """
    Manages multiple providers for different use cases.
    Supports hybrid setup: e.g., DeepSeek for chat, OpenAI for embeddings.
    """

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self._chat_provider: Optional[LLMProvider] = None
        self._scene_provider: Optional[LLMProvider] = None
        self._embedding_provider: Optional[LLMProvider] = None

        # Detect provider type from settings
        self._detect_providers()

        # Ensure embedding provider is available
        self._ensure_embedding_provider()

    def _detect_providers(self):
        """Auto-detect provider types from available API keys"""
        provider = self.settings.LLM_PROVIDER.lower()

        if provider == "anthropic" and self.settings.ANTHROPIC_API_KEY:
            self._chat_provider = AnthropicProvider(
                api_key=self.settings.ANTHROPIC_API_KEY,
                base_url=self.settings.ANTHROPIC_BASE_URL,
                model=self.settings.CHAT_MODEL,
            )
            self._scene_provider = AnthropicProvider(
                api_key=self.settings.ANTHROPIC_API_KEY,
                base_url=self.settings.ANTHROPIC_BASE_URL,
                model=self.settings.SCENE_MODEL or "claude-opus-4-6",
            )
        elif provider == "deepseek" and self.settings.DEEPSEEK_API_KEY:
            self._chat_provider = DeepSeekProvider(
                api_key=self.settings.DEEPSEEK_API_KEY,
                base_url=self.settings.DEEPSEEK_BASE_URL,
                model=self.settings.CHAT_MODEL or "deepseek-v4-flash",
            )
            self._scene_provider = DeepSeekProvider(
                api_key=self.settings.DEEPSEEK_API_KEY,
                base_url=self.settings.DEEPSEEK_BASE_URL,
                model=self.settings.SCENE_MODEL or "deepseek-v4-flash",
            )
        elif provider == "openai" and self.settings.OPENAI_API_KEY:
            self._chat_provider = OpenAIProvider(
                api_key=self.settings.OPENAI_API_KEY,
                base_url=self.settings.OPENAI_BASE_URL,
                model=self.settings.CHAT_MODEL or "gpt-4o",
            )
            self._scene_provider = OpenAIProvider(
                api_key=self.settings.OPENAI_API_KEY,
                base_url=self.settings.OPENAI_BASE_URL,
                model=self.settings.SCENE_MODEL or "gpt-4o-mini",
            )
            self._embedding_provider = self._chat_provider
        else:
            raise RuntimeError(f"No valid provider configured for: {provider}")

    def _ensure_embedding_provider(self):
        """Ensure we have a working embedding provider"""
        if self._embedding_provider is not None:
            return

        # Priority: OpenAI > fallback
        if self.settings.OPENAI_API_KEY and self.settings.OPENAI_API_KEY != "your-openai-key-here":
            logging.info("Using OpenAI for embeddings (hybrid mode)")
            self._embedding_provider = OpenAIProvider(
                api_key=self.settings.OPENAI_API_KEY,
                base_url=self.settings.OPENAI_BASE_URL,
            )
        else:
            logging.warning("No OpenAI key for embeddings, using fallback (random vectors)")
            # Will use the chat provider's fallback implementation
            self._embedding_provider = self._chat_provider

    @property
    def chat_provider(self) -> LLMProvider:
        """Provider for main chat"""
        if self._chat_provider is None:
            raise RuntimeError("No chat provider configured")
        return self._chat_provider

    @property
    def scene_provider(self) -> LLMProvider:
        """Provider for background tasks"""
        if self._scene_provider is None:
            raise RuntimeError("No scene provider configured")
        return self._scene_provider

    @property
    def embedding_provider(self) -> LLMProvider:
        """Provider for embeddings"""
        if self._embedding_provider is None:
            # Fall back to chat provider (which will use fallback embeddings)
            return self._chat_provider
        return self._embedding_provider

    async def close(self):
        """Cleanup (providers don't need explicit close)"""
        pass
