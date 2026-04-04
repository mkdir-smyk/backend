from app.models.schemas import CandidateScores, ExtractedClaims, VerifiedClaims
from app.utils.helpers import clean_text
import re

def compute_scores(resume_text: str, jd_text: str, verified_claims: VerifiedClaims) -> CandidateScores:
    """Computes a deterministic trust score and a JD match score."""
    
    # JD Match logic: simple keyword overlap based on words in JD
    resume_words = set(re.findall(r'\b\w+\b', clean_text(resume_text).lower()))
    jd_words = set(re.findall(r'\b\w+\b', clean_text(jd_text).lower()))
    
    # Filter out common stop words to get a raw but effective match score
    stop_words = {"and", "the", "to", "of", "in", "for", "with", "on", "a", "an", "is", "as", "be", "this", "that", "it"}
    jd_keywords = jd_words - stop_words
    
    if jd_keywords:
        overlap = len(resume_words.intersection(jd_keywords))
        jd_match = min(100, int((overlap / len(jd_keywords)) * 100))
    else:
        jd_match = 0
        
    # Trust Score Logic
    trust_score = 50 # Base trust
    
    if verified_claims.github_verified.get("verified"):
        trust_score += 20
        # Add a bit more if they have repos
        trust_score += min(15, verified_claims.github_verified.get("repo_count", 0))
    
    if verified_claims.leetcode_verified.get("verified"):
        trust_score += 15
        if verified_claims.leetcode_verified.get("total_solved", 0) > 100:
            trust_score += 10
            
    if verified_claims.codeforces_verified.get("verified"):
        trust_score += 10
        if verified_claims.codeforces_verified.get("rating", 0) > 1400:
            trust_score += 10
            
    if verified_claims.inconsistencies:
        trust_score -= min(30, 10 * len(verified_claims.inconsistencies))
        
    trust_score = min(100, max(0, trust_score))
    
    # Confidence Level
    if trust_score > 80:
        confidence = "high"
    elif trust_score > 50:
        confidence = "medium"
    else:
        confidence = "low"
        
    return CandidateScores(
        trust_score=trust_score,
        jd_match=jd_match,
        confidence_level=confidence
    )
