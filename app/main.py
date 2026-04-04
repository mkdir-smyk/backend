from fastapi import FastAPI
from app.api.routes import router
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="A production-grade candidate verification engine.",
    version="1.0.0"
)

app.include_router(router)

@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.PROJECT_NAME}...")

@app.get("/health")
def health_check():
    return {"status": "healthy"}
