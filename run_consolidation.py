"""
Entry point for memory consolidation.
Run: python run_consolidation.py
"""

import asyncio
import sys
from memory_consolidation import main

if __name__ == "__main__":
    # Just delegate to the main consolidation logic
    stats = asyncio.run(main())
    sys.exit(0 if stats.get("success") else 1)
