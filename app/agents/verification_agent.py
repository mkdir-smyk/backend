import asyncio
import re

from app.models.schemas import ExtractedClaims, VerifiedClaims
from app.services.github_service import verify_github_user
from app.services.leetcode_service import verify_leetcode_user
from app.services.codeforces_service import verify_codeforces_user
from app.services.web_search_service import search_web
from app.core.logger import get_logger

logger = get_logger(__name__)


def _extract_github_username_from_text(text: str) -> str | None:
    """
    Multi-pattern GitHub username extraction from raw resume text.
    Tries URL patterns first, then inline mentions.
    """
    patterns = [
        r"github\.com/([A-Za-z0-9][A-Za-z0-9\-]{0,38})",   # URL form
        r"@([A-Za-z0-9][A-Za-z0-9\-]{0,38})\s+github",      # @handle + github
        r"github[:\s]+@?([A-Za-z0-9][A-Za-z0-9\-]{0,38})",  # "GitHub: handle"
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            username = match.group(1).rstrip("/").strip()
            # Exclude obviously bad matches
            if username.lower() not in ("com", "io", "org", "net"):
                return username
    return None


def _extract_leetcode_username_from_text(text: str) -> str | None:
    patterns = [
        r"leetcode\.com/u/([A-Za-z0-9_\-]{1,40})",
        r"leetcode\.com/([A-Za-z0-9_\-]{1,40})",
        r"leetcode[:\s]+@?([A-Za-z0-9_\-]{1,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).rstrip("/").strip()
    return None


def _extract_codeforces_username_from_text(text: str) -> str | None:
    patterns = [
        r"codeforces\.com/profile/([A-Za-z0-9_\-\.]{1,40})",
        r"codeforces\.com/([A-Za-z0-9_\-\.]{1,40})",
        r"codeforces[:\s]+@?([A-Za-z0-9_\-\.]{1,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).rstrip("/").strip()
    return None


async def verify_claims(
    claims: ExtractedClaims,
    resume_text: str,
    github_username: str | None = None,
    leetcode_username: str | None = None,
    codeforces_username: str | None = None,
) -> VerifiedClaims:
    """
    Verifies extracted claims against external APIs.

    Resolution priority for usernames:
      1. Explicitly passed argument (from frontend / manual override)
      2. LLM-extracted from claims
      3. Regex-extracted from raw resume text (most reliable fallback)
    """
    verified = VerifiedClaims()

    # ── Username resolution ──────────────────────────────────────
    final_github = (
        github_username
        or claims.github_username
        or _extract_github_username_from_text(resume_text)
    )
    final_leetcode = (
        leetcode_username
        or claims.leetcode_username
        or _extract_leetcode_username_from_text(resume_text)
    )
    final_codeforces = (
        codeforces_username
        or claims.codeforces_username
        or _extract_codeforces_username_from_text(resume_text)
    )

    # Strip any trailing slashes / whitespace that sneak in from PDFs
    if final_github:
        final_github = final_github.strip().rstrip("/")
    if final_leetcode:
        final_leetcode = final_leetcode.strip().rstrip("/")
    if final_codeforces:
        final_codeforces = final_codeforces.strip().rstrip("/")

    logger.info(f"[Verification] Resolved GitHub       : {final_github!r}")
    logger.info(f"[Verification] Resolved LeetCode     : {final_leetcode!r}")
    logger.info(f"[Verification] Resolved Codeforces   : {final_codeforces!r}")

    # ── Build async task list ────────────────────────────────────
    # Use sentinel coroutines for missing usernames so gather indices stay stable
    async def _noop():
        return None

    tasks = [
        verify_github_user(final_github) if final_github else _noop(),
        verify_leetcode_user(final_leetcode) if final_leetcode else _noop(),
        verify_codeforces_user(final_codeforces) if final_codeforces else _noop(),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── GitHub result ────────────────────────────────────────────
    github_result = results[0]
    if final_github:
        if isinstance(github_result, Exception):
            logger.error(f"[Verification] GitHub task raised exception: {github_result}")
            verified.inconsistencies.append(
                f"GitHub verification failed with error: {github_result}"
            )
        elif github_result is None or not github_result:
            logger.warning("[Verification] GitHub returned empty result")
        else:
            verified.github_verified = github_result
            if not github_result.get("verified"):
                verified.inconsistencies.append(
                    f"GitHub profile '{final_github}' not found or inaccessible."
                )
            else:
                logger.info(
                    f"[Verification] GitHub OK — "
                    f"repos={github_result.get('repo_count')}, "
                    f"stars={github_result.get('total_stars')}"
                )
    else:
        logger.info("[Verification] No GitHub username — skipping")

    # ── LeetCode result ──────────────────────────────────────────
    leetcode_result = results[1]
    if final_leetcode:
        if isinstance(leetcode_result, Exception):
            logger.error(f"[Verification] LeetCode task raised exception: {leetcode_result}")
            verified.inconsistencies.append(
                f"LeetCode verification failed with error: {leetcode_result}"
            )
        elif leetcode_result is None or not leetcode_result:
            logger.warning("[Verification] LeetCode returned empty result")
        else:
            verified.leetcode_verified = leetcode_result
            if not leetcode_result.get("verified"):
                verified.inconsistencies.append(
                    f"LeetCode profile '{final_leetcode}' not found or inaccessible."
                )
            else:
                logger.info(
                    f"[Verification] LeetCode OK — "
                    f"solved={leetcode_result.get('total_solved')}, "
                    f"contest_rating={leetcode_result.get('contest_rating')}"
                )
    else:
        logger.info("[Verification] No LeetCode username — skipping")

    # ── Codeforces result ────────────────────────────────────────
    codeforces_result = results[2]
    if final_codeforces:
        if isinstance(codeforces_result, Exception):
            logger.error(f"[Verification] Codeforces task raised exception: {codeforces_result}")
            verified.inconsistencies.append(
                f"Codeforces verification failed with error: {codeforces_result}"
            )
        elif codeforces_result is None or not codeforces_result:
            logger.warning("[Verification] Codeforces returned empty result")
        else:
            verified.codeforces_verified = codeforces_result
            if not codeforces_result.get("verified"):
                verified.inconsistencies.append(
                    f"Codeforces handle '{final_codeforces}' not found or inaccessible."
                )
            else:
                logger.info(
                    f"[Verification] Codeforces OK — "
                    f"rating={codeforces_result.get('rating')}, "
                    f"rank={codeforces_result.get('rank')}"
                )
    else:
        logger.info("[Verification] No Codeforces handle — skipping")

    # ── Web search fallback for project verification ─────────────
    if claims.projects:
        first_project = claims.projects[0]
        logger.info(f"[Verification] Web search for project: {first_project!r}")
        try:
            search_results = await search_web(first_project, limit=2)
            verified.web_verified = search_results
            logger.info(f"[Verification] Web search returned {len(search_results)} results")
        except Exception as e:
            logger.warning(f"[Verification] Web search failed: {e}")

    logger.info(
        f"[Verification] Done. Inconsistencies found: {len(verified.inconsistencies)}"
    )
    return verified