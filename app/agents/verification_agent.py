from app.models.schemas import ExtractedClaims, VerifiedClaims
from app.services.github_service import verify_github_user
from app.services.leetcode_service import verify_leetcode_user
from app.services.codeforces_service import verify_codeforces_user
from app.services.web_search_service import search_web
from app.core.logger import get_logger

import asyncio

logger = get_logger(__name__)

async def verify_claims(claims: ExtractedClaims, 
                       github_username: str = None, 
                       leetcode_username: str = None, 
                       codeforces_username: str = None) -> VerifiedClaims:
    """Verifies claims using external services."""
    
    verified_claims = VerifiedClaims()
    
    # Try to extract github username from links if not provided
    if not github_username and claims.github_links:
        for link in claims.github_links:
            if "github.com/" in link:
                parts = link.split("github.com/")
                if len(parts) > 1:
                    github_username = parts[1].split("/")[0]
                    break

    tasks = {
        "github": verify_github_user(github_username) if github_username else asyncio.sleep(0),
        "leetcode": verify_leetcode_user(leetcode_username) if leetcode_username else asyncio.sleep(0),
        "codeforces": verify_codeforces_user(codeforces_username) if codeforces_username else asyncio.sleep(0),
    }

    results = await asyncio.gather(*tasks.values())
    
    if github_username:
        verified_claims.github_verified = results[0]
        if not verified_claims.github_verified.get("verified"):
            verified_claims.inconsistencies.append("GitHub profile not found or unreachable.")
            
    if leetcode_username:
        verified_claims.leetcode_verified = results[1]
        if not verified_claims.leetcode_verified.get("verified"):
            verified_claims.inconsistencies.append("LeetCode profile not found or unreachable.")
            
    if codeforces_username:
        verified_claims.codeforces_verified = results[2]
        if not verified_claims.codeforces_verified.get("verified"):
            verified_claims.inconsistencies.append("Codeforces profile not found or unreachable.")
            
    # Fallback to web search for specific projects if they sound significant
    if claims.projects:
        # Example: Just search the first notable project for proof
        first_project = claims.projects[0]
        search_results = await search_web(first_project, limit=2)
        verified_claims.web_verified = search_results

    return verified_claims
