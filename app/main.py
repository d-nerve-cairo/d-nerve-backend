"""
D-Nerve Backend API

FastAPI backend for Cairo informal transit network.
Provides ETA predictions using ML models.

Author: D-Nerve Backend Team
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Import routers
from app.routers import eta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="D-Nerve API",
    description="Backend API for Cairo's informal microbus network. Provides route discovery and ETA predictions.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(eta.router)
logger.info(" ETA prediction router registered")


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint - API status"""
    return {
        "message": "D-Nerve API v1.0.0",
        "status": "operational",
        "docs": "/docs",
        "endpoints": {
            "predict_eta": "/api/v1/predict-eta",
            "model_info": "/api/v1/model-info",
            "health": "/api/v1/health"
        }
    }


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info(" D-Nerve API starting up...")
    logger.info(" ML models loading...")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info(" D-Nerve API shutting down...")