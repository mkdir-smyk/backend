"""
scoring_engine.py
-----------------
Computes deterministic baseline scores that the LLM reasoner then refines.

JD Match  — skill-focused TF-IDF-style overlap, NOT raw word overlap
Trust Score — evidence-based, distinguishes "claim contradicted" vs "profile absent"
"""

from app.models.schemas import CandidateScores, ExtractedClaims, VerifiedClaims
from app.utils.helpers import clean_text
import re

# ---------------------------------------------------------------------------
# Stop-word list (extended) — stripped before JD keyword extraction
# ---------------------------------------------------------------------------
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall", "can",
    "this", "that", "these", "those", "it", "its", "we", "you", "they",
    "our", "your", "their", "us", "he", "she", "his", "her", "him",
    # Generic JD filler words that inflate denominator
    "experience", "work", "working", "team", "ability", "strong", "good",
    "excellent", "knowledge", "understanding", "preferred", "required",
    "responsibilities", "requirements", "qualifications", "opportunity",
    "position", "role", "candidate", "applicant", "job", "company",
    "please", "apply", "including", "such", "well", "also", "any",
    "all", "not", "more", "than", "one", "two", "years", "year",
    "new", "use", "using", "used", "like", "other", "within", "across",
    "help", "make", "build", "develop", "support", "ensure", "provide",
    "manage", "create", "design", "implement", "maintain", "improve",
}

# Technical skill tokens — these carry 3x weight in JD match
_TECH_BOOST_PATTERNS = re.compile(
    r'\b('
    r'python|java(?:script)?|typescript|c\+\+|c#|golang|go|rust|ruby|php|swift|kotlin|scala|r\b|'
    r'react|angular|vue|svelte|nextjs|nuxt|'
    r'node(?:js)?|express|fastapi|django|flask|spring|laravel|rails|'
    r'sql|mysql|postgres(?:ql)?|mongodb|redis|elasticsearch|dynamodb|'
    r'aws|gcp|azure|docker|kubernetes|k8s|terraform|ansible|'
    r'git|linux|bash|graphql|rest|grpc|kafka|rabbitmq|'
    r'pytorch|tensorflow|scikit[\-_]learn|pandas|numpy|spark|hadoop|'
    r'html|css|sass|scss|webpack|vite|'
    r'ml|ai|llm|nlp|cv|deep.?learning|machine.?learning|'
    r'ci[/\-]cd|devops|agile|scrum'
    r')\b',
    re.IGNORECASE,
)


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    cleaned = clean_text(text)
    if not cleaned:
        return set()
    return set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9\+\#\.]*\b', cleaned.lower()))


def _extract_skill_ngrams(text: str) -> set[str]:
    """Extract both unigrams and bigrams for multi-word skills (e.g. 'machine learning')."""
    if not text:
        return set()
    cleaned = clean_text(text)
    if not cleaned:
        return set()
    tokens = re.findall(r'\b[a-zA-Z][a-zA-Z0-9\+\#\.]*\b', cleaned.lower())
    unigrams = set(tokens)
    bigrams = {f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)}
    return unigrams | bigrams


def _compute_jd_match(resume_text: str, jd_text: str) -> int:
    """
    Skill-focused JD match score (0–100).

    Algorithm:
    1. Extract skill keywords from JD (remove stop words + generic filler).
    2. Give tech tokens 3x weight — they matter far more than generic words.
    3. Score = weighted_overlap / weighted_jd_total * 100
    4. Cap at 100. Never divide by the full JD vocab.
    """
    if not resume_text or not jd_text:
        return 0

    resume_tokens = _extract_skill_ngrams(resume_text)
    jd_tokens = _extract_skill_ngrams(jd_text)

    # Remove stop words
    jd_keywords = {t for t in jd_tokens if t not in _STOP_WORDS and len(t) > 2}

    if not jd_keywords:
        return 0

    weighted_total = 0.0
    weighted_overlap = 0.0

    for kw in jd_keywords:
        # Boost weight for technical tokens
        weight = 3.0 if _TECH_BOOST_PATTERNS.search(kw) else 1.0
        weighted_total += weight
        if kw in resume_tokens:
            weighted_overlap += weight

    if weighted_total == 0:
        return 0

    raw = (weighted_overlap / weighted_total) * 100

    # Apply a mild curve: scores < 30 are stretched upward slightly,
    # because even a 30% weighted skill overlap is meaningful.
    if raw < 30:
        curved = raw * 1.4
    elif raw < 60:
        curved = 30 + (raw - 30) * 1.1
    else:
        curved = raw

    return min(100, int(curved))


def _compute_trust_score(verified_claims: VerifiedClaims) -> tuple[int, str]:
    """
    Evidence-based trust score (0–100).

    Key design decisions:
    - Base = 60 (innocent until proven guilty)
    - Verified profiles ADD points
    - ONLY deduct for explicit contradictions, NOT for absent profiles
    - Empty GitHub ≠ lie; empty GitHub + claimed "100 open source repos" = lie
    - Inconsistencies from verification_agent already filter this correctly
    """
    score = 60  # Neutral baseline — we assume good faith

    gh = verified_claims.github_verified or {}
    lc = verified_claims.leetcode_verified or {}
    cf = verified_claims.codeforces_verified or {}

    # ── GitHub ───────────────────────────────────────────────────
    if gh.get("verified"):
        score += 10  # Profile exists = a real person with a GitHub account
        repo_count = gh.get("repo_count", 0)
        stars = gh.get("total_stars", 0)
        recent = gh.get("recent_activity", False)

        if repo_count >= 5:
            score += 5
        if repo_count >= 15:
            score += 5
        if stars >= 10:
            score += 3
        if stars >= 50:
            score += 3
        if recent:
            score += 4

        # Empty profile is NOT penalized — students often have private repos
        # Only penalize if the candidate made explicit open-source claims
        # (that logic lives in the LLM reasoner which has the resume text)

    # ── LeetCode ─────────────────────────────────────────────────
    if lc.get("verified"):
        score += 8
        solved = lc.get("total_solved", 0)
        contest_rating = lc.get("contest_rating") or 0
        if solved >= 50:
            score += 4
        if solved >= 200:
            score += 4
        if contest_rating >= 1500:
            score += 5

    # ── Codeforces ───────────────────────────────────────────────
    if cf.get("verified"):
        score += 7
        rating = cf.get("rating", 0)
        contests = cf.get("contests_participated", 0)
        if rating >= 1200:
            score += 4
        if rating >= 1600:
            score += 4
        if contests >= 5:
            score += 3

    # ── Deductions — ONLY for explicit contradictions ────────────
    # Filter: only count inconsistencies that are genuine contradictions,
    # not just "profile not found" for profiles the candidate never claimed.
    genuine_contradictions = [
        i for i in (verified_claims.inconsistencies or [])
        if "not found" not in i.lower()           # absent ≠ contradiction
        and "inaccessible" not in i.lower()
        and "unreachable" not in i.lower()
    ]
    score -= min(20, 7 * len(genuine_contradictions))

    # ── Normalize ────────────────────────────────────────────────
    score = min(100, max(0, score))

    if score >= 75:
        confidence = "high"
    elif score >= 50:
        confidence = "medium"
    else:
        confidence = "low"

    return score, confidence


def compute_scores(resume_text: str, jd_text: str, verified_claims: VerifiedClaims) -> CandidateScores:
    jd_match = _compute_jd_match(resume_text, jd_text)
    trust_score, confidence = _compute_trust_score(verified_claims)

    return CandidateScores(
        trust_score=trust_score,
        jd_match=jd_match,
        confidence_level=confidence,
    )