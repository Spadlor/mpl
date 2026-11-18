import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from api.admin import router as admin

load_dotenv()

def create_app() -> FastAPI:
    app = FastAPI(
        title="QXEL User API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.include_router(admin)
    public_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
    if os.path.isdir(public_dir):
        app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
    else:
        print(f"Warning: public directory not found at {public_dir}")

    return app


app = create_app()
