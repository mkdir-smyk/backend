from pydantic import BaseModel
from typing import List, Optional

# Final Response Format (Strict)
class CandidateSummary(BaseModel):
    role_classification: str
    primary_skills: List[str]

class CandidateScores(BaseModel):
    trust_score: int
    jd_match: int
    confidence_level: str

class CandidateAssessments(BaseModel):
    strengths: List[str]
    risk_factors: List[str]

class AnalysisResponse(BaseModel):
    candidate_id: str
    status: str
    summary: CandidateSummary
    scores: CandidateScores
    assessments: CandidateAssessments
    interview_questions: List[str]

# Intermediate Models
class ExtractedClaims(BaseModel):
    skills: List[str] = []
    projects: List[str] = []
    github_links: List[str] = []
    platforms: List[str] = []
    experience_dates: List[str] = []
    github_username: Optional[str] = None
    leetcode_username: Optional[str] = None
    codeforces_username: Optional[str] = None

class VerifiedClaims(BaseModel):
    github_verified: dict = {}
    leetcode_verified: dict = {}
    codeforces_verified: dict = {}
    web_verified: List[dict] = []
    inconsistencies: List[str] = []
