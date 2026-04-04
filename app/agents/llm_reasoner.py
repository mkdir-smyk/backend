import google.generativeai as genai
import json
from app.core.config import settings
from app.core.logger import get_logger
from app.models.schemas import AnalysisResponse, CandidateSummary, CandidateScores, CandidateAssessments

logger = get_logger(__name__)

async def reason_candidate(resume_text: str, jd_text: str, extracted_claims: dict, verified_claims: dict, scores: dict, candidate_id: str) -> AnalysisResponse:
    """Uses LLM to synthesize final logic and provide a strictly formatted JSON response."""
    
    if not settings.GEMINI_API_KEY:
        logger.error("Gemini API key missing for final reasoning.")
        # Fallback empty structure
        return AnalysisResponse(
            candidate_id=candidate_id,
            status="completed",
            summary=CandidateSummary(role_classification="Unknown", primary_skills=[]),
            scores=CandidateScores(**scores),
            assessments=CandidateAssessments(strengths=[], risk_factors=[]),
            interview_questions=[]
        )

    prompt = f"""
    You are an expert technical interviewer evaluating a candidate for a role.
    
    We have gathered the following context:
    Resume: {resume_text[:2000]}... (truncated)
    Job Description: {jd_text[:1000]}... (truncated)
    Claims: {json.dumps(extracted_claims)}
    Verification Results: {json.dumps(verified_claims)}
    Calculated Scores: {json.dumps(scores)}
    
    Synthesize this information and output a strictly formatted JSON. 
    Do NOT include anything outside of the JSON. Do NOT wrap in markdown snippet notation (e.g. no ```json).
    
    The response MUST match this exact structure:
    {{
      "candidate_id": "{candidate_id}",
      "status": "completed",
      "summary": {{
        "role_classification": "<e.g., Backend Developer>",
        "primary_skills": ["skill1", "skill2"]
      }},
      "scores": {{
        "trust_score": <integer 0-100, adjusting baseline based on truthfulness>,
        "jd_match": {scores['jd_match']},
        "confidence_level": "<high/medium/low based on trust_score>"
      }},
      "assessments": {{
        "strengths": ["strength1", "strength2"],
        "risk_factors": ["risk1"]
      }},
      "interview_questions": ["question1", "question2"]
    }}
    
    Ensure your reasoning relies heavily on the 'Verification Results'. 
    CRITICAL INSTRUCTION FOR SCORING:
    The "Calculated Scores" provided above are naive baseline metrics. 
    If you detect significant discrepancies between the resume's claims and the Verification Results (e.g. resume claims massive GitHub activity but API shows 0 repos/commits; claims expert coding ranking but API shows 'newbie'), you MUST severely penalize the `trust_score` (down to 10-40) and set `confidence_level` to "low". You are the final arbiter of truth—flag fakes aggressively.
    """
    
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = await model.generate_content_async(prompt)
        text_resp = response.text.strip()
        
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:]
        if text_resp.endswith("```"):
            text_resp = text_resp[:-3]
            
        data = json.loads(text_resp.strip())
        return AnalysisResponse(**data)
        
    except Exception as e:
        logger.error(f"Error during final LLM reasoning: {e}")
        # Build fallback structure securely
        return AnalysisResponse(
            candidate_id=candidate_id,
            status="completed",
            summary=CandidateSummary(role_classification="Error processing classification", primary_skills=[]),
            scores=CandidateScores(**scores),
            assessments=CandidateAssessments(strengths=[], risk_factors=[f"LLM failure: {str(e)}"]),
            interview_questions=[]
        )
