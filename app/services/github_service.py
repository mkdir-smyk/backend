import httpx
import asyncio
from app.core.logger import get_logger
from app.core.config import settings

logger = get_logger(__name__)

# GitHub requires a User-Agent header — requests without it get a 403
_USER_AGENT = "ResumeAnalyzer/1.0 (resume-analysis-bot)"

# How many times to retry on transient errors (429, 5xx, network timeout)
_MAX_RETRIES = 3
_RETRY_DELAY = 1.5  # seconds between retries


def _build_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.GITHUB_TOKEN:
        # GitHub now prefers "Bearer" over the old "token" prefix
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
        logger.info("[GitHub] Using authenticated requests with token")
    else:
        logger.warning("[GitHub] No GITHUB_TOKEN set — unauthenticated (60 req/hr limit)")
    return headers


async def _get_with_retry(client: httpx.AsyncClient, url: str, headers: dict) -> httpx.Response | None:
    """GET with exponential-backoff retry on rate-limit or transient errors."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = await client.get(url, headers=headers)

            if resp.status_code == 200:
                return resp

            if resp.status_code == 401:
                logger.error(
                    f"[GitHub] 401 Unauthorized for {url}. "
                    "Check that GITHUB_TOKEN is set correctly and has not expired."
                )
                return resp

            if resp.status_code == 403:
                rate_remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                rate_reset = resp.headers.get("X-RateLimit-Reset", "?")
                logger.error(
                    f"[GitHub] 403 Forbidden for {url}. "
                    f"Rate limit remaining: {rate_remaining}, resets at: {rate_reset}. "
                    "Body: " + resp.text[:300]
                )
                # If rate-limited wait and retry; otherwise give up
                if rate_remaining == "0" and attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY * attempt)
                    continue
                return resp

            if resp.status_code == 404:
                logger.warning(f"[GitHub] 404 Not Found: {url}")
                return resp

            if resp.status_code == 422:
                logger.error(f"[GitHub] 422 Unprocessable: {url} — {resp.text[:300]}")
                return resp

            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(
                    f"[GitHub] {resp.status_code} on attempt {attempt}/{_MAX_RETRIES} for {url}"
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY * attempt)
                    continue
                return resp

            logger.error(f"[GitHub] Unexpected {resp.status_code} for {url}: {resp.text[:300]}")
            return resp

        except httpx.TimeoutException:
            logger.warning(f"[GitHub] Timeout on attempt {attempt}/{_MAX_RETRIES} for {url}")
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_DELAY * attempt)
        except httpx.ConnectError as e:
            logger.error(
                f"[GitHub] Connection error for {url}: {e}. "
                "Check network connectivity or firewall rules."
            )
            return None
        except Exception as e:
            logger.error(f"[GitHub] Unexpected exception for {url}: {e}")
            return None

    logger.error(f"[GitHub] All {_MAX_RETRIES} attempts failed for {url}")
    return None


async def verify_github_user(username: str) -> dict:
    if not username:
        logger.warning("[GitHub] No username provided.")
        return {}

    username = username.strip().lstrip("@")

    result = {
        "verified": False,
        "profile_stats": {},
        "repo_count": 0,
        "top_languages": [],
        "projects_list": [],
        "total_stars": 0,
        "recent_activity": False,
    }

    headers = _build_headers()

    # Use a generous timeout — GitHub can be slow under load
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=True) as client:

        # ── 1. User profile ──────────────────────────────────────
        url = f"https://api.github.com/users/{username}"
        logger.info(f"[GitHub] Fetching profile: {url}")
        user_resp = await _get_with_retry(client, url, headers)

        if not user_resp or user_resp.status_code != 200:
            logger.error(f"[GitHub] Could not fetch profile for '{username}'")
            return result

        result["verified"] = True
        user_data = user_resp.json()

        result["profile_stats"] = {
            "followers": user_data.get("followers", 0),
            "following": user_data.get("following", 0),
            "public_repos": user_data.get("public_repos", 0),
            "public_gists": user_data.get("public_gists", 0),
            "bio": user_data.get("bio") or "",
            "company": user_data.get("company") or "",
            "blog": user_data.get("blog") or "",
            "location": user_data.get("location") or "",
            "created_at": user_data.get("created_at") or "",
        }
        result["repo_count"] = user_data.get("public_repos", 0)

        # ── 2. Repositories ──────────────────────────────────────
        repos_url = (
            f"https://api.github.com/users/{username}/repos"
            "?per_page=100&sort=updated&type=owner"
        )
        logger.info(f"[GitHub] Fetching repos: {repos_url}")
        repos_resp = await _get_with_retry(client, repos_url, headers)

        if repos_resp and repos_resp.status_code == 200:
            repos = repos_resp.json()
            lang_count: dict[str, int] = {}
            total_stars = 0
            projects = []

            for r in repos:
                if r.get("fork"):
                    continue  # Skip forks — only count original work
                lang = r.get("language")
                if lang:
                    lang_count[lang] = lang_count.get(lang, 0) + 1
                total_stars += r.get("stargazers_count", 0)
                projects.append({
                    "name": r.get("name", ""),
                    "description": r.get("description") or "",
                    "stars": r.get("stargazers_count", 0),
                    "language": lang or "",
                    "url": r.get("html_url", ""),
                    "updated_at": r.get("updated_at", ""),
                })

            # Sort languages by frequency
            sorted_langs = sorted(lang_count.items(), key=lambda x: x[1], reverse=True)
            result["top_languages"] = [lang for lang, _ in sorted_langs[:8]]
            result["total_stars"] = total_stars
            projects.sort(key=lambda x: x["stars"], reverse=True)
            result["projects_list"] = projects[:10]
            logger.info(
                f"[GitHub] Found {len(projects)} original repos, "
                f"top langs: {result['top_languages'][:3]}, "
                f"total stars: {total_stars}"
            )
        else:
            logger.warning(f"[GitHub] Could not fetch repos for '{username}'")

        # ── 3. Recent activity ───────────────────────────────────
        events_url = (
            f"https://api.github.com/users/{username}/events/public?per_page=30"
        )
        logger.info(f"[GitHub] Fetching events: {events_url}")
        events_resp = await _get_with_retry(client, events_url, headers)

        if events_resp and events_resp.status_code == 200:
            events = events_resp.json()
            result["recent_activity"] = len(events) > 0
            result["recent_event_count"] = len(events)
            logger.info(f"[GitHub] {len(events)} recent public events found")
        else:
            logger.warning(f"[GitHub] Could not fetch events for '{username}'")

    logger.info(
        f"[GitHub] Verification complete for '{username}': "
        f"verified={result['verified']}, repos={result['repo_count']}, "
        f"stars={result['total_stars']}"
    )
    return result