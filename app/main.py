import os
import logging
from pathlib import Path as FilePath
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.models.schemas import TrackingResponse, TrackRequest
from app.services.tracker import tracker_service

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("api")

# Disable public swagger/docs to hide API internals as requested
app = FastAPI(
    title="India Post Consignment Tracking Portal",
    description="Live Tracking Portal for India Post & Speed Post Consignments.",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES_DIR = FilePath(__file__).resolve().parent / "templates"
INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"


def get_html_content() -> str:
    if INDEX_HTML_PATH.exists():
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>India Post Tracking Portal</h1><p>Please enter consignment number to track.</p>"


@app.get("/", response_class=HTMLResponse, tags=["Tracking Portal"])
@app.head("/", response_class=HTMLResponse, tags=["Tracking Portal"])
def root():
    """
    Render clean, responsive tracking web interface for users.
    """
    return HTMLResponse(content=get_html_content(), status_code=200)


@app.get("/track/{consignment_number}", response_class=HTMLResponse, tags=["Tracking Portal"])
def track_page(consignment_number: str):
    """
    Deep-link route to open the tracking page with consignment prefilled.
    """
    return HTMLResponse(content=get_html_content(), status_code=200)


@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok", "cached_items": len(tracker_service.cache)}


@app.get("/api/track/{consignment_number}", response_model=TrackingResponse, tags=["Tracking API"])
def track_by_path(
    consignment_number: str = Path(..., description="13-character consignment number, e.g. EE123456789IN")
):
    """
    Track an India Post consignment number via path parameter.
    """
    logger.info(f"Tracking request received for: {consignment_number}")
    response = tracker_service.track(consignment_number)

    if not response.success and response.error and "Invalid" in response.error:
        raise HTTPException(status_code=400, detail=response.error)

    return response


@app.get("/api/track", response_model=TrackingResponse, tags=["Tracking API"])
def track_by_query(
    consignment: str = Query(..., description="13-character consignment number, e.g. EE123456789IN")
):
    """
    Track an India Post consignment number via query parameter.
    """
    return track_by_path(consignment)


@app.post("/api/track", response_model=TrackingResponse, tags=["Tracking API"])
def track_by_post(payload: TrackRequest):
    """
    Track an India Post consignment number via JSON POST body.
    """
    return track_by_path(payload.consignment_number)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
