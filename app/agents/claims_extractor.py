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
    You are a high-precision information extraction system.

    Your task is to extract verifiable, structured claims from a resume.

    ### EXTRACTION RULES (STRICT)

    - Output MUST be valid JSON only (no markdown, no explanations).
    - Do NOT hallucinate or infer missing data.
    - If a field is not present, return an empty list [].
    - Normalize all outputs:
    - Skills → concise technical terms (e.g., "Python", "FastAPI")
    - Projects → short descriptive phrases
    - Links → full valid URLs only
    - Platforms → standardized names (e.g., "LeetCode", "Codeforces")
    - Dates → normalized format (e.g., "2020-2022", "2022-Present")

    ### FIELDS TO EXTRACT

    Extract the following categories if present in the resume:

    1. skills → programming languages, frameworks, tools
    2. projects → personal or professional project descriptions
    3. github_links → any GitHub profile or repository links
    4. platforms → coding platforms (LeetCode, Codeforces, etc.)
    5. experience_dates → employment or project timelines
    6. github_username → exact username if mentioned or parsed from link (or null)
    7. leetcode_username → exact username if mentioned or parsed from link (or null)
    8. codeforces_username → exact username if mentioned or parsed from link (or null)

    ### OUTPUT SCHEMA

    Return ONLY this JSON structure:

    {{
    "skills": ["skill1", "skill2"],
    "projects": ["project1", "project2"],
    "github_links": ["link1"],
    "platforms": ["platform1"],
    "experience_dates": ["date1"],
    "github_username": "string or null",
    "leetcode_username": "string or null",
    "codeforces_username": "string or null"
    }}

    ### INPUT DATA

    Resume Text:
    \"\"\"
    {resume_text}
    \"\"\"
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
