import httpx
from app.core.logger import get_logger
from app.core.config import settings

logger = get_logger(__name__)

async def search_web(query: str, limit: int = 3) -> list:
    """Uses Google Custom Search API to perform a web search fallback."""
    if not settings.GOOGLE_SEARCH_API_KEY:
        logger.warning("Google Search API key not configured, skipping web search.")
        return []
        
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.GOOGLE_SEARCH_API_KEY,
        "cx": settings.GOOGLE_SEARCH_CX,
        "q": query,
        "num": limit
    }
    
    results = []
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying Google Search API for: '{query}'...")
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    results.append({
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "snippet": item.get("snippet")
                    })
        except Exception as e:
            logger.error(f"Web search failed for '{query}': {e}")
            
    return results
