"""
D-Nerve Backend API Server
FastAPI application for Cairo Informal Transit Platform

Author: D-Nerve Team
Version: 1.0.0
Date: January 2026
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings
from app.routers import eta, drivers, trips, routes, gamification

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = FastAPI(
    title=settings.APP_NAME,
    description="""
    Backend API for the D-Nerve Cairo Informal Transit Platform.
    
    ## Features
    - **ETA Prediction**: Estimate travel times for microbus routes
    - **Route Discovery**: Access discovered microbus routes
    - **Trip Tracking**: Submit and track GPS trips
    - **Gamification**: Driver scoring, leaderboards, and rewards
    
    ## ML Models
    - ETA Model: Linear Regression (MAE: 3.28 min)
    - Route Discovery: DBSCAN Clustering (F1: 0.963)
    """,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for mobile apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# INCLUDE ROUTERS
# =============================================================================

app.include_router(eta.router, prefix="/api/v1", tags=["ETA Prediction"])
app.include_router(routes.router, prefix="/api/v1", tags=["Routes"])
app.include_router(trips.router, prefix="/api/v1", tags=["Trips"])
app.include_router(drivers.router, prefix="/api/v1", tags=["Drivers"])
app.include_router(gamification.router, prefix="/api/v1", tags=["Gamification"])

# =============================================================================
# ROOT ENDPOINTS
# =============================================================================

@app.get("/", tags=["System"])
async def root():
    """API root - returns basic info"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health"
    }


@app.get("/api/v1/health", tags=["System"])
async def health_check():
    """System health check"""
    from app.ml.model_loader import DNerveModelLoader
    
    try:
        loader = DNerveModelLoader()
        ml_health = loader.health_check()
    except Exception as e:
        ml_health = {"healthy": False, "error": str(e)}
    
    return {
        "status": "healthy" if ml_health.get('healthy', False) else "degraded",
        "components": {
            "api": {"status": "healthy"},
            "ml_models": ml_health,
            "database": {"status": "healthy"}  # Update when DB connected
        },
        "version": settings.APP_VERSION
    }


@app.get("/api/v1/model-info", tags=["System"])
async def get_model_info():
    """Get ML model information"""
    from app.ml.model_loader import DNerveModelLoader
    
    loader = DNerveModelLoader()
    return loader.get_model_info()


# =============================================================================
# STARTUP & SHUTDOWN
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # Pre-load ML models
    try:
        from app.ml.model_loader import DNerveModelLoader
        loader = DNerveModelLoader()
        _ = loader.eta_model  # Trigger loading
        logger.info("✓ ML models loaded")
    except Exception as e:
        logger.error(f"✗ Failed to load ML models: {e}")
    
    logger.info("✓ Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("👋 Shutting down application")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("="*70)
    print("D-NERVE FASTAPI SERVER")
    print("="*70)
    print(f"\n📍 Starting {settings.APP_NAME}...")
    print("   Docs: http://localhost:8000/docs")
    print("   Health: http://localhost:8000/api/v1/health")
    print("\n")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
