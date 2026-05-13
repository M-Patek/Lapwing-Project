"""Lapwing LLM Provider for Open-LLM-VTuber.

This provider connects Open-LLM-VTuber to Lapwing's emotional AI backend,
enabling Live2D avatar with emotional intelligence, weighted memory,
dreaming system, and proactive behavior.
"""

from typing import AsyncIterator, List, Dict, Any
import httpx
from loguru import logger

from .stateless_llm_interface import StatelessLLMInterface


class LapwingLLM(StatelessLLMInterface):
    """Lapwing LLM Provider - connects to Lapwing emotional AI backend."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "lapwing",
        temperature: float = 0.95,
        **kwargs,
    ):
        """Initialize Lapwing LLM Provider.

        Args:
            base_url: URL of Lapwing API server (default: http://localhost:8000)
            model: Model name (not used, for compatibility)
            temperature: Temperature (not used, Lapwing manages this)
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.support_tools = False  # Lapwing handles tools internally

        # Session state
        self.session_id: str = None

        logger.info(f"Initialized LapwingLLM with base_url: {self.base_url}")

    async def _ensure_session(self):
        """Ensure we have a session with Lapwing."""
        # Lapwing doesn't require explicit session creation
        # It maintains state internally
        pass

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        system: str = None,
        tools: List[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """Generate chat completion using Lapwing API.

        Args:
            messages: List of messages (converted to single user message)
            system: System prompt (ignored, Lapwing uses its own persona)
            tools: Tools (ignored, Lapwing handles internally)

        Yields:
            str: Response content from Lapwing
        """
        try:
            # Extract the last user message
            user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        # Handle multi-modal content
                        for item in content:
                            if item.get("type") == "text":
                                user_message = item.get("text", "")
                                break
                    else:
                        user_message = content
                    break

            if not user_message:
                logger.warning("No user message found in conversation history")
                user_message = "Hello"

            # Call Lapwing chat API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat",
                    json={"message": user_message},
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                # Extract response
                lapwing_response = data.get("response", "")

                if not lapwing_response:
                    logger.warning("Empty response from Lapwing")
                    yield "I'm sorry, I couldn't process that."
                    return

                # Stream the response word by word for real-time effect
                words = lapwing_response.split()
                for word in words:
                    yield word + " "

        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to Lapwing server at {self.base_url}: {e}")
            yield f"[Error: Cannot connect to Lapwing server. Please ensure it's running on {self.base_url}]"
        except httpx.TimeoutException:
            logger.error("Lapwing request timed out")
            yield "[Error: Request timed out. Lapwing is taking too long to respond.]"
        except Exception as e:
            logger.error(f"Error in Lapwing chat completion: {e}")
            yield f"[Error: {str(e)}]"

    async def get_emotional_state(self) -> Dict[str, Any]:
        """Get current emotional state from Lapwing.

        Returns:
            Dict with EII and other emotional metrics
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    timeout=5.0,
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "eii": data.get("eii", 53.0),
                    "status": data.get("status", "unknown"),
                }
        except Exception as e:
            logger.error(f"Failed to get emotional state: {e}")
            return {"eii": 53.0, "status": "error"}

    async def get_proactive_message(self) -> str:
        """Check for proactive messages from Lapwing.

        Returns:
            Proactive message if available, empty string otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/proactive/messages",
                    timeout=5.0,
                )
                response.raise_for_status()
                data = response.json()
                messages = data.get("messages", [])
                return messages[0] if messages else ""
        except Exception as e:
            logger.debug(f"No proactive messages: {e}")
            return ""
