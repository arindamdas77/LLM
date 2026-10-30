from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

app = FastAPI(
    title="My Custom LLM",
    description="My first locally hosted LLM API",
    version="1.0.0"
)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:3b"


class ChatRequest(BaseModel):
    question: str


@app.get("/")
def home():
    return {
        "status": "running",
        "model": MODEL_NAME,
        "message": "My LLM API is working"
    }


@app.post("/ask")
def ask_llm(request: ChatRequest):

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": request.question,
                "stream": False
            },
            timeout=180
        )

        response.raise_for_status()

        result = response.json()

        return {
            "question": request.question,
            "answer": result["response"],
            "model": MODEL_NAME
        }

    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama connection failed: {error}"
        )
