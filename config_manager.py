"""
Configuration Hot Reload System
Monitors config files and reloads without restart.
"""
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Callable, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime
import json
import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

from settings import Settings


@dataclass
class ConfigChange:
    """Represents a configuration change"""
    file_path: Path
    old_value: Any
    new_value: Any
    timestamp: datetime


class ConfigFileHandler(FileSystemEventHandler):
    """Watchdog handler for config file changes"""

    def __init__(self, callback: Callable[[Path], None]):
        self.callback = callback

    def on_modified(self, event):
        if not event.is_directory:
            self.callback(Path(event.src_path))


class ConfigManager:
    """
    Configuration manager with hot reload support.

    Usage:
        config = ConfigManager(settings)
        await config.start_watching()

        # Register change handlers
        config.on_change("TEMPERATURE", on_temp_change)

        # Access current config
        current_temp = config.get("TEMPERATURE")
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._current_config: Dict[str, Any] = {}
        self._change_handlers: Dict[str, List[Callable]] = {}
        self._global_handlers: List[Callable] = []
        self._watched_files: Set[Path] = set()
        self._observer: Optional[Observer] = None
        self._watching = False
        self._last_reload: Dict[Path, datetime] = {}
        self._reload_debounce_seconds = 1.0

        # Load initial config
        self._load_config()

    def _load_config(self):
        """Load current configuration into dict"""
        self._current_config = {
            "LLM_PROVIDER": self.settings.LLM_PROVIDER,
            "CHAT_MODEL": self.settings.CHAT_MODEL,
            "SCENE_MODEL": self.settings.SCENE_MODEL,
            "TEMPERATURE": self.settings.TEMPERATURE,
            "MAX_TOKENS": self.settings.MAX_TOKENS,
            "EII_BASELINE": self.settings.EII_BASELINE,
            "SIMILARITY_THRESHOLD": self.settings.SIMILARITY_THRESHOLD,
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._current_config.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values"""
        return self._current_config.copy()

    def on_change(self, key: str, handler: Callable[[ConfigChange], None]):
        """
        Register a handler for a specific config key change.

        Args:
            key: Configuration key to watch
            handler: Callback function receiving ConfigChange
        """
        if key not in self._change_handlers:
            self._change_handlers[key] = []
        self._change_handlers[key].append(handler)

    def on_any_change(self, handler: Callable[[ConfigChange], None]):
        """Register a handler for any config change"""
        self._global_handlers.append(handler)

    async def start_watching(self):
        """Start watching config files for changes"""
        if self._watching:
            return

        self._watching = True

        # Watch .env file
        env_file = Path(".env")
        if env_file.exists():
            self._watched_files.add(env_file.absolute())

        # Watch settings files
        settings_files = [
            Path("settings.py"),
            Path("config.yaml"),
            Path("conf.yaml"),
        ]
        for f in settings_files:
            if f.exists():
                self._watched_files.add(f.absolute())

        if not self._watched_files:
            logging.warning("[ConfigManager] No config files to watch")
            return

        # Setup watchdog
        self._observer = Observer()
        handler = ConfigFileHandler(self._on_file_changed)

        for file_path in self._watched_files:
            self._observer.schedule(handler, str(file_path.parent), recursive=False)
            logging.info(f"[ConfigManager] Watching: {file_path}")

        self._observer.start()
        logging.info("[ConfigManager] Started watching config files")

    def stop_watching(self):
        """Stop watching config files"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._watching = False
            logging.info("[ConfigManager] Stopped watching")

    def _on_file_changed(self, file_path: Path):
        """Handle file change event"""
        # Debounce: ignore rapid successive changes
        now = datetime.now()
        last_change = self._last_reload.get(file_path)
        if last_change and (now - last_change).total_seconds() < self._reload_debounce_seconds:
            return

        self._last_reload[file_path] = now

        # Schedule reload
        asyncio.create_task(self._reload_config(file_path))

    async def _reload_config(self, file_path: Path):
        """Reload configuration from file"""
        logging.info(f"[ConfigManager] Reloading config from: {file_path}")

        try:
            old_config = self._current_config.copy()

            # Reload based on file type
            if file_path.name == ".env":
                await self._reload_from_env(file_path)
            elif file_path.suffix in [".yaml", ".yml"]:
                await self._reload_from_yaml(file_path)
            elif file_path.suffix == ".json":
                await self._reload_from_json(file_path)

            # Detect changes and notify handlers
            await self._detect_changes(old_config)

        except Exception as e:
            logging.error(f"[ConfigManager] Failed to reload config: {e}")

    async def _reload_from_env(self, file_path: Path):
        """Reload from .env file"""
        from dotenv import load_dotenv
        import os

        # Clear and reload
        load_dotenv(str(file_path), override=True)

        # Update current config
        self._current_config.update({
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", self.settings.LLM_PROVIDER),
            "CHAT_MODEL": os.getenv("CHAT_MODEL", self.settings.CHAT_MODEL),
            "SCENE_MODEL": os.getenv("SCENE_MODEL", self.settings.SCENE_MODEL),
            "TEMPERATURE": float(os.getenv("TEMPERATURE", self.settings.TEMPERATURE)),
            "MAX_TOKENS": int(os.getenv("MAX_TOKENS", self.settings.MAX_TOKENS)),
        })

    async def _reload_from_yaml(self, file_path: Path):
        """Reload from YAML file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if data:
                self._current_config.update(data)

    async def _reload_from_json(self, file_path: Path):
        """Reload from JSON file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self._current_config.update(data)

    async def _detect_changes(self, old_config: Dict[str, Any]):
        """Detect changes and notify handlers"""
        for key, new_value in self._current_config.items():
            old_value = old_config.get(key)

            if old_value != new_value:
                change = ConfigChange(
                    file_path=Path(".env"),
                    old_value=old_value,
                    new_value=new_value,
                    timestamp=datetime.now()
                )

                # Notify specific handlers
                handlers = self._change_handlers.get(key, [])
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(change)
                        else:
                            handler(change)
                    except Exception as e:
                        logging.error(f"[ConfigManager] Handler error for {key}: {e}")

                # Notify global handlers
                for handler in self._global_handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(change)
                        else:
                            handler(change)
                    except Exception as e:
                        logging.error(f"[ConfigManager] Global handler error: {e}")

                logging.info(f"[ConfigManager] Changed {key}: {old_value} -> {new_value}")

    def validate(self) -> List[str]:
        """Validate current configuration"""
        errors = []

        # Validate temperature
        temp = self._current_config.get("TEMPERATURE")
        if temp is not None and not (0 <= temp <= 2):
            errors.append(f"TEMPERATURE must be between 0 and 2, got {temp}")

        # Validate max_tokens
        max_tokens = self._current_config.get("MAX_TOKENS")
        if max_tokens is not None and max_tokens < 1:
            errors.append(f"MAX_TOKENS must be positive, got {max_tokens}")

        # Validate EII baseline
        eii = self._current_config.get("EII_BASELINE")
        if eii is not None and not (0 <= eii <= 100):
            errors.append(f"EII_BASELINE must be between 0 and 100, got {eii}")

        return errors


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager(settings: Optional[Settings] = None) -> ConfigManager:
    """Get or create global config manager"""
    global _config_manager
    if _config_manager is None:
        if settings is None:
            raise RuntimeError("Settings required for first initialization")
        _config_manager = ConfigManager(settings)
    return _config_manager


# Example usage
if __name__ == "__main__":
    async def main():
        settings = Settings()
        config = get_config_manager(settings)

        # Register change handler
        def on_temp_change(change: ConfigChange):
            print(f"Temperature changed: {change.old_value} -> {change.new_value}")

        config.on_change("TEMPERATURE", on_temp_change)

        # Start watching
        await config.start_watching()

        # Wait for changes
        print("Modify .env file to see hot reload in action...")
        await asyncio.sleep(60)

        config.stop_watching()

    asyncio.run(main())
