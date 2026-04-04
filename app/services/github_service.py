import httpx
from app.core.logger import get_logger
from app.core.config import settings

logger = get_logger(__name__)

async def verify_github_user(username: str) -> dict:
    if not username:
        return {}
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"

    url = f"https://api.github.com/users/{username}"
    repos_url = f"https://api.github.com/users/{username}/repos?per_page=100"
    
    result = {
        "verified": False,
        "repo_count": 0,
        "top_languages": []
    }
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying GitHub API for {username}...")
            user_resp = await client.get(url, headers=headers)
            if user_resp.status_code == 200:
                result["verified"] = True
                
                repos_resp = await client.get(repos_url, headers=headers)
                if repos_resp.status_code == 200:
                    repos = repos_resp.json()
                    result["repo_count"] = len(repos)
                    langs = set()
                    for r in repos:
                        if r.get("language"):
                            langs.add(r["language"])
                    result["top_languages"] = list(langs)
        except Exception as e:
            logger.error(f"GitHub verification failed for {username}: {e}")
            
    return result
