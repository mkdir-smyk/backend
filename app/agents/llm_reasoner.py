"""
llm_reasoner.py
---------------
Final LLM synthesis step. Takes all upstream signals and produces the
structured AnalysisResponse.

Key fixes vs original:
- Does NOT hardcode jd_match from the baseline scorer in the prompt template
  (the LLM was locked into a broken number)
- Passes the baseline scores as CONTEXT only — the LLM can adjust all of them
- Caps primary_skills at 5 so the summary stays clean
- Strips ```json fences more robustly (Gemini sometimes wraps in ``` without "json")
- Full resume + JD text passed (not truncated to 2000/1000 chars which lost key info)
"""

import re
import google.generativeai as genai
import json
from app.core.config import settings
from app.core.logger import get_logger
from app.models.schemas import (
    AnalysisResponse,
    CandidateSummary,
    CandidateScores,
    CandidateAssessments,
)

logger = get_logger(__name__)

_MAX_RESUME_CHARS = 6000   # ~1500 tokens — enough for a full resume
_MAX_JD_CHARS = 3000       # ~750 tokens — enough for most JDs
_MAX_PRIMARY_SKILLS = 5    # Keep the summary tight


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that Gemini sometimes adds."""
    text = text.strip()
    # Handle ```json, ```JSON, ``` with or without newline
    text = re.sub(r'^```[a-zA-Z]*\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


async def reason_candidate(
    resume_text: str,
    jd_text: str,
    extracted_claims: dict,
    verified_claims: dict,
    scores: dict,
    candidate_id: str,
) -> AnalysisResponse:
    """
    Uses Gemini to synthesize all signals into a final structured response.
    The baseline `scores` dict is provided as context — the LLM may adjust
    trust_score and confidence_level based on qualitative reasoning,
    but jd_match should stay close to the calculated value unless there is
    a clear reason to adjust.
    """

    def _fallback(error_msg: str = "") -> AnalysisResponse:
        return AnalysisResponse(
            candidate_id=candidate_id,
            status="completed",
            summary=CandidateSummary(
                role_classification="Unknown",
                primary_skills=[],
            ),
            scores=CandidateScores(**scores),
            assessments=CandidateAssessments(
                strengths=[],
                risk_factors=[error_msg] if error_msg else [],
            ),
            interview_questions=[],
        )

    if not settings.GEMINI_API_KEY:
        logger.error("[Reasoner] Gemini API key missing.")
        return _fallback("Gemini API key not configured.")

    # Summarise verification results concisely for the prompt
    gh = verified_claims.get("github_verified", {}) or {}
    lc = verified_claims.get("leetcode_verified", {}) or {}
    cf = verified_claims.get("codeforces_verified", {}) or {}
    inconsistencies = verified_claims.get("inconsistencies", []) or []

    verification_summary = {
        "github": {
            "verified": gh.get("verified", False),
            "repo_count": gh.get("repo_count", 0),
            "total_stars": gh.get("total_stars", 0),
            "top_languages": gh.get("top_languages", [])[:6],
            "recent_activity": gh.get("recent_activity", False),
            "top_projects": [
                {"name": p["name"], "stars": p["stars"], "language": p.get("language", "")}
                for p in (gh.get("projects_list") or [])[:5]
            ],
        } if gh.get("verified") else {"verified": False},
        "leetcode": {
            "verified": lc.get("verified", False),
            "total_solved": lc.get("total_solved", 0),
            "contest_rating": lc.get("contest_rating"),
            "difficulty": lc.get("difficulty_distribution", {}),
        } if lc.get("verified") else {"verified": False},
        "codeforces": {
            "verified": cf.get("verified", False),
            "rating": cf.get("rating", 0),
            "rank": cf.get("rank", ""),
            "max_rating": cf.get("max_rating", 0),
            "contests_participated": cf.get("contests_participated", 0),
        } if cf.get("verified") else {"verified": False},
        "inconsistencies": inconsistencies,
    }

    prompt = f"""You are an expert technical recruiter performing a final candidate evaluation.

=== RESUME (full text) ===
{resume_text[:_MAX_RESUME_CHARS]}

=== JOB DESCRIPTION (full text) ===
{jd_text[:_MAX_JD_CHARS]}

=== EXTRACTED CLAIMS ===
{json.dumps(extracted_claims, indent=2)}

=== VERIFICATION RESULTS ===
{json.dumps(verification_summary, indent=2)}

=== BASELINE SCORES (calculated algorithmically) ===
- jd_match: {scores['jd_match']} / 100  (skill-weighted keyword overlap — use this as a strong anchor)
- trust_score: {scores['trust_score']} / 100  (evidence-based — you may adjust ±15 based on qualitative reasoning)
- confidence_level: {scores['confidence_level']}

=== YOUR TASK ===
Synthesize the above and produce a strictly valid JSON object. No markdown fences. No text outside the JSON.

RULES:
1. primary_skills: list EXACTLY the top {_MAX_PRIMARY_SKILLS} skills most relevant to the JD. No more.
2. role_classification: classify the candidate by what they ARE, not what the JD asks for. Be honest.
3. trust_score: stay within ±15 of the baseline UNLESS there is a stark, explicit contradiction in the verification results (e.g., candidate claims "100+ stars on GitHub" but verified star count is 0). An empty GitHub for a student who did NOT claim major open-source contributions is NOT a contradiction — do not penalise it.
4. jd_match: keep close to the baseline {scores['jd_match']}. Only adjust if you find skills in the resume that the keyword scorer clearly missed (e.g. a skill spelled differently).
5. strengths: list only genuine, evidence-backed strengths. Empty array [] is valid.
6. risk_factors: list only real contradictions or misalignments. Do NOT add risk factors for profiles the candidate never claimed to have. Empty array [] is valid.
7. interview_questions: generate 3–5 sharp, specific questions that probe the actual gaps and claims. Reference real project names and technologies from the resume.

OUTPUT FORMAT (return this exact structure, filled in):
{{
  "candidate_id": "{candidate_id}",
  "status": "completed",
  "summary": {{
    "role_classification": "<honest classification of the candidate>",
    "primary_skills": ["skill1", "skill2", "skill3", "skill4", "skill5"]
  }},
  "scores": {{
    "trust_score": <integer 0-100>,
    "jd_match": <integer 0-100>,
    "confidence_level": "<high|medium|low>"
  }},
  "assessments": {{
    "strengths": ["<specific evidence-backed strength>"],
    "risk_factors": ["<specific contradiction or gap>"]
  }},
  "interview_questions": [
    "<specific question 1>",
    "<specific question 2>",
    "<specific question 3>"
  ]
}}"""

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        logger.info("[Reasoner] Sending request to Gemini...")
        response = await model.generate_content_async(prompt)
        text_resp = _strip_fences(response.text)

        logger.debug(f"[Reasoner] Raw Gemini response (first 500 chars): {text_resp[:500]}")

        data = json.loads(text_resp)

        # Enforce primary_skills cap even if Gemini ignores the instruction
        if "summary" in data and "primary_skills" in data["summary"]:
            data["summary"]["primary_skills"] = data["summary"]["primary_skills"][:_MAX_PRIMARY_SKILLS]

        # Enforce score bounds
        if "scores" in data:
            data["scores"]["trust_score"] = max(0, min(100, int(data["scores"].get("trust_score", scores["trust_score"]))))
            data["scores"]["jd_match"] = max(0, min(100, int(data["scores"].get("jd_match", scores["jd_match"]))))
            if data["scores"].get("confidence_level") not in ("high", "medium", "low"):
                data["scores"]["confidence_level"] = scores["confidence_level"]

        logger.info(
            f"[Reasoner] Final scores — "
            f"trust={data['scores']['trust_score']}, "
            f"jd_match={data['scores']['jd_match']}, "
            f"confidence={data['scores']['confidence_level']}"
        )

        return AnalysisResponse(**data)

    except json.JSONDecodeError as e:
        logger.error(f"[Reasoner] JSON parse error: {e}. Response was: {text_resp[:500]}")
        return _fallback(f"LLM returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"[Reasoner] Unexpected error: {e}")
        return _fallback(f"LLM error: {e}")