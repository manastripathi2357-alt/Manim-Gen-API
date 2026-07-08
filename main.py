from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from generate_scene import generate_animation_video
import os
import uuid
from auth import create_access_token, get_current_user, verify_password, get_password_hash
from sqlalchemy.orm import Session
from database import get_db, engine
from models import Base, User, Task

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Animatrix AI Video Generator")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

# --- Models ---
class GenerateRequest(BaseModel):
    prompt: str

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class GoogleLoginRequest(BaseModel):
    credential: str

from google.oauth2 import id_token
from google.auth.transport import requests

GOOGLE_CLIENT_ID = "295602549979-v72k4qunp6gqfb8meggbatpckahk0rct.apps.googleusercontent.com"

# --- Endpoints ---
@app.post("/api/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(request.password)
    user = User(username=request.username, hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/google-login")
def google_login(request: GoogleLoginRequest, db: Session = Depends(get_db)):
    try:
        # Verify the token
        idinfo = id_token.verify_oauth2_token(request.credential, requests.Request(), GOOGLE_CLIENT_ID)
        
        email = idinfo['email']
        
        # Check if user exists
        user = db.query(User).filter(User.username == email).first()
        if not user:
            # Register them automatically. Use a dummy hashed password.
            hashed_password = get_password_hash(str(uuid.uuid4()))
            user = User(username=email, hashed_password=hashed_password)
            db.add(user)
            db.commit()
            db.refresh(user)
            
        access_token = create_access_token(data={"sub": user.username})
        return {"access_token": access_token, "token_type": "bearer", "username": user.username}
        
    except ValueError:
        # Invalid token
        raise HTTPException(status_code=400, detail="Invalid Google token")

@app.post("/api/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/generate")
def generate_video(request: GenerateRequest, background_tasks: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task_id = str(uuid.uuid4())
    
    new_task = Task(id=task_id, user_id=user.id, prompt=request.prompt, status="processing")
    db.add(new_task)
    db.commit()
    
    # Spawn background task
    background_tasks.add_task(generate_animation_video, request.prompt, task_id)
    
    return {"status": "success", "task_id": task_id}

@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": task.status, "video_url": task.video_url, "error": task.error, "code": task.code}

@app.get("/api/history")
def get_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tasks = db.query(Task).filter(Task.user_id == user.id).order_by(Task.created_at.desc()).all()
    return [{"id": t.id, "prompt": t.prompt, "status": t.status, "video_url": t.video_url, "code": t.code, "created_at": t.created_at} for t in tasks]

# Serve frontend at the root (must be placed after all API routes!)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
