import httpx
from app.core.logger import get_logger

logger = get_logger(__name__)

async def verify_codeforces_user(username: str) -> dict:
    if not username:
        return {}
        
    url = f"https://codeforces.com/api/user.info?handles={username}"
    
    result = {
        "verified": False,
        "rating": 0,
        "rank": ""
    }
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying Codeforces API for {username}...")
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "OK" and data.get("result"):
                    user = data["result"][0]
                    result["verified"] = True
                    result["rating"] = user.get("rating", 0)
                    result["rank"] = user.get("rank", "unrated")
        except Exception as e:
            logger.error(f"Codeforces verification failed for {username}: {e}")
            
    return result
