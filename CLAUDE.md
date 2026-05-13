# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lapwing is an AI character simulation implementing digital emotions through a multi-layered memory system and emotional state tracking. Uses OpenAI-compatible APIs (OpenAI, OpenRouter, Together, etc.) for LLM and embeddings.

**New in v2.0:**
- **Proactive Behavior System**: Lapwing can initiate conversations when bored
- **Weighted Memory System**: Time decay + emotional weighting for memory retrieval
- **Dreaming System**: Off-line memory consolidation and insight generation
- **Voice Integration**: GPT SoVITS TTS with emotional mapping

## Development Commands

**Install dependencies:**
```bash
poetry install
# OR
pip install -r requirements.txt
```

**Set up environment:**
```bash
# Copy .env and fill in your API key
cp .env.example .env
# Edit .env with your OPENAI_API_KEY and optional OPENAI_BASE_URL
```

**Run the API server (development):**
```bash
uvicorn api:app --reload --port 8000
```

**Run tests:**
```bash
pytest
pytest tests/test_main.py -v
```

**Run memory consolidation (one-off script):**
```bash
python run_consolidation.py
```

**Docker build:**
```bash
docker build -t lapwing .
docker run -p 80:80 --env-file .env lapwing
```

**Start GPT SoVITS for voice:**
```bash
cd gpt-sovits
docker-compose up -d
```

## Architecture

### Core Components

**Lapwing Class (`main.py`)**: Central orchestrator with:
- `EmotionalState`: EII (Emotional Intensity Index 0-100) and foundation
- `WeightedMemoryManager`: Time-decay + emotion-weighted memory retrieval
- `BoredomSystem`: Proactive behavior when idle
- `DreamingSystem`: Off-line memory consolidation and insights
- Async chat flow with emotional impact analysis

**Memory System (`memory_weighted.py`)**: Three-tier weighted memory:
- **Working Memory**: In-memory deque (10 turns)
- **Short-term Memory**: JSON file (recent events)
- **Long-term Memory**: FAISS index + weighted metadata
  - Time decay: Exponential with 30-day half-life
  - Emotional weighting: High-emotion memories get 1.5x boost
  - Access frequency: Frequently accessed memories decay slower
  - Retrieval scoring: `0.4*similarity + 0.3*recency + 0.3*emotional_match`

**Proactive System (`proactive_system.py`)**:
- **Boredom accumulation**: Increases when idle, decreases on interaction
- **Time acceleration**: 5min idle → 1.5x, 30min → 2x, 2hr → 3x
- **Goal Manager**: Lapwing can have goals and report progress
- **Intent library**: 7 proactive behaviors (share, ask, express missing, etc.)
- **Cooldown system**: Prevents spam, each intent has independent cooldown

**Dreaming System (`dreaming_system.py`)**:
- **Trigger**: After 30 min idle, with increasing probability
- **Five phases**: Memory review → Emotion processing → Pattern recognition → Insight generation → Narrative dream
- **Insights**: Automatic generation of patterns about Master
- **Memory compression**: Consolidates similar memories
- **Emotional aftermath**: Dreams affect waking emotional state

**ApiClientManager (`api_client.py`)**: OpenAI-compatible clients:
- `chat_client`: Main chat (GPT-4o)
- `scene_client`: Background tasks (GPT-4o-mini)
- `embedding_client`: Embeddings (text-embedding-3-small)

**WorldStateUpdater (`world_events.py`)**: Background task every 15 minutes:
- `WorldClock`: Paris timezone tracking
- `WeatherService`: Open-Meteo API integration
- `SocialManager`: Simulated friends, projects, social events

### Memory System Flow

```
User Input → Emotional Impact Analysis (-10 to +10)
    ↓
Update EII → Save emotional state
    ↓
Retrieve Memories (with weights):
  - Working: Last 10 turns
  - Short-term: Recent events from JSON
  - Long-term: FAISS RAG with scoring:
    * Similarity (40%)
    * Recency with time decay (30%)
    * Emotional match (30%)
    ↓
Generate CoT Response → Extract final answer
    ↓
Store in Working Memory
Add to Weighted Memory (with EII + emotional intensity)
Stage for consolidation
Save Session State
```

### Proactive Behavior Flow

```
Idle → Boredom accumulates (0.5/sec base)
    ↓
Threshold check every 60s:
  - Boredom 30-60: 10% chance
  - Boredom 60-85: 30% chance
  - Boredom 85+: 60% chance
    ↓
Select intent (weighted by priority)
    ↓
Generate message → Queue for delivery
    ↓
Boredom -= 20 (relief from expressing)
```

### Dreaming Flow

```
Idle 30+ minutes → Dream trigger
    ↓
Five-phase dream:
  1. Memory review: Select and reflect on memories
  2. Emotion processing: Transform emotions to imagery
  3. Pattern recognition: Find connections
  4. Insight generation: Create insights about Master
  5. Narrative dream: Generate poetic dream scene
    ↓
Save dream + insights
Update emotional state (aftermath)
Compress redundant memories
```

### Configuration

**Environment Variables (`.env`):**
- `OPENAI_API_KEY` - Required for OpenAI-compatible APIs
- `OPENAI_BASE_URL` - Optional (default: `https://api.openai.com/v1`)

**Model Configuration (`settings.py`):**
- `CHAT_MODEL` - Main conversation (default: gpt-4o)
- `SCENE_MODEL` - Background/emotional analysis (default: gpt-4o-mini)
- `EMBEDDING_MODEL` - Embeddings (default: text-embedding-3-small)

**Key Constants:**
- `EII_BASELINE = 53` - Default emotional baseline
- `TEMPERATURE = 0.95` - LLM temperature
- `WORKING_MEMORY_SIZE = 10` - Working memory capacity
- `LONG_TERM_RETRIEVAL_K = 3` - Number of memories to retrieve
- `DECAY_HALF_LIFE_DAYS = 30` - Memory time decay half-life

### File Structure

```
├── api.py                 # FastAPI entry with lifespan management
├── main.py                # Core Lapwing class
├── memory_weighted.py     # WeightedMemoryManager with FAISS
├── proactive_system.py    # BoredomSystem + GoalManager
├── dreaming_system.py     # DreamingSystem + insight generation
├── tts_client.py          # GPT SoVITS TTS client
├── audio_manager.py       # Audio file management
├── api_client.py          # OpenAI-compatible client manager
├── world_events.py        # World state simulation
├── memory_consolidation.py # Nightly memory processing
├── run_consolidation.py   # Entry point for consolidation
├── settings.py            # Pydantic-settings configuration
├── utils.py               # JSON utilities + helpers
├── prompts/               # Jinja2 templates and text files
│   ├── base_context.jinja2
│   ├── cot_prompt.jinja2
│   ├── event_prompts.jinja2
│   ├── persona.txt        # <- NEVER MODIFY
│   └── world_lore.txt     # <- NEVER MODIFY
├── json/                  # Runtime data (memory files)
├── gpt-sovits/           # GPT SoVITS deployment
│   ├── docker-compose.yml
│   └── README.md
└── audio/                 # Generated audio files
```

### API Endpoints

**Chat:**
- `POST /chat` - Text chat
- `POST /chat/voice` - Chat with voice response

**Voice/TTS:**
- `POST /tts` - Direct text-to-speech
- `GET /tts/emotions` - List emotion presets

**Proactive:**
- `GET /proactive/status` - Boredom level and state
- `POST /goals` - Create a goal for Lapwing
- `GET /goals` - List active goals
- `GET /proactive/messages` - Get queued proactive messages

**Dreaming:**
- `GET /dreams` - Recent dreams
- `GET /insights` - Generated insights about Master
- `POST /dreams/reflect` - Generate reflection on topic

**Management:**
- `GET /health` - Health check with EII
- `GET /stats` - Full system statistics
- `GET /audio/stats` - Audio storage stats
- `POST /memory/clear` - Clear working memory
- `POST /audio/clear-cache` - Clear audio cache

### Async Patterns

- FastAPI uses `lifespan` context manager for startup/shutdown
- `Lapwing.start_background_tasks()` starts all loops
- Background tasks: WorldUpdater, BoredomSystem, DreamingSystem
- Memory retrieval is async (embeddings API)
- FAISS operations are CPU-bound but wrapped for consistency

### Error Handling

- All API calls wrapped with try/except and logged
- Emotional impact failures return 0 (neutral)
- Memory retrieval failures return fallback messages
- LLM response extraction has multiple fallback strategies

### Testing

Tests use pytest-asyncio with extensive mocking:
- Mock Settings, ApiClientManager, MemoryManager
- Test EmotionalState calculations
- Test emotional impact analysis with mocked APIs
- Test JSON parsing utilities

## Important Notes

**Never modify:**
- `prompts/persona.txt` - Core character personality
- `prompts/world_lore.txt` - World setting and background

These files define Lapwing's fundamental character and should only be changed with explicit user direction.
