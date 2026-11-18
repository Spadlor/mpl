import os
import base64
import logging
import httpx
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")  # e.g. "8282828"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = "spadlor"
GITHUB_REPO = "mpl"
GITHUB_BRANCH = "main"
GITHUB_FILE_PATH = "public/scores.yml"
JSDELIVR_PURGE_URL = "https://purge.jsdelivr.net/"

logger = logging.getLogger("admin_scores")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)


async def _get_file_sha(client: httpx.AsyncClient) -> str | None:
    """Return the current SHA of the file, or None if it doesn't exist."""
    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{GITHUB_FILE_PATH}"
    )
    resp = await client.get(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        params={"ref": GITHUB_BRANCH},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("sha")


async def _put_file(
    client: httpx.AsyncClient,
    content: str,
    existing_sha: str | None,
) -> None:
    """Create (sha=None) or update (sha=<existing>) the file in one PUT."""
    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{GITHUB_FILE_PATH}"
    )
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": "chore: update scores.yml",
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    resp = await client.put(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json=payload,
    )
    resp.raise_for_status()


async def _purge_jsdelivr() -> None:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            JSDELIVR_PURGE_URL,
            headers={"content-type": "application/json"},
            json={
                "path": [
                    "/gh/spadlor/mpl@main/scores.yml",
                ]
            },
        )
        resp.raise_for_status()


@router.post("/admin")
async def update_scores(request: Request):
    """
    Body:
      {
        "password": "8282828",
        "file": "<yaml content>"
      }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )

    password = body.get("password")
    file_content = body.get("file")

    if not ADMIN_PASSWORD:
        logger.error("ADMIN_PASSWORD env var not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfigured",
        )

    if not password or password != ADMIN_PASSWORD:
        logger.warning("Rejected update-scores: bad password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    if not isinstance(file_content, str) or not file_content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or empty file content",
        )

    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN env var not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfigured",
        )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            existing_sha = await _get_file_sha(client)
            if existing_sha:
                logger.info(
                    "Updating existing scores.yml (sha=%s)", existing_sha[:10]
                )
            else:
                logger.info("Creating new scores.yml (no existing file)")

            await _put_file(client, file_content, existing_sha)
            logger.info(
                "scores.yml %s (%d bytes)",
                "updated" if existing_sha else "created",
                len(file_content),
            )

        await _purge_jsdelivr()
        logger.info("jsdelivr purge triggered")

        return {
            "status": "success",
            "message": "scores.yml updated and purge triggered",
            "action": "updated" if existing_sha else "created",
        }

    except httpx.HTTPStatusError as e:
        logger.error(
            "GitHub/JSdelivr error | status=%s | body=%s",
            e.response.status_code,
            e.response.text[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream error: {e.response.status_code}",
        )
    except Exception as e:
        logger.exception("Unexpected error in update-scores")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {type(e).__name__}",
        )
