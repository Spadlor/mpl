import os
import logging
import httpx
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
BLOB_READ_WRITE_TOKEN = os.getenv("BLOB_READ_WRITE_TOKEN")
BLOB_FILE_PATH = "scores.yml"

logger = logging.getLogger("admin_scores")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)


async def _put_vercel_blob(client: httpx.AsyncClient, content: str) -> dict:
    """Upload or override the scores.yml file directly in Vercel Blob."""
    # Vercel Blob Server Upload API endpoint
    url = f"https://blob.vercel-storage.com/{BLOB_FILE_PATH}"
    
    resp = await client.put(
        url,
        headers={
            "Authorization": f"Bearer {BLOB_READ_WRITE_TOKEN}",
            "x-access": "public",  # Change to "private" if your store is private
            "x-add-random-suffix": "0",  # Ensures it overwrites the exact filename without random string suffixes
            "x-allow-overwrite": "true", # Explicitly allows overriding an existing file
        },
        content=content.encode("utf-8"),
    )
    resp.raise_for_status()
    return resp.json()


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

    if not BLOB_READ_WRITE_TOKEN:
        logger.error("BLOB_READ_WRITE_TOKEN env var not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfigured",
        )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            logger.info("Updating scores.yml in Vercel Blob...")
            result = await _put_vercel_blob(client, file_content)
            logger.info(
                "scores.yml successfully updated in Vercel Blob (%d bytes)",
                len(file_content),
            )

        return {
            "status": "success",
            "message": "scores.yml updated successfully via Vercel Blob",
            "blob_url": result.get("url"),
        }

    except httpx.HTTPStatusError as e:
        logger.error(
            "Vercel Blob error | status=%s | body=%s",
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
