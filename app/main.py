from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import APP_TITLE, DATA_DIR
from app.database import engine, Base
from app.routers import export, frontend

app = FastAPI(title=APP_TITLE)

BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(frontend.router)
app.include_router(export.router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
