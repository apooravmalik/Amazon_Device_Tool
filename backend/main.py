# backend/main.py

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import os

from logger import get_logger
from config import APP_HOST, APP_PORT, LOG_LEVEL
from routes import router as api_router
from services.scheduler_service import start_scheduler
from database_setup import init_sqlite_db

logger = get_logger(__name__)

# --- NEW: Startup Event Handler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    logger.info("Application starting up...")
    
    # 1. Initialize the SQLite DB (creates tables if they don't exist)
    #    We need a new function in database_setup for this
    #    For now, we assume init_sqlite_db() is safe to call
    #    (or you can create a new create_tables_if_not_exist())
    logger.info("Initializing SQLite database...")
    init_sqlite_db() # Note: Your current setup deletes the DB. Be careful.
    
    # 2. Start the background scheduler
    logger.info("Starting scheduler thread...")
    start_scheduler()
    
    yield
    
    # Code to run on shutdown (if any)
    logger.info("Application shutting down...")

# --- App Setup ---
app = FastAPI(lifespan=lifespan)

# --- Mount Frontend ---
# This assumes your 'frontend' folder is one level up
# Adjust the path if your structure is different

# Get the directory of the current file (backend/)
backend_dir = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory (root)
root_dir = os.path.dirname(backend_dir)
# Path to the frontend directory
frontend_dir = os.path.join(root_dir, "frontend")

if not os.path.exists(frontend_dir):
    logger.warning(f"Frontend directory not found at: {frontend_dir}")
    logger.warning("Please check your file structure. Serving API only.")
else:
    logger.info(f"Serving static files from: {frontend_dir}")
    # Mount static files (css, js)
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    
    # Setup templates for index.html
    templates = Jinja2Templates(directory=frontend_dir)

    @app.get("/", response_class=HTMLResponse)
    async def serve_home(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

# --- Include API Routes ---
app.include_router(api_router, prefix="/api")

# --- Run the App ---
if __name__ == "__main__":
    logger.info(f"Starting server on {APP_HOST}:{APP_PORT} with log level {LOG_LEVEL}")
    uvicorn.run(
        "main:app",
        host=APP_HOST,
        port=APP_PORT,
        log_level=LOG_LEVEL.lower(),
        reload=True # Set to False in production
    )