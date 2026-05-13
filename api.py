"""
FastAPI Entry Point for Lapwing with Voice Support
Provides REST API and WebSocket endpoints for chatting with Lapwing.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from main import Lapwing, setup_logging
from tts_client import LapwingTTS, EmotionPreset
from audio_manager import AudioManager, managed_audio_manager

# Load environment variables
load_dotenv()
setup_logging()

# Ensure required directories exist
Path("audio").mkdir(exist_ok=True)
Path("json").mkdir(exist_ok=True)

# Global instances (initialized on startup)
lapwing_instance: Optional[Lapwing] = None
tts_instance: Optional[LapwingTTS] = None
audio_manager: Optional[AudioManager] = None

# WebSocket connection manager
class ConnectionManager:
    """Manage WebSocket connections for real-time updates"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logging.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logging.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logging.error(f"Failed to send WebSocket message: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logging.error(f"Failed to send personal message: {e}")


manager = ConnectionManager()


# ============================================================================
# Request/Response Models
# ============================================================================

class UserInput(BaseModel):
    """User input model."""
    message: str = Field(..., min_length=0, max_length=10000, description="User's message to Lapwing")


class LapwingResponse(BaseModel):
    """Lapwing text response model."""
    reply: str = Field(..., description="Lapwing's response text")
    eii: Optional[float] = Field(None, description="Current emotional intensity index (0-100)")


class VoiceResponse(LapwingResponse):
    """Lapwing response with voice."""
    audio_url: Optional[str] = Field(None, description="URL to generated audio file")


class VoiceRequest(BaseModel):
    """Direct TTS request."""
    text: str = Field(..., min_length=1, max_length=5000, description="Text to synthesize")
    eii: Optional[float] = Field(None, ge=0, le=100, description="EII value (0-100). Auto-detects emotion if not provided.")
    emotion: Optional[str] = Field(None, description="Override emotion: sad, calm, neutral, happy, excited")
    use_cache: bool = Field(True, description="Use cached audio if available")


class VoiceResponseDirect(BaseModel):
    """Direct TTS response."""
    audio_url: str = Field(..., description="URL to audio file")
    emotion_used: str = Field(..., description="Emotion preset used")
    cached: bool = Field(..., description="Whether audio was cached")


class StatsResponse(BaseModel):
    """Statistics response model."""
    emotional_state: dict
    memory: dict
    proactive: dict
    dreaming: dict
    world_state: dict


class AudioStatsResponse(BaseModel):
    """Audio storage statistics."""
    total_files: int
    total_size_mb: float
    cached_files: int
    generated_files: int


class GoalRequest(BaseModel):
    """Create goal request."""
    description: str = Field(..., min_length=1, max_length=500)
    priority: int = Field(5, ge=1, le=10)


class GoalResponse(BaseModel):
    """Goal response."""
    goals: List[dict]
    total_active: int
    total_completed: int


class ProactiveStatusResponse(BaseModel):
    """Proactive system status."""
    boredom: float
    state: str
    minutes_since_interaction: float
    active_goals: int
    completed_goals: int


class DreamsResponse(BaseModel):
    """Recent dreams."""
    dreams: List[dict]
    total: int


class InsightsResponse(BaseModel):
    """Generated insights."""
    insights: List[dict]
    total: int


# ============================================================================
# Lifespan Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Lifespan context manager for startup/shutdown.
    Handles initialization and cleanup.
    """
    global lapwing_instance, tts_instance, audio_manager

    logging.info("=" * 50)
    logging.info("Starting up Lapwing with Voice...")
    logging.info("=" * 50)

    try:
        # Initialize Audio Manager with cleanup task
        audio_manager = AudioManager()
        await audio_manager.start_cleanup_task()
        logging.info("Audio manager initialized")

        # Initialize TTS client
        tts_base_url = "http://localhost:9872"  # GPT SoVITS API
        tts_instance = LapwingTTS(base_url=tts_base_url)

        # Check TTS health
        tts_health = await tts_instance.client.health_check()
        if tts_health.get("status") == "healthy":
            logging.info(f"TTS service connected: {tts_base_url}")
        else:
            logging.warning(f"TTS service unavailable: {tts_health}")

        # Create Lapwing instance
        lapwing_instance = Lapwing()
        await lapwing_instance.initialize()
        logging.info("Lapwing core initialized")

        # Start ALL background tasks
        await lapwing_instance.start_background_tasks()

        logging.info("=" * 50)
        logging.info("Lapwing is ready!")
        logging.info("=" * 50)

        yield

    except Exception as e:
        logging.error(f"Failed to start Lapwing: {e}", exc_info=True)
        raise

    finally:
        # Cleanup
        logging.info("Shutting down Lapwing...")

        if tts_instance:
            await tts_instance.close()
            logging.info("TTS client closed")

        if lapwing_instance and lapwing_instance.api_manager:
            await lapwing_instance.api_manager.close()
            logging.info("API clients closed")

        if audio_manager:
            await audio_manager.stop_cleanup_task()
            logging.info("Audio manager stopped")

        logging.info("Lapwing stopped.")


# ============================================================================
# FastAPI App Creation
# ============================================================================

app = FastAPI(
    title="Lapwing API",
    description="AI character with emotional intelligence, memory, and voice",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for audio (after app creation)
app.mount("/audio", StaticFiles(directory="audio"), name="audio_files")


# ============================================================================
# Health & Stats Endpoints
# ============================================================================

@app.get("/health", summary="Health check")
async def health_check() -> dict:
    """Check if the API is healthy."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    # Check TTS
    tts_status = "unknown"
    if tts_instance:
        tts_health = await tts_instance.client.health_check()
        tts_status = tts_health.get("status", "unknown")

    return {
        "status": "healthy",
        "eii": lapwing_instance.emotional_state.get_eii(),
        "tts": tts_status
    }


@app.get("/stats", response_model=StatsResponse, summary="Get current statistics")
async def get_stats() -> StatsResponse:
    """
    Get current statistics about Lapwing's state.
    Includes emotional state, memory usage, and world state.
    """
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    try:
        stats = await lapwing_instance.get_stats()
        return StatsResponse(**stats)
    except Exception as e:
        logging.error(f"Stats error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error getting stats")


@app.get("/audio/stats", response_model=AudioStatsResponse, summary="Get audio storage statistics")
async def get_audio_stats() -> AudioStatsResponse:
    """Get audio file storage statistics."""
    if audio_manager is None:
        raise HTTPException(status_code=503, detail="Audio manager not initialized")

    stats = await audio_manager.get_stats()
    return AudioStatsResponse(
        total_files=stats.total_files,
        total_size_mb=round(stats.total_size_mb, 2),
        cached_files=stats.cached_files,
        generated_files=stats.generated_files
    )


# ============================================================================
# Chat Endpoints
# ============================================================================

@app.post("/chat", response_model=LapwingResponse, summary="Chat with Lapwing (text only)")
async def chat_with_lapwing(user_input: UserInput) -> LapwingResponse:
    """
    Send a message to Lapwing and get her text response.

    - **message**: Your message to Lapwing
    - Returns Lapwing's reply and current emotional state
    """
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    try:
        response_text = await lapwing_instance.get_response(user_input.message)
        return LapwingResponse(
            reply=response_text,
            eii=lapwing_instance.emotional_state.get_eii()
        )
    except Exception as e:
        logging.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error generating response")


@app.post("/chat/voice", response_model=VoiceResponse, summary="Chat with Lapwing (with voice)")
async def chat_with_voice(user_input: UserInput) -> VoiceResponse:
    """
    Send a message to Lapwing and get her response with voice.

    - **message**: Your message to Lapwing
    - Returns Lapwing's text reply, emotional state, and audio URL
    - Audio is generated based on Lapwing's current emotional state (EII)
    """
    if lapwing_instance is None or tts_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing or TTS not initialized")

    try:
        # Generate text response
        response_text = await lapwing_instance.get_response(user_input.message)
        current_eii = lapwing_instance.emotional_state.get_eii()

        # Generate voice based on emotional state
        audio_url = await tts_instance.speak(
            text=response_text,
            eii=current_eii,
            use_cache=True
        )

        return VoiceResponse(
            reply=response_text,
            eii=current_eii,
            audio_url=audio_url
        )

    except Exception as e:
        logging.error(f"Chat voice error: {e}", exc_info=True)
        # Fallback to text-only response
        try:
            response_text = await lapwing_instance.get_response(user_input.message)
            return VoiceResponse(
                reply=response_text,
                eii=lapwing_instance.emotional_state.get_eii(),
                audio_url=None
            )
        except:
            raise HTTPException(status_code=500, detail="Internal error generating response")


# ============================================================================
# TTS Endpoints
# ============================================================================

@app.post("/tts", response_model=VoiceResponseDirect, summary="Text-to-speech")
async def text_to_speech(request: VoiceRequest) -> VoiceResponseDirect:
    """
    Convert text to speech with emotional tone.

    - **text**: Text to synthesize (max 5000 chars)
    - **eii**: Emotional Intensity Index (0-100). Auto-detects emotion if not provided.
    - **emotion**: Override emotion preset: sad, calm, neutral, happy, excited
    - **use_cache**: Whether to use cached audio if available

    Returns URL to audio file and emotion used.
    """
    if tts_instance is None:
        raise HTTPException(status_code=503, detail="TTS not initialized")

    try:
        # Determine emotion
        emotion_preset = None
        if request.emotion:
            try:
                emotion_preset = EmotionPreset(request.emotion.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid emotion: {request.emotion}. Use: sad, calm, neutral, happy, excited"
                )

        # Generate audio
        from tts_client import GPTSoVITSClient
        audio_path = await tts_instance.client.synthesize(
            text=request.text,
            emotion_preset=emotion_preset,
            eii=request.eii,
            use_cache=request.use_cache
        )

        # Convert to URL
        try:
            relative_path = audio_path.relative_to(Path.cwd())
            audio_url = f"/{relative_path.as_posix()}"
        except ValueError:
            audio_url = f"/{audio_path.as_posix()}"

        # Determine emotion used
        emotion_used = emotion_preset.value if emotion_preset else "auto"
        if emotion_used == "auto" and request.eii is not None:
            detected = tts_instance.client.eii_to_emotion(request.eii)
            emotion_used = detected.value

        # Check if cached (based on existence before generation)
        # This is simplified; actual cache check is internal to synthesize
        cached = False  # Will be True if cache hit

        return VoiceResponseDirect(
            audio_url=audio_url,
            emotion_used=emotion_used,
            cached=cached
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"TTS error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


@app.get("/tts/emotions", summary="List available emotions")
async def list_emotions() -> dict:
    """Get list of available emotion presets for TTS."""
    return {
        "emotions": [
            {"name": "sad", "eii_range": "0-20", "description": "悲伤、低落"},
            {"name": "calm", "eii_range": "20-40", "description": "平静、思考"},
            {"name": "neutral", "eii_range": "40-60", "description": "温和、日常"},
            {"name": "happy", "eii_range": "60-80", "description": "开心、活泼"},
            {"name": "excited", "eii_range": "80-100", "description": "激动、兴奋"}
        ],
        "note": "EII = Emotional Intensity Index. Can use 'eii' param or specific 'emotion' in TTS requests."
    }


# ============================================================================
# Audio File Management
# ============================================================================

@app.get("/audio/{path:path}", summary="Serve audio files")
async def serve_audio(path: str):
    """Direct audio file access (also available via /audio static mount)."""
    file_path = Path("audio") / path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(file_path)


@app.post("/memory/clear", summary="Clear working memory")
async def clear_working_memory() -> dict:
    """Clear the current conversation working memory."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    lapwing_instance.memory_manager.clear_working_memory()
    return {"status": "working memory cleared"}


@app.post("/audio/clear-cache", summary="Clear audio cache")
async def clear_audio_cache() -> dict:
    """Manually clear all cached audio files."""
    if audio_manager is None:
        raise HTTPException(status_code=503, detail="Audio manager not initialized")

    count = await audio_manager.clear_cache()
    return {"status": "cache cleared", "files_deleted": count}


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication.

    Features:
    - Receive proactive messages instantly
    - Real-time status updates
    - Bidirectional chat
    """
    await manager.connect(websocket)
    try:
        # Send initial status
        if lapwing_instance:
            await websocket.send_json({
                "type": "status",
                "data": {
                    "eii": lapwing_instance.emotional_state.get_eii(),
                    "connected": True
                }
            })

        while True:
            # Wait for messages from client
            data = await websocket.receive_json()
            message_type = data.get("type", "chat")

            if message_type == "chat":
                # Handle chat message
                user_message = data.get("message", "")
                if user_message and lapwing_instance:
                    response = await lapwing_instance.get_response(user_message)
                    await websocket.send_json({
                        "type": "chat_response",
                        "data": {
                            "reply": response,
                            "eii": lapwing_instance.emotional_state.get_eii()
                        }
                    })

            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def broadcast_proactive_message(message: str):
    """Broadcast proactive message to all WebSocket clients"""
    await manager.broadcast({
        "type": "proactive_message",
        "data": {
            "message": message,
            "timestamp": asyncio.get_event_loop().time()
        }
    })


async def broadcast_status_update():
    """Broadcast status update to all clients"""
    if lapwing_instance:
        await manager.broadcast({
            "type": "status_update",
            "data": {
                "eii": lapwing_instance.emotional_state.get_eii(),
                "boredom": lapwing_instance.proactive_system.get_status()
            }
        })


# ============================================================================
# Proactive & Goals Endpoints
# ============================================================================

@app.get("/proactive/status", response_model=ProactiveStatusResponse, summary="Get proactive system status")
async def get_proactive_status() -> ProactiveStatusResponse:
    """Get current boredom level and proactive state."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    status = lapwing_instance.proactive_system.get_status()
    return ProactiveStatusResponse(**status)


@app.post("/goals", summary="Create a goal")
async def create_goal(request: GoalRequest) -> dict:
    """Create a new goal for Lapwing."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    goal = lapwing_instance.proactive_system.goal_manager.create_goal(
        request.description,
        request.priority
    )
    return {
        "id": goal.id,
        "description": goal.description,
        "priority": goal.priority,
        "created_at": goal.created_at.isoformat()
    }


@app.get("/goals", response_model=GoalResponse, summary="List active goals")
async def list_goals() -> GoalResponse:
    """List Lapwing's active goals."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    active = lapwing_instance.proactive_system.goal_manager.get_active_goals()
    completed = lapwing_instance.proactive_system.goal_manager.completed_goals

    return GoalResponse(
        goals=[
            {
                "id": g.id,
                "description": g.description,
                "priority": g.priority,
                "progress": g.progress,
                "status": g.status
            }
            for g in active
        ],
        total_active=len(active),
        total_completed=len(completed)
    )


@app.get("/proactive/messages", summary="Get pending proactive messages")
async def get_proactive_messages() -> dict:
    """Get messages Lapwing wants to send proactively (clears queue)."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    messages = lapwing_instance.get_pending_proactive_messages()

    # Also broadcast via WebSocket
    for msg in messages:
        await broadcast_proactive_message(msg)

    return {"messages": messages, "count": len(messages)}


# ============================================================================
# Dreaming & Insights Endpoints
# ============================================================================

@app.get("/dreams", response_model=DreamsResponse, summary="Get recent dreams")
async def get_recent_dreams(limit: int = 5) -> DreamsResponse:
    """Get Lapwing's recent dreams."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    dreams = lapwing_instance.dreaming_system.get_recent_dreams(limit)
    return DreamsResponse(
        dreams=[
            {
                "timestamp": d.timestamp.isoformat(),
                "phase": d.phase.name,
                "content": d.content[:200] + "..." if len(d.content) > 200 else d.content,
                "insights_count": len(d.insights)
            }
            for d in dreams
        ],
        total=len(lapwing_instance.dreaming_system.dreams)
    )


@app.get("/insights", response_model=InsightsResponse, summary="Get generated insights")
async def get_insights(limit: int = 10) -> InsightsResponse:
    """Get Lapwing's insights about Master."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    insights = lapwing_instance.dreaming_system.get_top_insights(limit)
    return InsightsResponse(
        insights=[
            {
                "content": i.content,
                "emotional_tone": i.emotional_tone,
                "importance": i.importance,
                "generated_at": i.generated_at.isoformat()
            }
            for i in insights
        ],
        total=len(lapwing_instance.dreaming_system.insights)
    )


@app.post("/dreams/reflect", summary="Generate reflection on topic")
async def generate_reflection(topic: str) -> dict:
    """Ask Lapwing to reflect on a specific topic."""
    if lapwing_instance is None:
        raise HTTPException(status_code=503, detail="Lapwing not initialized")

    reflection = await lapwing_instance.dreaming_system.generate_reflection(
        topic=topic,
        context={"trigger": "user_request"}
    )
    return {
        "topic": reflection.topic,
        "thoughts": reflection.thoughts,
        "timestamp": reflection.timestamp.isoformat()
    }
