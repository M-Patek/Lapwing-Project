"""
Memory Consolidation Script
Processes staged memories and promotes significant ones to long-term storage.
Run periodically (e.g., nightly via cron) or manually with `python run_consolidation.py`
"""
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from settings import Settings
from llm_provider import MultiProviderManager
from utils import load_or_initialize_json, save_json, safe_json_loads


def setup_consolidation_logging() -> None:
    """Setup logging for consolidation runs."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "consolidation.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


class MemoryConsolidator:
    """Consolidates staged memories into long-term storage."""

    def __init__(self, settings: Settings, api_manager: ApiClientManager):
        self.settings = settings
        self.api_manager = api_manager

    async def _evaluate_memories(
        self,
        staged_memories: List[dict]
    ) -> Optional[dict]:
        """
        Use LLM to evaluate which memories are significant.

        Args:
            staged_memories: List of staged memory entries

        Returns:
            Dictionary with new_preferences, new_dislikes, new_shared_memories
        """
        if not staged_memories:
            return None

        # Format memories for prompt
        memories_text = json.dumps(staged_memories, indent=2, ensure_ascii=False)

        prompt = f'''[TASK] Act as a Memory Arbiter.
Review these potential memories from conversations between Lapwing and her master.
Identify significant memories worth keeping as long-term core memories.

[CRITERIA] A memory is significant if it reveals:
- Core preferences or dislikes of the master
- Shared experiences with emotional weight
- Key personal information
- Moments defining their relationship

[INPUT DATA]
{memories_text}

[OUTPUT FORMAT]
Return JSON:
{{
    "new_preferences": ["..."],
    "new_dislikes": ["..."],
    "new_shared_memories": ["..."]
}}

Return empty arrays if none are significant.'''

        try:
            response = await self.api_manager.scene_client.generate_content(prompt)
            return safe_json_loads(response, {})
        except Exception as e:
            logging.error(f"Memory evaluation failed: {e}")
            return None

    def _merge_memories(
        self,
        long_term: dict,
        consolidated: dict
    ) -> bool:
        """
        Merge consolidated memories into long-term storage.

        Args:
            long_term: Current long-term memory dict
            consolidated: New memories to add

        Returns:
            True if any changes were made
        """
        updated = False

        # Ensure structure
        if "user_profile" not in long_term:
            long_term["user_profile"] = {}

        # Add preferences
        new_prefs = consolidated.get("new_preferences", [])
        if new_prefs:
            prefs = long_term["user_profile"].setdefault("preferences", [])
            for pref in new_prefs:
                if pref not in prefs:
                    prefs.append(pref)
                    updated = True
                    logging.info(f"Added preference: {pref}")

        # Add dislikes
        new_dislikes = consolidated.get("new_dislikes", [])
        if new_dislikes:
            dislikes = long_term["user_profile"].setdefault("dislikes", [])
            for dislike in new_dislikes:
                if dislike not in dislikes:
                    dislikes.append(dislike)
                    updated = True
                    logging.info(f"Added dislike: {dislike}")

        # Add shared memories
        new_mems = consolidated.get("new_shared_memories", [])
        if new_mems:
            mems = long_term.setdefault("shared_memories", [])
            for mem in new_mems:
                if mem not in mems:
                    mems.append(mem)
                    updated = True
                    logging.info(f"Added shared memory: {mem[:100]}...")

        return updated

    def _archive_staged(
        self,
        staged_memories: List[dict],
        consolidated: dict
    ) -> None:
        """
        Archive processed memories.
        Keeps rejected memories in a separate archive file for review.
        """
        archive_file = Path("json/archived_memories.json")

        # Load existing archive
        archive = load_or_initialize_json(archive_file, {"archived": []})

        # Add processed memories with timestamp
        archive["archived"].append({
            "processed_at": datetime.now().isoformat(),
            "consolidated": consolidated,
            "staged_count": len(staged_memories)
        })

        save_json(archive_file, archive)
        logging.info(f"Archived {len(staged_memories)} processed memories")

    async def consolidate(self) -> Dict[str, any]:
        """
        Run full consolidation process.

        Returns:
            Statistics about the consolidation run
        """
        stats = {
            "staged_count": 0,
            "added_preferences": 0,
            "added_dislikes": 0,
            "added_memories": 0,
            "success": False,
            "timestamp": datetime.now().isoformat()
        }

        try:
            # Load staged memories
            staging_data = load_or_initialize_json(
                self.settings.STAGING_FILE,
                {"potential_memories": []}
            )

            staged = staging_data.get("potential_memories", [])
            stats["staged_count"] = len(staged)

            if not staged:
                logging.info("No memories to consolidate")
                stats["success"] = True
                return stats

            logging.info(f"Consolidating {len(staged)} staged memories...")

            # Evaluate memories
            consolidated = await self._evaluate_memories(staged)

            if not consolidated:
                logging.warning("Memory evaluation returned no results")
                return stats

            # Load long-term memory
            long_term = load_or_initialize_json(
                self.settings.MEMORY_FILE,
                {}
            )

            # Merge memories
            updated = self._merge_memories(long_term, consolidated)

            if updated:
                save_json(self.settings.MEMORY_FILE, long_term)

            # Update stats
            stats["added_preferences"] = len(consolidated.get("new_preferences", []))
            stats["added_dislikes"] = len(consolidated.get("new_dislikes", []))
            stats["added_memories"] = len(consolidated.get("new_shared_memories", []))
            stats["success"] = True

            # Clear staging
            save_json(self.settings.STAGING_FILE, {"potential_memories": []})

            # Archive
            self._archive_staged(staged, consolidated)

            logging.info(
                f"Consolidation complete: "
                f"+{stats['added_preferences']} prefs, "
                f"+{stats['added_dislikes']} dislikes, "
                f"+{stats['added_memories']} memories"
            )

        except Exception as e:
            logging.error(f"Consolidation failed: {e}", exc_info=True)
            stats["error"] = str(e)

        return stats


async def main():
    """Entry point for consolidation script."""
    load_dotenv()
    setup_consolidation_logging()

    logging.info("=" * 50)
    logging.info("Memory Consolidation Started")
    logging.info("=" * 50)

    settings = Settings()
    api_manager = ApiClientManager(settings)

    consolidator = MemoryConsolidator(settings, api_manager)
    stats = await consolidator.consolidate()

    logging.info(f"Stats: {json.dumps(stats, indent=2)}")

    # Cleanup
    await api_manager.close()

    return stats


if __name__ == "__main__":
    asyncio.run(main())
