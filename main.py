import os
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

def create_app() -> FastAPI:
    app = FastAPI(
        title="MPL API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.head("/")
    async def health_check():
        return {"status": "healthy", "service": "qxel_webhooks"}

    @app.head("/health")
    async def health():
        return {"status": "healthy"}

    try:
        from api.admin import router as admin_router
        app.include_router(admin_router)
    except ImportError:
        print("Warning: api.admin module not found", file=sys.stderr)
    public_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
    if os.path.isdir(public_dir):
        app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
    else:
        print(f"Warning: public directory not found at {public_dir}", file=sys.stderr)

    return app


app = create_app()
