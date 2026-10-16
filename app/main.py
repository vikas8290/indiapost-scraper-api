import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

app = FastAPI(
    title="India Post Free Self-Hosted Tracking API",
    description="A free, self-hosted REST API to track India Post / Speed Post consignments without RapidAPI.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for web apps and dashboard integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["General"])
def root():
    return {
        "service": "India Post Free Tracking Scraper API",
        "status": "online",
        "version": "1.0.0",
        "documentation": "/docs",
        "endpoints": {
            "track_get_path": "/api/track/{consignment_number}",
            "track_get_query": "/api/track?consignment=EE123456789IN",
            "track_post_json": "/api/track"
        }
    }


@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok", "cached_items": len(tracker_service.cache)}


@app.get("/api/track/{consignment_number}", response_model=TrackingResponse, tags=["Tracking"])
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


@app.get("/api/track", response_model=TrackingResponse, tags=["Tracking"])
def track_by_query(
    consignment: str = Query(..., description="13-character consignment number, e.g. EE123456789IN")
):
    """
    Track an India Post consignment number via query parameter.
    """
    return track_by_path(consignment)


@app.post("/api/track", response_model=TrackingResponse, tags=["Tracking"])
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
