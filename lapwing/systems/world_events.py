"""
World State Updater - Simulates Lapwing's independent life in Paris.
Manages time, weather, social events, and projects.
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional
import httpx
from jinja2 import Environment, FileSystemLoader

from lapwing.core.settings import Settings
from lapwing.api.llm_provider import MultiProviderManager
from lapwing.utils.utils import save_json


class WorldClock:
    """Manages time context for Paris timezone."""

    def __init__(self, tz_str: str = "Europe/Paris"):
        self.tz = ZoneInfo(tz_str)

    def get_current_time(self) -> datetime:
        """Get current time in Paris."""
        return datetime.now(self.tz)

    def get_time_context(self) -> tuple[str, str, str]:
        """
        Get formatted time context.

        Returns:
            (time_string, day_of_week, time_of_day)
        """
        now = self.get_current_time()
        day_of_week = now.strftime("%A")
        hour = now.hour

        if 5 <= hour < 12:
            time_of_day = "Morning"
        elif 12 <= hour < 17:
            time_of_day = "Afternoon"
        elif 17 <= hour < 21:
            time_of_day = "Evening"
        else:
            time_of_day = "Night"

        return now.strftime("%Y-%m-%d %H:%M"), day_of_week, time_of_day


class SocialManager:
    """Manages Lapwing's social interactions and projects."""

    def __init__(self):
        self.friends = ["Elise", "Chloé", "Léo", "Marie", "Julien"]
        self.project_state: str = "Idle"
        self.project_progress: int = 0
        self.project_name: Optional[str] = None

    def get_social_context(self) -> str:
        """Generate random social event context."""
        if random.random() < 0.1:
            friend = random.choice(self.friends)
            events = [
                f"Just received a nice message from {friend}.",
                f"Planning to meet {friend} for coffee this week.",
                f"{friend} sent a funny meme about cats.",
            ]
            return random.choice(events)
        return "A quiet day on the social front."

    def get_project_context(self) -> str:
        """Generate project update context."""
        # Start new project
        if self.project_state == "Idle" and random.random() < 0.05:
            self.project_state = "In Progress"
            self.project_progress = 10
            projects = [
                "gallery website UI",
                "cafe menu design",
                "photography portfolio",
                "brand identity project",
            ]
            self.project_name = random.choice(projects)
            return f"Just got a new commission for a {self.project_name}. Exciting!"

        # Progress existing project
        elif self.project_state == "In Progress":
            self.project_progress += random.randint(5, 15)

            if self.project_progress >= 100:
                self.project_state = "Idle"
                self.project_progress = 0
                name = self.project_name or "project"
                self.project_name = None
                return f"Finished the {name}! It feels so good to deliver it."

            return f"Making progress on the project. Now at {self.project_progress}%."

        return "No active projects at the moment."


class WeatherService:
    """Fetches weather data from Open-Meteo API."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_weather(self) -> str:
        """Fetch current weather for Paris."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {
                    "latitude": self.settings.WEATHER_LATITUDE,
                    "longitude": self.settings.WEATHER_LONGITUDE,
                    "current_weather": "true",
                }
                response = await client.get(
                    self.settings.WEATHER_API_URL, params=params
                )
                response.raise_for_status()
                data = response.json()

                temp = data["current_weather"]["temperature"]
                code = data["current_weather"]["weathercode"]

                # Map weather codes to descriptions
                weather_desc = self._weather_code_to_description(code)
                return f"{temp}°C, {weather_desc}"

        except Exception as e:
            logging.warning(f"Weather fetch failed: {e}")
            # Return simulated weather based on time of day
            from datetime import datetime

            hour = datetime.now().hour
            if 6 <= hour < 12:
                return "12°C, Morning mist"
            elif 12 <= hour < 18:
                return "18°C, Partly cloudy"
            elif 18 <= hour < 22:
                return "15°C, Clear evening"
            else:
                return "8°C, Starry night"

    @staticmethod
    def _weather_code_to_description(code: int) -> str:
        """Convert WMO weather code to description."""
        weather_codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            95: "Thunderstorm",
            96: "Thunderstorm with hail",
        }
        return weather_codes.get(code, f"Weather code {code}")


class WorldStateUpdater:
    """
    Updates Lapwing's world state periodically.
    Runs as a background task to simulate her independent life.
    """

    def __init__(self, settings: Settings, api_manager: MultiProviderManager):
        self.settings = settings
        self.api_manager = api_manager
        self.clock = WorldClock(str(settings.PARIS_TZ))
        self.social = SocialManager()
        self.weather = WeatherService(settings)
        self.state_file = Path(settings.STATE_FILE)

        # Jinja2 template for event generation
        self.jinja_env = Environment(
            loader=FileSystemLoader("prompts"), autoescape=True
        )
        self.event_template = self.jinja_env.get_template("event_prompts.jinja2")

    def _load_state(self) -> dict:
        """Load current state from file."""
        if self.state_file.exists() and self.state_file.stat().st_size > 0:
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logging.warning("State file corrupted, using defaults")
        return {}

    def _save_state(self, state_data: dict) -> None:
        """Save state to file."""
        save_json(self.state_file, state_data)

    async def _generate_scene(self, context: dict) -> str:
        """
        Generate new scene description using LLM.

        Args:
            context: Dictionary with time, weather, social, project context

        Returns:
            Generated scene description
        """
        prompt = self.event_template.render(**context)

        try:
            response = await self.api_manager.scene_provider.chat(
                prompt
            )
            return response.text.strip()[:500]  # Limit length
        except Exception as e:
            logging.error(f"Scene generation failed: {e}")
            return "Quietly enjoying the moment."

    async def update_world_state(self) -> None:
        """Main update method - fetches data and generates new scene."""
        logging.info("World Heartbeat: Checking for state update...")

        try:
            # Load current state
            state = self._load_state()
            timeline = state.get(
                "current_timeline",
                {"scene": "Waking up.", "next_intention": "Thinking about the day."},
            )

            # Gather context
            weather_str = await self.weather.get_weather()
            paris_time, day_of_week, time_of_day = self.clock.get_time_context()

            context = {
                "timeline": timeline,
                "paris_time_str": paris_time,
                "day_of_week": day_of_week,
                "time_of_day": time_of_day,
                "weather_str": weather_str,
                "social_context": self.social.get_social_context(),
                "project_context": self.social.get_project_context(),
            }

            # Generate new scene
            new_scene = await self._generate_scene(context)

            # Update timeline
            new_timeline = {
                "previous_event": timeline.get("scene", "A quiet moment."),
                "scene": new_scene,
                "next_intention": "Thinking about what to do next...",
            }

            state["current_timeline"] = new_timeline
            state["last_world_update_timestamp"] = datetime.now(
                timezone.utc
            ).isoformat()

            self._save_state(state)
            logging.info(f"World state updated: {new_scene[:100]}...")

        except Exception as e:
            logging.error(f"World state update failed: {e}", exc_info=True)

    async def run_loop(self, interval_minutes: int = 15) -> None:
        """
        Run periodic world state updates.

        Args:
            interval_minutes: Minutes between updates
        """
        logging.info(f"Starting world state updater (interval: {interval_minutes}min)")

        while True:
            try:
                await self.update_world_state()
            except Exception as e:
                logging.error(f"Error in world updater loop: {e}", exc_info=True)

            await asyncio.sleep(interval_minutes * 60)
