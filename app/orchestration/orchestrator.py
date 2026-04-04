from fastapi import UploadFile
import uuid
import asyncio
from app.agents.parser_agent import parse_pdf
from app.agents.claims_extractor import extract_claims
from app.agents.verification_agent import verify_claims
from app.agents.scoring_engine import compute_scores
from app.agents.llm_reasoner import reason_candidate
from app.models.schemas import AnalysisResponse
from app.core.logger import get_logger

logger = get_logger(__name__)

async def process_candidate(
    resume: UploadFile, 
    jd: UploadFile,
    github_username: str = None, 
    leetcode_username: str = None, 
    codeforces_username: str = None
) -> AnalysisResponse:
    
    candidate_id = str(uuid.uuid4())
    logger.info(f"Starting process for candidate {candidate_id}")
    
    # 1. Parse PDFs concurrently
    resume_text, jd_text = await asyncio.gather(
        parse_pdf(resume),
        parse_pdf(jd)
    )
    logger.info(f"Parsed PDFs for {candidate_id}")
    
    # 2. Extract Claims
    claims = await extract_claims(resume_text)
    logger.info(f"Extracted claims for {candidate_id}")
    
    # 3. Verify Claims
    verified_claims = await verify_claims(
        claims, github_username, leetcode_username, codeforces_username
    )
    logger.info(f"Verified claims for {candidate_id}")
    
    # 4. Scoring Engine
    scores = compute_scores(resume_text, jd_text, verified_claims)
    logger.info(f"Computed scores for {candidate_id}")
    
    # 5. LLM Reasoner
    final_analysis = await reason_candidate(
        resume_text, 
        jd_text, 
        claims.model_dump(), 
        verified_claims.model_dump(), 
        scores.model_dump(), 
        candidate_id
    )
    logger.info(f"Completed LLM reasoning for {candidate_id}")
    
    return final_analysis
