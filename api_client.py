import google.generativeai as genai
import asyncio
import random
import structlog

logger = structlog.get_logger()

class ApiClient:
    """A wrapper to handle the stateful configuration of the genai library."""
    def __init__(self, api_key: str, generation_config: dict, model_name: str = 'gemini-pro', max_retries: int = 3, backoff_factor: float = 0.5):
        self.api_key = api_key
        self.generation_config = generation_config
        self.model = genai.GenerativeModel(model_name, generation_config=self.generation_config)
        self.chat_session = self.model.start_chat(history=[])
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def _configure(self):
        """Sets the global API key for the upcoming call."""
        genai.configure(api_key=self.api_key)

    async def _execute_with_retry(self, api_call_coroutine):
        """Executes a given API call coroutine with retry logic."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                self._configure()
                return await api_call_coroutine()
            except Exception as e:
                last_exception = e
                wait_time = self.backoff_factor * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning("api_call_failed", attempt=attempt + 1, max_attempts=self.max_retries, wait_time=wait_time, error=str(e))
                await asyncio.sleep(wait_time)
        raise last_exception or RuntimeError("API call failed after all retries.")

    async def generate_content(self, prompt: str):
        return await self._execute_with_retry(lambda: self.model.generate_content_async(prompt))

    async def send_chat_message(self, prompt: str, stream: bool = False):
        return await self._execute_with_retry(lambda: self.model.generate_content_async(prompt, stream=stream))
