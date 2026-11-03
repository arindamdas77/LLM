
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

import requests

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "llm_chat.db"

OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "qwen2.5:3b"

REQUEST_TIMEOUT = (10, 600)
KEEP_ALIVE = "10m"


# ==========================================
# FASTAPI
# ==========================================

app = FastAPI(
    title="My Custom LLM",
    description="Local AI chatbot using Ollama, Qwen and FastAPI",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ==========================================
# DATABASE
# ==========================================

def get_db():

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    with get_db() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id)
                    REFERENCES chats(id)
                    ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id
            ON messages(chat_id, id)
        """)

        conn.execute("PRAGMA foreign_keys = ON")

        conn.commit()

    logger.info("SQLite database initialized")


def current_time():

    return datetime.now(timezone.utc).isoformat()


def create_chat(question):

    now = current_time()

    with get_db() as conn:

        cursor = conn.execute(
            """
            INSERT INTO chats (title, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (question[:50], now, now)
        )

        chat_id = cursor.lastrowid

        conn.commit()

        return chat_id


def chat_exists(chat_id):

    with get_db() as conn:

        result = conn.execute(
            "SELECT id FROM chats WHERE id = ?",
            (chat_id,)
        ).fetchone()

        return result is not None


def save_message(chat_id, role, content):

    now = current_time()

    with get_db() as conn:

        conn.execute(
            """
            INSERT INTO messages
            (chat_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, role, content, now)
        )

        conn.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (now, chat_id)
        )

        conn.commit()


def get_chat_messages(chat_id):

    with get_db() as conn:

        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE chat_id = ?
            ORDER BY id ASC
            """,
            (chat_id,)
        ).fetchall()

        return [dict(row) for row in rows]


# ==========================================
# REQUEST MODELS
# ==========================================

class ChatRequest(BaseModel):

    question: str = Field(
        ...,
        min_length=1,
        max_length=10000
    )

    chat_id: int | None = None


# ==========================================
# SSE HELPER
# ==========================================

def sse_event(data):

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ==========================================
# STARTUP
# ==========================================

@app.on_event("startup")
def startup_event():

    init_db()

    logger.info("My Custom LLM started")
    logger.info("Model: %s", MODEL_NAME)


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():

    return {
        "status": "running",
        "application": "My Custom LLM",
        "model": MODEL_NAME,
        "version": "3.0.0"
    }


# ==========================================
# HEALTH
# ==========================================

@app.get("/health")
def health_check():

    try:

        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=10
        )

        response.raise_for_status()

        models = response.json().get("models", [])

        available = any(
            model.get("name") == MODEL_NAME
            for model in models
        )

        return {
            "status": "healthy" if available else "degraded",
            "ollama": "connected",
            "model": MODEL_NAME,
            "model_available": available
        }

    except requests.RequestException as error:

        logger.error("Health check failed: %s", error)

        raise HTTPException(
            status_code=503,
            detail="Ollama is unavailable"
        )


# ==========================================
# MODEL INFORMATION
# ==========================================

@app.get("/model")
def model_info():

    try:

        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=10
        )

        response.raise_for_status()

        return {
            "model": MODEL_NAME,
            "available_models": response.json().get("models", [])
        }

    except requests.RequestException:

        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve model information"
        )


# ==========================================
# LIST CHATS
# ==========================================

@app.get("/chats")
def list_chats():

    with get_db() as conn:

        rows = conn.execute(
            """
            SELECT
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                COUNT(m.id) AS message_count
            FROM chats c
            LEFT JOIN messages m ON c.id = m.chat_id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            """
        ).fetchall()

        return {
            "chats": [dict(row) for row in rows]
        }


# ==========================================
# GET CHAT
# ==========================================

@app.get("/chats/{chat_id}")
def get_chat(chat_id: int):

    with get_db() as conn:

        chat = conn.execute(
            "SELECT * FROM chats WHERE id = ?",
            (chat_id,)
        ).fetchone()

        if not chat:

            raise HTTPException(
                status_code=404,
                detail="Chat not found"
            )

    return {
        "chat": dict(chat),
        "messages": get_chat_messages(chat_id)
    }


# ==========================================
# DELETE CHAT
# ==========================================

@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: int):

    with get_db() as conn:

        conn.execute("PRAGMA foreign_keys = ON")

        cursor = conn.execute(
            "DELETE FROM chats WHERE id = ?",
            (chat_id,)
        )

        if cursor.rowcount == 0:

            raise HTTPException(
                status_code=404,
                detail="Chat not found"
            )

        conn.commit()

    return {
        "status": "success",
        "message": "Chat deleted",
        "chat_id": chat_id
    }


# ==========================================
# STREAMING LLM ENDPOINT
# ==========================================

@app.post("/ask")
def ask_llm(request: ChatRequest):

    question = request.question.strip()

    if not question:

        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty"
        )

    # Create or validate conversation

    if request.chat_id is None:

        chat_id = create_chat(question)

    else:

        chat_id = request.chat_id

        if not chat_exists(chat_id):

            raise HTTPException(
                status_code=404,
                detail="Chat not found"
            )

    # Save user message

    save_message(
        chat_id,
        "user",
        question
    )

    # Build conversation context

    messages = get_chat_messages(chat_id)

    recent_messages = messages[-12:]

    prompt_parts = [
        "You are a helpful AI assistant. "
        "Answer clearly and accurately using Markdown. "
        "When writing code, use appropriate fenced code blocks."
    ]

    for message in recent_messages:

        role = (
            "Assistant"
            if message["role"] == "assistant"
            else "User"
        )

        prompt_parts.append(
            f"{role}: {message['content']}"
        )

    prompt_parts.append("Assistant:")

    prompt = "\n\n".join(prompt_parts)

    logger.info("Starting generation for chat %s", chat_id)

    def generate():

        full_answer = ""

        try:

            with requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": True,
                    "keep_alive": KEEP_ALIVE
                },
                stream=True,
                timeout=REQUEST_TIMEOUT
            ) as response:

                response.raise_for_status()

                for line in response.iter_lines():

                    if not line:
                        continue

                    data = json.loads(line)

                    token = data.get("response", "")

                    if token:

                        full_answer += token

                        yield sse_event({
                            "token": token
                        })

                    if data.get("done"):

                        save_message(
                            chat_id,
                            "assistant",
                            full_answer
                        )

                        yield sse_event({
                            "done": True,
                            "chat_id": chat_id,
                            "model": MODEL_NAME,
                            "eval_count": data.get("eval_count")
                        })

                        return

            raise RuntimeError(
                "Ollama ended without completing generation"
            )

        except Exception as error:

            logger.exception(
                "Generation failed for chat %s",
                chat_id
            )

            yield sse_event({
                "error": str(error)
            })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )

