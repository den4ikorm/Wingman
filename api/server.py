import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine

app = FastAPI(title="Dietolog v2 API")

# CORS для Telegram Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Фронтенд отдаётся статикой
app.mount("/static", StaticFiles(directory="frontend"), name="static")


# --- МОДЕЛИ ---

class TaskDone(BaseModel):
    user_id: int
    task: str


class VibeUpdate(BaseModel):
    user_id: int
    vibe: str


# --- ЭНДПОИНТЫ ---

@app.get("/")
def root():
    return {"status": "Dietolog v2 API running"}


@app.get("/api/profile/{user_id}")
def get_profile(user_id: int):
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@app.get("/api/plan/{user_id}")
def get_plan(user_id: int):
    db = MemoryManager(user_id)
    plan = db.get_last_plan()
    vibe = db.get_vibe()
    css = db.get_vibe_css()
    return {
        "html": plan,
        "vibe": vibe,
        "css": css,
    }


@app.post("/api/task/done")
def task_done(body: TaskDone):
    db = MemoryManager(body.user_id)
    profile = db.get_profile()
    completed = profile.get("completed_tasks", [])
    completed.append(body.task)
    db.save_profile({"completed_tasks": completed})
    return {"status": "ok"}


@app.post("/api/vibe")
def update_vibe(body: VibeUpdate):
    if body.vibe not in ["spark", "observer", "twilight"]:
        raise HTTPException(status_code=400, detail="Invalid vibe")
    db = MemoryManager(body.user_id)
    db.set_vibe(body.vibe)
    return {"status": "ok", "vibe": body.vibe}


@app.get("/dashboard/{user_id}")
def dashboard(user_id: int):
    """Редирект на Mini App HTML"""
    from fastapi.responses import FileResponse
    return FileResponse("frontend/dashboard.html")
