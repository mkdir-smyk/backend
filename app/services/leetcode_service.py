import httpx
from app.core.logger import get_logger

logger = get_logger(__name__)

async def verify_leetcode_user(username: str) -> dict:
    if not username:
        return {}
        
    # We use LeetCode GraphQL API
    query = """
    query getUserProfile($username: String!) {
        matchedUser(username: $username) {
            submitStats: submitStatsGlobal {
                acSubmissionNum {
                    difficulty
                    count
                }
            }
        }
    }
    """
    
    url = "https://leetcode.com/graphql"
    
    result = {
        "verified": False,
        "total_solved": 0,
        "difficulty_distribution": {}
    }
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying LeetCode GraphQL API for {username}...")
            resp = await client.post(
                url, 
                json={"query": query, "variables": {"username": username}},
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and data["data"]["matchedUser"]:
                    stats = data["data"]["matchedUser"]["submitStats"]["acSubmissionNum"]
                    result["verified"] = True
                    for item in stats:
                        difficulty = item["difficulty"]
                        count = item["count"]
                        if difficulty == "All":
                            result["total_solved"] = count
                        else:
                            result["difficulty_distribution"][difficulty] = count
        except Exception as e:
            logger.error(f"LeetCode verification failed for {username}: {e}")
            
    return result
