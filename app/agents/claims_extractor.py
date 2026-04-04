import google.generativeai as genai
import json
from app.core.config import settings
from app.core.logger import get_logger
from app.models.schemas import ExtractedClaims

logger = get_logger(__name__)

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

async def extract_claims(resume_text: str) -> ExtractedClaims:
    """Uses Gemini to extract structured claims from the resume text."""
    if not settings.GEMINI_API_KEY:
        logger.warning("Gemini API key missing. Returning empty claims.")
        return ExtractedClaims()

    prompt = f"""
    You are an expert technical recruiter analyzing a resume.
    Extract the candidate's claims into the following strict JSON format. 
    Ensure the output is ONLY a valid JSON object matching this schema, without markdown formatting like ```json.
    
    {{
        "skills": ["Python", "FastAPI"],
        "projects": ["Built a distributed task queue", "E-commerce backend"],
        "github_links": ["https://github.com/user"],
        "platforms": ["LeetCode", "Codeforces"],
        "experience_dates": ["2020-2022", "2022-Present"]
    }}
    
    Resume Text:
    {resume_text}
    """
    
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # We use asyncio to run the blocking generation in a thread pool if needed
        # but since google-generativeai doesn't natively expose async endpoints for simple generate_content in all versions, 
        # we will run it directly (or async generation if supported: generate_content_async).
        response = await model.generate_content_async(prompt)
        text_resp = response.text
        
        # Clean up markdown code blocks if gemini outputs them
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:]
        if text_resp.endswith("```"):
            text_resp = text_resp[:-3]
            
        data = json.loads(text_resp.strip())
        return ExtractedClaims(**data)
        
    except Exception as e:
        logger.error(f"Error during claim extraction: {e}")
        return ExtractedClaims()
