"""
Audio Manager for TTS file handling
Provides file storage, cleanup, and static file serving configuration.
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass
from contextlib import asynccontextmanager
import aiofiles


@dataclass
class AudioStats:
    """Statistics about audio storage."""
    total_files: int
    total_size_mb: float
    cached_files: int
    generated_files: int
    oldest_file: Optional[datetime]
    newest_file: Optional[datetime]


class AudioManager:
    """
    Manages TTS audio file storage and cleanup.

    Directory structure:
    audio/
    ├── generated/           # Generated TTS files (auto-cleaned)
    │   └── cache/
    │       └── 2025-05-12/
    │           └── hash.wav
    └── reference/           # Reference audio for TTS (permanent)
        ├── sad.wav
        ├── calm.wav
        ├── neutral.wav
        ├── happy.wav
        └── excited.wav
    """

    def __init__(
        self,
        base_dir: Path = Path("audio"),
        max_cache_age_days: int = 7,
        max_generated_age_hours: int = 24,
        cleanup_interval_hours: int = 6
    ):
        self.base_dir = Path(base_dir)
        self.generated_dir = self.base_dir / "generated"
        self.cache_dir = self.generated_dir / "cache"
        self.reference_dir = self.base_dir / "reference"

        self.max_cache_age_days = max_cache_age_days
        self.max_generated_age_hours = max_generated_age_hours
        self.cleanup_interval_hours = cleanup_interval_hours

        # Ensure directories exist
        self._ensure_dirs()

        # Cleanup task handle
        self._cleanup_task: Optional[asyncio.Task] = None

    def _ensure_dirs(self):
        """Create required directories."""
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.reference_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Audio directories initialized: {self.base_dir}")

    async def start_cleanup_task(self):
        """Start periodic cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(),
                name="audio_cleanup"
            )
            logging.info("Started audio cleanup task")

    async def stop_cleanup_task(self):
        """Stop cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logging.info("Stopped audio cleanup task")

    async def _cleanup_loop(self):
        """Background loop for periodic cleanup."""
        while True:
            try:
                await self.cleanup()
            except Exception as e:
                logging.error(f"Audio cleanup error: {e}")

            # Wait until next cleanup
            await asyncio.sleep(self.cleanup_interval_hours * 3600)

    async def cleanup(self) -> dict:
        """
        Clean up old audio files.

        Returns:
            Cleanup statistics
        """
        stats = {
            "cache_deleted": 0,
            "generated_deleted": 0,
            "errors": []
        }

        now = datetime.now()

        # Clean cache files older than max_cache_age_days
        try:
            cache_deleted = await self._cleanup_directory(
                self.cache_dir,
                timedelta(days=self.max_cache_age_days),
                now
            )
            stats["cache_deleted"] = cache_deleted
        except Exception as e:
            stats["errors"].append(f"Cache cleanup error: {e}")

        # Clean non-cache generated files older than max_generated_age_hours
        try:
            generated_deleted = await self._cleanup_generated(
                timedelta(hours=self.max_generated_age_hours),
                now
            )
            stats["generated_deleted"] = generated_deleted
        except Exception as e:
            stats["errors"].append(f"Generated cleanup error: {e}")

        if stats["cache_deleted"] or stats["generated_deleted"]:
            logging.info(
                f"Audio cleanup: removed {stats['cache_deleted']} cache, "
                f"{stats['generated_deleted']} generated files"
            )

        return stats

    async def _cleanup_directory(
        self,
        directory: Path,
        max_age: timedelta,
        now: datetime
    ) -> int:
        """Clean up files in directory older than max_age."""
        deleted = 0

        if not directory.exists():
            return 0

        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue

            try:
                # Get file modification time
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

                if now - mtime > max_age:
                    file_path.unlink()
                    deleted += 1

                    # Remove empty parent directories
                    parent = file_path.parent
                    while parent != directory and not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent

            except Exception as e:
                logging.warning(f"Failed to delete {file_path}: {e}")

        return deleted

    async def _cleanup_generated(
        self,
        max_age: timedelta,
        now: datetime
    ) -> int:
        """Clean up non-cache generated files."""
        deleted = 0

        if not self.generated_dir.exists():
            return 0

        for file_path in self.generated_dir.iterdir():
            if not file_path.is_file():
                continue

            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

                if now - mtime > max_age:
                    file_path.unlink()
                    deleted += 1

            except Exception as e:
                logging.warning(f"Failed to delete {file_path}: {e}")

        return deleted

    def get_generated_path(self, filename: str) -> Path:
        """Get path for a generated audio file."""
        return self.generated_dir / filename

    def get_cache_path(self, date_str: str, filename: str) -> Path:
        """Get path for a cached audio file."""
        cache_subdir = self.cache_dir / date_str
        cache_subdir.mkdir(parents=True, exist_ok=True)
        return cache_subdir / filename

    def get_reference_path(self, filename: str) -> Path:
        """Get path for a reference audio file."""
        return self.reference_dir / filename

    def list_reference_files(self) -> List[Path]:
        """List all reference audio files."""
        if not self.reference_dir.exists():
            return []
        return [f for f in self.reference_dir.iterdir() if f.is_file()]

    async def save_generated(self, filename: str, data: bytes) -> Path:
        """Save a generated audio file."""
        path = self.get_generated_path(filename)
        async with aiofiles.open(path, 'wb') as f:
            await f.write(data)
        return path

    async def get_stats(self) -> AudioStats:
        """Get storage statistics."""
        total_files = 0
        total_size = 0
        oldest = None
        newest = None
        cached = 0
        generated = 0

        # Scan all audio directories
        for directory in [self.generated_dir, self.reference_dir]:
            if not directory.exists():
                continue

            for file_path in directory.rglob("*"):
                if not file_path.is_file():
                    continue

                total_files += 1
                size = file_path.stat().st_size
                total_size += size

                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

                if oldest is None or mtime < oldest:
                    oldest = mtime
                if newest is None or mtime > newest:
                    newest = mtime

                # Categorize
                if self.cache_dir in file_path.parents:
                    cached += 1
                elif self.reference_dir in file_path.parents:
                    pass  # reference files
                else:
                    generated += 1

        return AudioStats(
            total_files=total_files,
            total_size_mb=total_size / (1024 * 1024),
            cached_files=cached,
            generated_files=generated,
            oldest_file=oldest,
            newest_file=newest
        )

    async def clear_cache(self) -> int:
        """Manually clear all cache files."""
        if not self.cache_dir.exists():
            return 0

        count = 0
        for file_path in self.cache_dir.rglob("*"):
            if file_path.is_file():
                file_path.unlink()
                count += 1

        # Remove empty directories
        for dir_path in sorted(self.cache_dir.rglob("*"), reverse=True):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()

        logging.info(f"Cleared {count} cache files")
        return count

    def get_static_config(self) -> dict:
        """Get FastAPI static files configuration."""
        return {
            "directory": str(self.base_dir),
            "path": "/audio",
            "name": "audio_files"
        }


@asynccontextmanager
async def managed_audio_manager(*args, **kwargs):
    """Context manager for AudioManager with cleanup task."""
    manager = AudioManager(*args, **kwargs)
    await manager.start_cleanup_task()
    try:
        yield manager
    finally:
        await manager.stop_cleanup_task()
