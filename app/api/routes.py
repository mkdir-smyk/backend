from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from app.orchestration.orchestrator import process_candidate
from app.models.schemas import AnalysisResponse
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_candidate(
    resume: UploadFile = File(...),
    jd: UploadFile = File(...),
    github_username: Optional[str] = Form(None),
    leetcode_username: Optional[str] = Form(None),
    codeforces_username: Optional[str] = Form(None)
):
    if resume.content_type != "application/pdf" or jd.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    try:
        response = await process_candidate(
            resume, jd, github_username, leetcode_username, codeforces_username
        )
        return response
    except Exception as e:
        logger.error(f"Error processing upload: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during analysis")
