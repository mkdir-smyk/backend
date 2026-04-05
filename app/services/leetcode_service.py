import httpx
import asyncio
from app.core.logger import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 1.5

# LeetCode's GraphQL endpoint blocks requests without a proper browser-like header set
_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://leetcode.com",
    "Origin": "https://leetcode.com",
}

# Full profile query — gets solved counts, ranking, badges, and recent submissions
_PROFILE_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile {
      ranking
      reputation
      starRating
    }
    submitStats: submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
        submissions
      }
    }
    badges {
      name
      displayName
    }
    activeBadge {
      displayName
    }
  }
  userContestRanking(username: $username) {
    attendedContestsCount
    rating
    globalRanking
    topPercentage
  }
}
"""


async def verify_leetcode_user(username: str) -> dict:
    if not username:
        return {}

    username = username.strip().lstrip("@")

    result = {
        "verified": False,
        "total_solved": 0,
        "difficulty_distribution": {},
        "ranking": None,
        "contest_rating": None,
        "contests_attended": 0,
        "top_percentage": None,
        "badges": [],
    }

    payload = {"query": _PROFILE_QUERY, "variables": {"username": username}}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        follow_redirects=True,
    ) as client:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                logger.info(
                    f"[LeetCode] Querying GraphQL for '{username}' "
                    f"(attempt {attempt}/{_MAX_RETRIES})"
                )
                resp = await client.post(
                    "https://leetcode.com/graphql",
                    json=payload,
                    headers=_HEADERS,
                )

                if resp.status_code == 200:
                    data = resp.json()

                    # GraphQL errors come back as 200 with an "errors" key
                    if "errors" in data:
                        logger.error(
                            f"[LeetCode] GraphQL errors for '{username}': {data['errors']}"
                        )
                        return result

                    matched = data.get("data", {}).get("matchedUser")
                    if not matched:
                        logger.warning(
                            f"[LeetCode] User '{username}' not found "
                            "(matchedUser is null)"
                        )
                        return result

                    result["verified"] = True

                    # Solved counts
                    ac_nums = (
                        matched.get("submitStats", {})
                        .get("acSubmissionNum", [])
                    )
                    for item in ac_nums:
                        difficulty = item.get("difficulty", "")
                        count = item.get("count", 0)
                        if difficulty == "All":
                            result["total_solved"] = count
                        else:
                            result["difficulty_distribution"][difficulty] = count

                    # Profile
                    profile = matched.get("profile", {})
                    result["ranking"] = profile.get("ranking")

                    # Badges
                    result["badges"] = [
                        b.get("displayName", b.get("name", ""))
                        for b in (matched.get("badges") or [])
                    ]

                    # Contest stats
                    contest = data.get("data", {}).get("userContestRanking")
                    if contest:
                        result["contest_rating"] = contest.get("rating")
                        result["contests_attended"] = contest.get("attendedContestsCount", 0)
                        result["top_percentage"] = contest.get("topPercentage")

                    logger.info(
                        f"[LeetCode] '{username}': "
                        f"solved={result['total_solved']}, "
                        f"ranking={result['ranking']}, "
                        f"contest_rating={result['contest_rating']}"
                    )
                    return result

                elif resp.status_code == 403:
                    logger.error(
                        f"[LeetCode] 403 Forbidden. LeetCode may be blocking the "
                        f"request. Response: {resp.text[:300]}"
                    )
                    # Don't retry on 403 — it won't help
                    return result

                elif resp.status_code == 429:
                    logger.warning(
                        f"[LeetCode] 429 Rate limited on attempt {attempt}. "
                        f"Waiting {_RETRY_DELAY * attempt}s..."
                    )
                    if attempt < _MAX_RETRIES:
                        await asyncio.sleep(_RETRY_DELAY * attempt)
                    continue

                else:
                    logger.error(
                        f"[LeetCode] Unexpected {resp.status_code} for '{username}': "
                        f"{resp.text[:300]}"
                    )
                    if attempt < _MAX_RETRIES:
                        await asyncio.sleep(_RETRY_DELAY * attempt)
                    continue

            except httpx.TimeoutException:
                logger.warning(
                    f"[LeetCode] Timeout on attempt {attempt}/{_MAX_RETRIES} for '{username}'"
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY * attempt)

            except httpx.ConnectError as e:
                logger.error(
                    f"[LeetCode] Connection error for '{username}': {e}. "
                    "Check network connectivity."
                )
                return result

            except Exception as e:
                logger.error(f"[LeetCode] Unexpected error for '{username}': {e}")
                return result

    logger.error(f"[LeetCode] All retries exhausted for '{username}'")
    return result